from flask import Blueprint

ui = Blueprint("ui", __name__, template_folder="../templates")

from . import routes  # noqa: F401
