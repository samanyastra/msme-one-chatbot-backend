from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# --- ensure eventlet monkey patching happens before importing app/socketio ---
try:
    import eventlet
    # apply monkey patch so standard library modules are cooperative with eventlet
    eventlet.monkey_patch()
except Exception:
    # eventlet may not be installed in all environments; socketio will fallback to other async modes
    pass

from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    # Use socketio.run for local development so websocket/polling endpoints are available.
    socketio.run(app, host="0.0.0.0", port=int(__import__("os").environ.get("PORT", 5000)), debug=True)

