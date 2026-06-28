"""NetSysDB — monitoring agent.

Runs on each monitored machine. Three threads:

* **MetricReader**  — every ``METRIC_INTERVAL`` seconds reads OS metrics from
  ``/proc`` and stores the latest snapshot under a lock.
* **MetricSender**  — keeps a persistent TCP connection to the collector and
  forwards the latest snapshot every interval, reconnecting with exponential
  backoff on failure.
* **Heartbeat**     — sends a small UDP packet every 10 seconds so the
  collector can detect when this agent goes offline.

SIGTERM / SIGINT set a stop Event so all threads exit cleanly.
"""

import os
import platform
import signal
import socket
import struct
import sys
import threading
import time
import zlib

# Make `import proc_reader` (same dir) and `from shared import protocol` work
# regardless of how the script is launched.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)

import proc_reader  # noqa: E402
from shared import protocol  # noqa: E402

COLLECTOR_HOST = os.environ.get("COLLECTOR_HOST", "localhost")
COLLECTOR_PORT = int(os.environ.get("COLLECTOR_PORT", "9000"))
HEARTBEAT_PORT = int(os.environ.get("HEARTBEAT_PORT", "9001"))
MACHINE_ID = os.environ.get("MACHINE_ID", platform.node() or "unknown")
METRIC_INTERVAL = int(os.environ.get("METRIC_INTERVAL", "5"))
HEARTBEAT_INTERVAL = 10
MAX_BACKOFF = 60


def _machine_id_hash(name: str) -> int:
    """Deterministic 64-bit id for a machine name.

    NOTE: Python's built-in ``hash()`` is salted per-process (PYTHONHASHSEED),
    which would make the id change on every restart and could desync the TCP
    metric id from the UDP heartbeat id. A CRC32 is used instead so the id is
    stable across restarts and identical for the metric and heartbeat paths.
    """
    env = os.environ.get("MACHINE_ID_HASH")
    if env is not None:
        return int(env) & 0xFFFFFFFFFFFFFFFF
    return zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFFFFFFFFFF


class Agent:
    def __init__(self):
        self.machine_name = MACHINE_ID
        self.machine_id = _machine_id_hash(self.machine_name)
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_metric = None
        self._threads = []

    # -- thread 1: read /proc ---------------------------------------------

    def reader_loop(self):
        while not self.stop_event.is_set():
            try:
                cpu = proc_reader.read_cpu()  # includes a 0.5s internal sample
                mem = proc_reader.read_memory()
                disk = proc_reader.read_disk()
                net = proc_reader.read_network()
                procs = proc_reader.read_processes()
                metric = {
                    "machine_id": self.machine_id,
                    "machine_name": self.machine_name,
                    "timestamp": time.time(),
                    "cpu_percent": cpu,
                    "ram_used_mb": mem["used_mb"],
                    "ram_total_mb": mem["total_mb"],
                    "disk_read_kb": disk["read_kb"],
                    "disk_write_kb": disk["write_kb"],
                    "net_rx_kb": net["rx_kb"],
                    "net_tx_kb": net["tx_kb"],
                    "processes": procs,
                }
                with self._lock:
                    self._latest_metric = metric
            except Exception as e:  # keep the agent alive on transient errors
                print(f"[reader] error: {e}", flush=True)
            self.stop_event.wait(METRIC_INTERVAL)

    # -- thread 2: send over TCP ------------------------------------------

    def _connect(self):
        """Block (interruptibly) until connected; backs off exponentially."""
        backoff = 1
        while not self.stop_event.is_set():
            try:
                sock = socket.create_connection(
                    (COLLECTOR_HOST, COLLECTOR_PORT), timeout=10
                )
                print(
                    f"Connected to collector {COLLECTOR_HOST}:{COLLECTOR_PORT}",
                    flush=True,
                )
                return sock
            except OSError as e:
                print(
                    f"[sender] connect failed ({e}); retrying in {backoff}s",
                    flush=True,
                )
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
        return None

    def sender_loop(self):
        sock = None
        while not self.stop_event.is_set():
            if sock is None:
                sock = self._connect()
                if sock is None:
                    break  # stop requested during connect
            with self._lock:
                metric = self._latest_metric
            if metric is None:
                # No snapshot yet — check back soon rather than waiting a full
                # interval so the first metric is sent promptly.
                self.stop_event.wait(0.5)
                continue
            try:
                sock.sendall(protocol.encode(protocol.MSG_METRIC, metric))
                print(
                    f"Metric sent: {metric['machine_name']} "
                    f"cpu={metric['cpu_percent']} ram={metric['ram_used_mb']}MB",
                    flush=True,
                )
            except OSError as e:
                print(f"[sender] send failed ({e}); reconnecting", flush=True)
                try:
                    sock.close()
                except OSError:
                    pass
                sock = None
                continue
            self.stop_event.wait(METRIC_INTERVAL)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    # -- thread 3: UDP heartbeat ------------------------------------------

    def heartbeat_loop(self):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while not self.stop_event.is_set():
            try:
                packet = struct.pack("!QQ", self.machine_id, int(time.time()))
                udp.sendto(packet, (COLLECTOR_HOST, HEARTBEAT_PORT))
            except OSError as e:
                print(f"[heartbeat] send failed ({e})", flush=True)
            self.stop_event.wait(HEARTBEAT_INTERVAL)
        udp.close()

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        targets = [self.reader_loop, self.sender_loop, self.heartbeat_loop]
        for fn in targets:
            t = threading.Thread(target=fn, name=fn.__name__, daemon=True)
            t.start()
            self._threads.append(t)
        print(
            f"Agent '{self.machine_name}' (id={self.machine_id}) started; "
            f"collector={COLLECTOR_HOST}:{COLLECTOR_PORT} interval={METRIC_INTERVAL}s",
            flush=True,
        )

    def shutdown(self, signum=None, frame=None):
        print("Agent shutting down...", flush=True)
        self.stop_event.set()

    def join(self):
        # Wait until stopped, then join worker threads.
        while not self.stop_event.is_set():
            self.stop_event.wait(1)
        for t in self._threads:
            t.join(timeout=5)


def main():
    agent = Agent()
    signal.signal(signal.SIGINT, agent.shutdown)
    try:
        signal.signal(signal.SIGTERM, agent.shutdown)
    except (AttributeError, ValueError):
        pass  # SIGTERM may be unavailable on some platforms
    agent.start()
    agent.join()
    print("Agent stopped.", flush=True)


if __name__ == "__main__":
    main()
