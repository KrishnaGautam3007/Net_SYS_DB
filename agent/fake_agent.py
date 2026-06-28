"""NetSysDB — fake agent with simulated metrics.

Generates synthetic metric readings without reading /proc. Useful for testing
on Windows or generating specific alert conditions (CPU spike, RAM pressure, etc.)
without stress-testing the system.

Scenarios (via SCENARIO env var):
  normal (default) — steady idle metrics
  cpu_spike — normal CPU for 5min, then 91-99% for 2min, repeat
  ram_pressure — RAM climbs 40→95% over 10min, then drops back
  dying — CPU + RAM climb, disk writes increase, stops heartbeat after 5min
  random — completely random values
"""

import json
import os
import random
import signal
import socket
import struct
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)

from shared import protocol

COLLECTOR_HOST = os.environ.get("COLLECTOR_HOST", "localhost")
COLLECTOR_PORT = int(os.environ.get("COLLECTOR_PORT", "9000"))
HEARTBEAT_PORT = int(os.environ.get("HEARTBEAT_PORT", "9001"))
MACHINE_ID = os.environ.get("MACHINE_ID", "fake-node-1")
SCENARIO = os.environ.get("SCENARIO", "normal")
METRIC_INTERVAL = 5
HEARTBEAT_INTERVAL = 10

import zlib

def _machine_id_hash(name: str) -> int:
    return zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFFFFFFFFFF


class FakeMetricGenerator:
    """Generates synthetic metrics based on scenario."""

    def __init__(self, scenario: str):
        self.scenario = scenario
        self.start_time = time.time()
        self.elapsed = 0
        self.cpu_in_spike = False

    def generate(self) -> dict:
        self.elapsed = time.time() - self.start_time

        if self.scenario == "normal":
            cpu = random.uniform(10, 40) + random.gauss(0, 2)
            ram_used = random.uniform(500, 1000) + random.gauss(0, 50)
            ram_total = 16000
            disk_w = random.uniform(0, 100)
        elif self.scenario == "cpu_spike":
            cycle = int(self.elapsed) % 420  # 300s normal + 120s spike
            if cycle < 300:
                self.cpu_in_spike = False
                cpu = random.uniform(15, 25) + random.gauss(0, 2)
            else:
                self.cpu_in_spike = True
                cpu = random.uniform(91, 99) + random.gauss(0, 1)
            ram_used = random.uniform(500, 1000)
            ram_total = 16000
            disk_w = random.uniform(0, 100)
        elif self.scenario == "ram_pressure":
            pct = (self.elapsed % 600) / 600.0  # 10min cycle
            if pct < 0.5:
                target = 40 + (pct * 2) * 55  # climb 40→95%
            else:
                target = 95 - ((pct - 0.5) * 2) * 55  # drop 95→40%
            ram_used = (target / 100.0) * 16000 + random.gauss(0, 100)
            ram_total = 16000
            cpu = random.uniform(10, 30)
            disk_w = random.uniform(0, 100)
        elif self.scenario == "dying":
            cpu = 5 + (self.elapsed / 300.0) * 90 + random.gauss(0, 2)
            ram_used = 500 + (self.elapsed / 300.0) * 14000 + random.gauss(0, 100)
            ram_total = 16000
            disk_w = 100 * (self.elapsed / 300.0) + random.uniform(0, 50)
        elif self.scenario == "random":
            cpu = random.uniform(0, 100)
            ram_used = random.uniform(100, 15000)
            ram_total = 16000
            disk_w = random.uniform(0, 10000)
        else:
            cpu = random.uniform(10, 40)
            ram_used = random.uniform(500, 1000)
            ram_total = 16000
            disk_w = random.uniform(0, 100)

        # Clamp to reasonable ranges
        cpu = max(0, min(100, cpu))
        ram_used = max(0, min(ram_total, ram_used))

        # Fake process list
        proc_names = ["nginx", "postgres", "python3", "node", "redis"]
        processes = [
            {
                "pid": 1000 + i,
                "name": proc_names[i % len(proc_names)],
                "ram_mb": round(random.uniform(10, 500), 2),
                "state": random.choice(["S", "R", "D"]),
            }
            for i in range(5)
        ]

        return {
            "machine_id": _machine_id_hash(MACHINE_ID),
            "machine_name": MACHINE_ID,
            "timestamp": time.time(),
            "cpu_percent": round(cpu, 2),
            "ram_used_mb": round(ram_used, 1),
            "ram_total_mb": ram_total,
            "disk_read_kb": random.randint(0, 500),
            "disk_write_kb": int(disk_w),
            "net_rx_kb": random.randint(0, 200),
            "net_tx_kb": random.randint(0, 200),
            "processes": processes,
        }


class FakeAgent:
    def __init__(self):
        self.machine_id = _machine_id_hash(MACHINE_ID)
        self.stop_event = threading.Event()
        self.gen = FakeMetricGenerator(SCENARIO)
        self._threads = []

    def sender_loop(self):
        sock = None
        backoff = 1
        while not self.stop_event.is_set():
            if sock is None:
                try:
                    sock = socket.create_connection(
                        (COLLECTOR_HOST, COLLECTOR_PORT), timeout=10
                    )
                    print(
                        f"[fake-agent] Connected to {COLLECTOR_HOST}:{COLLECTOR_PORT}",
                        flush=True,
                    )
                    backoff = 1
                except OSError as e:
                    print(
                        f"[fake-agent] connect failed ({e}); retrying in {backoff}s",
                        flush=True,
                    )
                    self.stop_event.wait(backoff)
                    backoff = min(backoff * 2, 60)
                    continue

            metric = self.gen.generate()
            try:
                sock.sendall(protocol.encode(protocol.MSG_METRIC, metric))
                print(
                    f"[fake-agent] {SCENARIO:12s} {MACHINE_ID:15s} "
                    f"cpu={metric['cpu_percent']:5.1f}% ram={int(metric['ram_used_mb']):5d}MB",
                    flush=True,
                )
            except OSError as e:
                print(f"[fake-agent] send failed ({e}); reconnecting", flush=True)
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

    def heartbeat_loop(self):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_heartbeat_time = 300 if SCENARIO == "dying" else float("inf")
        while not self.stop_event.is_set():
            if self.gen.elapsed < max_heartbeat_time:
                try:
                    packet = struct.pack("!QQ", self.machine_id, int(time.time()))
                    udp.sendto(packet, (COLLECTOR_HOST, HEARTBEAT_PORT))
                except OSError as e:
                    print(f"[fake-agent] heartbeat send failed ({e})", flush=True)
            self.stop_event.wait(HEARTBEAT_INTERVAL)
        udp.close()

    def start(self):
        targets = [self.sender_loop, self.heartbeat_loop]
        for fn in targets:
            t = threading.Thread(target=fn, name=fn.__name__, daemon=True)
            t.start()
            self._threads.append(t)
        print(
            f"[fake-agent] {MACHINE_ID} (scenario={SCENARIO}) started",
            flush=True,
        )

    def shutdown(self, signum=None, frame=None):
        print("[fake-agent] shutting down...", flush=True)
        self.stop_event.set()

    def join(self):
        while not self.stop_event.is_set():
            self.stop_event.wait(1)
        for t in self._threads:
            t.join(timeout=5)


def main():
    agent = FakeAgent()
    signal.signal(signal.SIGINT, agent.shutdown)
    try:
        signal.signal(signal.SIGTERM, agent.shutdown)
    except (AttributeError, ValueError):
        pass
    agent.start()
    agent.join()
    print("[fake-agent] stopped.", flush=True)


if __name__ == "__main__":
    main()
