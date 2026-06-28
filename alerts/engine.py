"""NetSysDB — rule-based sliding-window alert engine.

Purely rule-based (no ML). For each (machine, rule) pair a sliding window of
``(timestamp, value)`` samples is kept in a deque. A rule *fires* when:

* every sample currently in the window exceeds the rule's threshold, AND
* the window spans at least ``window_sec`` seconds (a full window of data),
  AND
* there is no already-open alert for that (machine, rule).

An open alert *resolves* when the latest sample drops below the threshold.

Fired and resolved alerts are persisted to ``<data_dir>/alerts.json`` so the
query engine and REST API can read alert history (a small metadata sidecar,
not the binary metrics store).
"""

import json
import os
import time
import uuid
from collections import defaultdict, deque

DEFAULT_RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")


class AlertEngine:
    def __init__(
        self, rules_path=DEFAULT_RULES_PATH, storage_engine=None, data_dir=None
    ):
        self.rules_path = rules_path
        self.rules = self._load_rules(rules_path)
        self._storage = storage_engine
        self.data_dir = data_dir or getattr(storage_engine, "data_dir", "data")

        # per machine -> per rule name -> deque[(ts, value)]
        self._windows = defaultdict(lambda: defaultdict(deque))
        # "machine|rule" -> open alert dict
        self._open_alerts = {}
        # full alert history (loaded from disk so it survives restarts)
        self._all_alerts = self._load_persisted()

    # -- rule + persistence helpers ---------------------------------------

    @staticmethod
    def _load_rules(path):
        with open(path, "r") as fh:
            return json.load(fh)

    def _alerts_path(self):
        return os.path.join(self.data_dir, "alerts.json")

    def _load_persisted(self):
        try:
            with open(self._alerts_path(), "r") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return []

    def _persist(self):
        path = self._alerts_path()
        try:
            tmp = path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(self._all_alerts, fh)
            os.replace(tmp, path)
        except OSError as e:
            print(f"[alerts] persist failed: {e}", flush=True)

    # -- value extraction --------------------------------------------------

    @staticmethod
    def _value(metric, field):
        if field == "ram_pct":
            total = metric.get("ram_total_mb") or 0
            used = metric.get("ram_used_mb") or 0
            return (used / total * 100.0) if total else 0.0
        return metric.get(field, 0)

    # -- evaluation --------------------------------------------------------

    def evaluate(self, metric: dict) -> list:
        """Update windows for a metric and return newly fired alerts."""
        machine = metric.get("machine_name", str(metric.get("machine_id")))
        ts = metric.get("timestamp", time.time())
        fired = []

        for rule in self.rules:
            name = rule["name"]
            threshold = rule["threshold"]
            window_sec = rule["window_sec"]
            value = self._value(metric, rule["field"])

            window = self._windows[machine][name]
            window.append((ts, value))
            # Trim samples older than the rule's window.
            while window and (ts - window[0][0]) > window_sec:
                window.popleft()

            key = f"{machine}|{name}"
            open_alert = self._open_alerts.get(key)

            spans_window = (window[-1][0] - window[0][0]) >= window_sec
            all_exceed = all(v > threshold for _, v in window)

            if open_alert is None:
                if spans_window and all_exceed and len(window) >= 2:
                    alert = {
                        "id": str(uuid.uuid4()),
                        "machine": machine,
                        "rule": name,
                        "severity": rule["severity"],
                        "field": rule["field"],
                        "threshold": threshold,
                        "fired_at": ts,
                        "resolved_at": None,
                    }
                    self._open_alerts[key] = alert
                    self._all_alerts.append(alert)
                    self._persist()
                    fired.append(alert)
            else:
                # Resolve when the latest sample falls back below threshold.
                if value < threshold:
                    open_alert["resolved_at"] = ts
                    del self._open_alerts[key]
                    self._persist()

        return fired

    # -- introspection / management ---------------------------------------

    def get_open_alerts(self) -> list:
        return list(self._open_alerts.values())

    def get_all_alerts(self) -> list:
        return list(self._all_alerts)

    def reload_rules(self, rules_path=None):
        """Re-read rules from disk (used by the Settings page hot-reload)."""
        self.rules_path = rules_path or self.rules_path
        self.rules = self._load_rules(self.rules_path)
        return self.rules
