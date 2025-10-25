from flask import request, jsonify
from . import auth
from ..models import User
from ..extensions import db
from flask_jwt_extended import create_access_token

@auth.route("/register", methods=["POST"])
def register():
    # accept JSON or form; avoid content-type logging with silent=True
    data = request.get_json(silent=True) or request.form or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"msg": "username and password required"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"msg": "user exists"}), 400
    u = User(username=username)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return jsonify(u.to_dict()), 201

@auth.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form or {}
    username = data.get("username")
    password = data.get("password", "")
    u = User.query.filter_by(username=username).first()
    if not u or not u.check_password(password):
        return jsonify({"msg": "bad credentials"}), 401
    token = create_access_token(identity=u.id)
    return jsonify({"access_token": token}), 200
