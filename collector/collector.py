"""NetSysDB — collector server.

A single-threaded event loop (``selectors``) that:

* accepts TCP connections from all agents and reads framed metric messages,
* receives UDP heartbeats for liveness tracking,
* runs a 6-step pipeline per metric (validate -> pack -> store -> index ->
  alert -> emit),
* rebuilds the timestamp B+ tree from storage on startup,
* flags agents offline after 60s of silence,
* serves the web API/WebSocket from a background thread (wired in Phase 11).

The Flask/SocketIO web layer and the rule-based AlertEngine are stubbed here
and filled in by later phases; the collector degrades gracefully until then.
"""

import json
import os
import selectors
import signal
import socket
import struct
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from query.engine import QueryEngine  # noqa: E402
from shared import protocol  # noqa: E402
from storage.bplustree import BPlusTree  # noqa: E402
from storage.engine import StorageEngine  # noqa: E402

# AlertEngine arrives in Phase 10; fall back to a no-op stub until then.
try:
    from alerts.engine import AlertEngine  # noqa: E402
except Exception:

    class AlertEngine:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def evaluate(self, metric):
            return []

        def get_open_alerts(self):
            return []


TCP_PORT = int(os.environ.get("COLLECTOR_PORT", "9000"))
UDP_PORT = int(os.environ.get("HEARTBEAT_PORT", "9001"))
WEB_PORT = int(os.environ.get("WEB_PORT", "5000"))
DATA_DIR = os.environ.get("DATA_DIR", "data")
OFFLINE_AFTER = 60  # seconds without a heartbeat/metric => OFFLINE

REQUIRED_FIELDS = (
    "machine_id",
    "machine_name",
    "timestamp",
    "cpu_percent",
    "ram_used_mb",
    "ram_total_mb",
    "disk_read_kb",
    "disk_write_kb",
    "net_rx_kb",
    "net_tx_kb",
)


class Collector:
    def __init__(self, data_dir=DATA_DIR):
        self.sel = selectors.DefaultSelector()
        self.engine = StorageEngine(data_dir)
        self.tree = BPlusTree()
        self.alert_engine = AlertEngine(storage_engine=self.engine)

        self.last_seen = {}  # machine_id (int) -> last activity timestamp
        self.last_seen_by_name = {}  # machine_name -> last metric timestamp
        self.machines = {}  # machine_name -> latest metric dict
        self.names = {}  # machine_id -> machine_name
        self._offline = set()  # machine_ids already reported offline

        self.data_dir = data_dir
        self.shutdown_event = threading.Event()
        self.start_time = time.time()
        self.listen_sock = None
        self.udp_sock = None

        # Emit hooks, set by the web layer in Phase 11 (no-ops until then).
        self.emit_metric = None
        self.emit_alert = None

        self._rebuild_index()

    # -- startup -----------------------------------------------------------

    def _rebuild_index(self):
        count = 0
        for page_id, slot_offset, record in self.engine.scan_all():
            self.tree.insert(record["timestamp"], (page_id, slot_offset))
            count += 1
        print(f"Rebuilt B+ tree from storage: {count} records", flush=True)

    def _setup_sockets(self):
        ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ls.bind(("0.0.0.0", TCP_PORT))
        ls.listen(64)
        ls.setblocking(False)
        self.sel.register(ls, selectors.EVENT_READ, data=None)
        self.listen_sock = ls
        print(f"Listening on TCP :{TCP_PORT}", flush=True)

        us = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        us.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        us.bind(("0.0.0.0", UDP_PORT))
        us.setblocking(False)
        self.sel.register(us, selectors.EVENT_READ, data=None)
        self.udp_sock = us
        print(f"Listening on UDP :{UDP_PORT}", flush=True)

    def _start_web(self):
        """Populate shared state and start the Flask/SocketIO server thread."""
        try:
            from web import api as web_api  # noqa: F401  (registers routes)
            from web import state as web_state
            from web.socket_server import emit_alert, emit_metric, socketio, app

            web_state.storage_engine = self.engine
            web_state.bplus_tree = self.tree
            web_state.alert_engine = self.alert_engine
            web_state.query_engine = QueryEngine(
                self.engine, self.tree, data_dir=self.data_dir
            )
            web_state.machines = self.machines
            web_state.last_seen = self.last_seen_by_name
            web_state.names = self.names
            web_state.start_time = self.start_time

            self.emit_metric = emit_metric
            self.emit_alert = emit_alert

            def _serve():
                socketio.run(
                    app,
                    host="0.0.0.0",
                    port=WEB_PORT,
                    allow_unsafe_werkzeug=True,
                )

            threading.Thread(target=_serve, daemon=True, name="web").start()
            print(f"Web API + WebSocket on :{WEB_PORT}", flush=True)
        except Exception as e:
            print(f"Web API failed to start: {e}", flush=True)

    # -- socket handlers ---------------------------------------------------

    def _accept(self):
        conn, addr = self.listen_sock.accept()
        conn.setblocking(True)
        self.sel.register(
            conn, selectors.EVENT_READ, data={"addr": addr, "machine_id": None}
        )
        print(f"Agent connected from {addr}", flush=True)

    def _disconnect(self, sock, state, reason):
        try:
            self.sel.unregister(sock)
        except (KeyError, ValueError):
            pass
        try:
            sock.close()
        except OSError:
            pass
        print(f"Agent disconnected {state.get('addr')}: {reason}", flush=True)

    def _handle_agent(self, sock, state):
        try:
            msg_type, payload = protocol.recv_message(sock)
        except (ConnectionError, OSError, ValueError) as e:
            self._disconnect(sock, state, e)
            return

        if msg_type == protocol.MSG_METRIC:
            state["machine_id"] = payload.get("machine_id")
            self._pipeline(payload)
        elif msg_type == protocol.MSG_HEARTBEAT:
            mid = payload.get("machine_id")
            if mid is not None:
                self.last_seen[mid] = time.time()

    def _handle_heartbeat(self):
        try:
            data, _addr = self.udp_sock.recvfrom(16)
        except OSError:
            return
        if len(data) < 16:
            return
        machine_id, _ts = struct.unpack("!QQ", data[:16])
        self.last_seen[machine_id] = time.time()
        if machine_id in self._offline:
            self._offline.discard(machine_id)
            print(
                f"Agent back ONLINE: {self.names.get(machine_id, machine_id)}",
                flush=True,
            )

    # -- pipeline ----------------------------------------------------------

    def _pipeline(self, metric):
        # Step 1: validate.
        for field in REQUIRED_FIELDS:
            if field not in metric:
                print(f"[pipeline] dropping metric missing '{field}'", flush=True)
                return

        # Step 2 + 3: pack + persist (StorageEngine.write packs internally and
        # logs via the WAL before writing).
        page_id, slot_offset = self.engine.write(metric)

        # Step 4: index by timestamp for range queries.
        self.tree.insert(metric["timestamp"], (page_id, slot_offset))

        # Step 5: evaluate alert rules.
        fired = self.alert_engine.evaluate(metric) or []

        # Step 6: update live state and broadcast.
        name = metric["machine_name"]
        self.machines[name] = metric
        if self.names.get(metric["machine_id"]) != name:
            self.names[metric["machine_id"]] = name
            self._write_registry()  # keep machines.json in sync for queries
        self.last_seen[metric["machine_id"]] = time.time()
        self.last_seen_by_name[name] = time.time()
        if self.emit_metric:
            self.emit_metric(metric)
        for alert in fired:
            print(
                f"ALERT FIRED: {alert['rule']} on {alert['machine']} "
                f"[{alert['severity']}]",
                flush=True,
            )
            if self.emit_alert:
                self.emit_alert(alert)

    def _write_registry(self):
        """Persist the machine_id -> machine_name map for the query engine.

        This is a small metadata sidecar (not the metrics store), so JSON is
        appropriate here. The query engine / CLI load it to resolve names,
        since the binary record only stores the numeric machine_id.
        """
        path = os.path.join(self.data_dir, "machines.json")
        registry = {str(mid): name for mid, name in self.names.items()}
        try:
            tmp = path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(registry, fh)
            os.replace(tmp, path)
        except OSError as e:
            print(f"[registry] write failed: {e}", flush=True)

    def _check_offline_agents(self):
        now = time.time()
        for mid, last in list(self.last_seen.items()):
            if now - last > OFFLINE_AFTER and mid not in self._offline:
                self._offline.add(mid)
                print(
                    f"WARNING: agent OFFLINE: {self.names.get(mid, mid)}",
                    flush=True,
                )

    # -- main loop ---------------------------------------------------------

    def run(self):
        self._setup_sockets()
        self._start_web()
        print("Collector running.", flush=True)
        while not self.shutdown_event.is_set():
            try:
                # A short timeout keeps shutdown and offline checks responsive
                # (spec suggested 30s; 5s reacts faster with no downside).
                events = self.sel.select(timeout=5.0)
            except OSError:
                continue  # interrupted by a signal — re-check shutdown flag
            for key, _mask in events:
                if key.fileobj is self.listen_sock:
                    self._accept()
                elif key.fileobj is self.udp_sock:
                    self._handle_heartbeat()
                else:
                    self._handle_agent(key.fileobj, key.data)
            self._check_offline_agents()
        self._cleanup()

    def shutdown(self, signum=None, frame=None):
        print("Collector shutting down...", flush=True)
        self.shutdown_event.set()

    def _cleanup(self):
        try:
            self.sel.close()
        except Exception:
            pass
        for s in (self.listen_sock, self.udp_sock):
            try:
                if s:
                    s.close()
            except OSError:
                pass
        try:
            self.engine.close()
        except Exception:
            pass
        print("Collector stopped.", flush=True)


def main():
    collector = Collector()
    signal.signal(signal.SIGINT, collector.shutdown)
    try:
        signal.signal(signal.SIGTERM, collector.shutdown)
    except (AttributeError, ValueError):
        pass
    collector.run()


if __name__ == "__main__":
    main()
