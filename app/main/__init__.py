from flask import Blueprint

main = Blueprint("main", __name__)

from . import routes  # noqa: F401
