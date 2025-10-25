# Note: shared extensions (db, jwt, etc.) live in app/extensions.py and are
# initialized in the app factory. Import them from ..extensions when needed.
from . import api
from flask import jsonify
from ..models import User

@api.route("/users", methods=["GET"])
def list_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])
