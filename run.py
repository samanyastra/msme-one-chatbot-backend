from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    # Use socketio.run for local development so websocket/polling endpoints are available.
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
    
