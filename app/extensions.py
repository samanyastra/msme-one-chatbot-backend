"""Module that exposes extension singletons.

Purpose:
- Create extension instances (SQLAlchemy, Migrate, JWT, SocketIO) here without binding
  them to an app. This avoids circular imports and lets any module import these objects.
- In the app factory (create_app) call each_extension.init_app(app) to bind them
  to the Flask application instance.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
# Set async_mode to 'eventlet' and allow cross-origin connections by default.
socketio = SocketIO(async_mode="eventlet", cors_allowed_origins="*")  # call socketio.init_app(app, cors_allowed_origins="*") in create_app

