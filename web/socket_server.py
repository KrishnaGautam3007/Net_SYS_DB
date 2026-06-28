"""NetSysDB — Flask app + Socket.IO server.

Hosts the REST API (defined in ``web.api``) and the WebSocket channel used to
push live metric/alert updates to the React dashboard. The built UI in
``ui/dist`` is served as static files; SPA client routes fall back to
``index.html``.
"""

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO

app = Flask(__name__, static_folder="../ui/dist", static_url_path="")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# -- WebSocket emit helpers (called by the collector) ---------------------


def emit_metric(metric: dict):
    socketio.emit("metric_update", metric)


def emit_alert(alert: dict):
    socketio.emit("alert_fired", alert)


def emit_agent_status(event: str, data: dict):
    socketio.emit(event, data)  # "agent_online" or "agent_offline"


# -- static / SPA serving --------------------------------------------------


@app.route("/")
def index():
    import os

    index_path = os.path.join(app.static_folder, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, "index.html")
    return jsonify(
        {
            "service": "NetSysDB",
            "ui": "not built yet — run: cd ui && npm install && npm run build",
        }
    )


@app.route("/<path:path>")
def spa(path):
    """Serve a static asset if it exists, else fall back to index.html."""
    import os

    full = os.path.join(app.static_folder, path)
    if os.path.exists(full) and os.path.isfile(full):
        return send_from_directory(app.static_folder, path)
    index_path = os.path.join(app.static_folder, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, "index.html")
    return jsonify({"error": "not found"}), 404


@socketio.on("connect")
def on_connect():
    print("WebSocket client connected", flush=True)


@socketio.on("disconnect")
def on_disconnect():
    print("WebSocket client disconnected", flush=True)
