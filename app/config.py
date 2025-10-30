import os
import sys
import logging


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///data.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me")
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def configure_logging(level: str | None = None, fmt: str | None = None, datefmt: str | None = None) -> None:
    """Configure root logging so background tasks and threads inherit settings.

    This function is safe to call multiple times. It sets a StreamHandler to
    stdout and adjusts common library logger levels (werkzeug, sqlalchemy).
    Call early during app startup or rely on the module import-time call below.
    """

    level_name = (level or os.getenv("LOG_LEVEL") or Config.LOG_LEVEL).upper()
    try:
        lvl = getattr(logging, level_name)
    except Exception:
        lvl = logging.INFO

    root = logging.getLogger()
    root.setLevel(lvl)

    formatter = logging.Formatter(
        fmt or "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt=datefmt or "%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(lvl)
    stream_handler.setFormatter(formatter)

    # Use basicConfig with force if available (Python 3.8+). This replaces
    # existing handlers and avoids duplicate logs when reconfiguring.
    try:
        logging.basicConfig(level=lvl, handlers=[stream_handler], force=True)
    except TypeError:
        # Older Python: clear handlers, then add our handler
        for h in list(root.handlers):
            root.removeHandler(h)
        root.addHandler(stream_handler)

    # Make typical third-party loggers follow the same level so background
    # tasks that use them also emit logs at INFO/DEBUG.
    for logger_name in ("werkzeug", "sqlalchemy", "socketio", "engineio"):
        try:
            logging.getLogger(logger_name).setLevel(lvl)
        except Exception:
            pass

    # Capture warnings via logging
    try:
        logging.captureWarnings(True)
    except Exception:
        pass


# Configure logging at import time so background threads/processes that
# import `app.config` will inherit these settings by default.
configure_logging()
