"""NetSysDB — REST API endpoints.

Importing this module registers all routes on the Flask ``app`` from
``web.socket_server``. The collector imports it during startup.
"""

import json
import time
import uuid

from flask import jsonify, request

from web import state
from web.socket_server import app, socketio


def _status_for(name: str) -> str:
    now = time.time()
    last = state.last_seen.get(name, 0)
    if now - last > state.OFFLINE_AFTER:
        return "OFFLINE"
    if state.alert_engine and any(
        a["machine"] == name for a in state.alert_engine.get_open_alerts()
    ):
        return "ALERT"
    return "ONLINE"


@app.route("/api/machines")
def get_machines():
    result = []
    for name, metric in state.machines.items():
        result.append(
            {
                "machine_name": name,
                "machine_id": metric.get("machine_id"),
                "cpu_percent": metric.get("cpu_percent"),
                "ram_used_mb": metric.get("ram_used_mb"),
                "ram_total_mb": metric.get("ram_total_mb"),
                "status": _status_for(name),
                "last_seen": state.last_seen.get(name, 0),
            }
        )
    result.sort(key=lambda m: m["machine_name"])
    return jsonify(result)


@app.route("/api/machines/<machine_name>/metrics")
def get_machine_metrics(machine_name):
    now = time.time()
    records = []
    if state.bplus_tree is not None and state.storage_engine is not None:
        for page_id, slot_offset in state.bplus_tree.range_query(now - 1800, now):
            rec = state.storage_engine.read(page_id, slot_offset)
            if state.names.get(rec["machine_id"]) == machine_name:
                rec["machine_name"] = machine_name
                records.append(rec)
    records.sort(key=lambda r: r["timestamp"])

    # Down-sample to at most 500 points, spread evenly.
    if len(records) > 500:
        step = len(records) / 500.0
        records = [records[int(i * step)] for i in range(500)]
    return jsonify(records)


@app.route("/api/machines/<machine_name>/procs")
def get_machine_procs(machine_name):
    metric = state.machines.get(machine_name)
    return jsonify(metric.get("processes", []) if metric else [])


@app.route("/api/query", methods=["POST"])
def post_query():
    body = request.get_json(silent=True) or {}
    q = body.get("q", "")
    if not q.strip():
        return jsonify({"error": "empty query"}), 400
    try:
        rows = state.query_engine.execute(q)
        return jsonify(rows)
    except Exception as e:  # parser/executor errors -> 400 with message
        return jsonify({"error": str(e)}), 400


@app.route("/api/alerts")
def get_alerts():
    severity = request.args.get("severity")
    machine = request.args.get("machine")
    from_ts = request.args.get("from", type=float)

    alerts = state.alert_engine.get_all_alerts() if state.alert_engine else []
    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]
    if machine:
        alerts = [a for a in alerts if a.get("machine") == machine]
    if from_ts is not None:
        alerts = [a for a in alerts if a.get("fired_at", 0) >= from_ts]
    alerts = sorted(alerts, key=lambda a: a.get("fired_at", 0), reverse=True)
    return jsonify(alerts)


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        rules = state.alert_engine.rules if state.alert_engine else []
        return jsonify({"rules": rules})

    body = request.get_json(silent=True) or {}
    rules = body.get("rules")
    if rules is None:
        return jsonify({"error": "missing 'rules'"}), 400
    path = state.alert_engine.rules_path
    try:
        with open(path, "w") as fh:
            json.dump(rules, fh, indent=2)
        state.alert_engine.reload_rules(path)
    except (OSError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "ok"})


@app.route("/api/status")
def get_status():
    now = time.time()
    connected = sum(
        1
        for n in state.machines
        if now - state.last_seen.get(n, 0) <= state.OFFLINE_AFTER
    )
    record_count = state.storage_engine.count_records() if state.storage_engine else 0
    page_count = state.storage_engine.page_count() if state.storage_engine else 0
    open_alerts = len(state.alert_engine.get_open_alerts()) if state.alert_engine else 0
    return jsonify(
        {
            "uptime_sec": int(now - state.start_time),
            "record_count": record_count,
            "page_count": page_count,
            "connected_agents": connected,
            "open_alerts": open_alerts,
        }
    )


@app.route("/api/alerts/create", methods=["POST"])
def create_alert():
    """Manually create an alert for testing."""
    body = request.get_json(silent=True) or {}
    machine = body.get("machine", "unknown")
    severity = body.get("severity", "MEDIUM")
    message = body.get("message", "Manual alert")

    alert = {
        "id": str(uuid.uuid4()),
        "machine": machine,
        "rule": "manual",
        "severity": severity,
        "field": None,
        "threshold": None,
        "fired_at": time.time(),
        "resolved_at": None,
    }

    if state.alert_engine:
        state.alert_engine._all_alerts.append(alert)
        state.alert_engine._persist()

    socketio.emit("alert_fired", alert)
    return jsonify({"status": "ok", "alert_id": alert["id"]})


@app.route("/api/alerts/<alert_id>/resolve", methods=["POST"])
def resolve_alert(alert_id):
    """Manually resolve an alert."""
    if not state.alert_engine:
        return jsonify({"error": "alert engine not initialized"}), 500

    for alert in state.alert_engine._all_alerts:
        if alert.get("id") == alert_id:
            alert["resolved_at"] = time.time()
            state.alert_engine._persist()
            socketio.emit("alert_resolved", alert)
            return jsonify({"status": "ok"})

    return jsonify({"error": f"alert {alert_id} not found"}), 404
