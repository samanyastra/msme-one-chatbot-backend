from flask import Flask

def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=False)

    # load config
    from .config import Config
    app.config.from_object(config_object or Config)

    # init extensions
    from .extensions import db, migrate, jwt, socketio
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    # initialize socketio with the Flask app
    socketio.init_app(app, cors_allowed_origins="*")

    # register blueprints
    from .main import main as main_bp
    app.register_blueprint(main_bp)

    from .auth import auth as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from .api import api as api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    from .ui import ui as ui_bp
    app.register_blueprint(ui_bp, url_prefix="/ui")

    # import socket event handlers so decorators register with the socketio instance
    # ensure this import happens after socketio.init_app(app)
    try:
        from .chat import socketio_events  # noqa: F401
    except Exception:
        # if import fails (e.g., during packaging), fail silently to not break the app creation
        pass

    return app
