from flask import render_template, request, redirect, url_for, flash
from . import ui
from ..models import User
from ..extensions import db
from flask_jwt_extended import create_access_token  # optional if you want to create tokens

@ui.route("/register", methods=["GET"])
def register():
    return render_template("auth/register.html")

@ui.route("/register", methods=["POST"])
def register_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not username or not password:
        flash("Username and password are required", "error")
        return render_template("auth/register.html"), 400

    if password != confirm:
        flash("Passwords do not match", "error")
        return render_template("auth/register.html"), 400

    if User.query.filter_by(username=username).first():
        flash("User already exists", "error")
        return render_template("auth/register.html"), 400

    u = User(username=username)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()

    flash("Account created. Please log in.", "success")
    return redirect(url_for("ui.login"))

@ui.route("/login", methods=["GET"])
def login():
    return render_template("auth/login.html")

@ui.route("/login", methods=["POST"])
def login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Username and password are required", "error")
        return render_template("auth/login.html"), 400

    u = User.query.filter_by(username=username).first()
    if not u or not u.check_password(password):
        flash("Invalid credentials", "error")
        return render_template("auth/login.html"), 401

    # optional: create a JWT token if you want to integrate JWT-based UI flows
    # token = create_access_token(identity=u.id)
    flash("Signed in successfully", "success")
    return redirect(url_for("main.index"))

# New: serve the chat UI page at /ui/chat
@ui.route("/chat", methods=["GET"])
def chat():
    return render_template("chat/chat.html")

# New: serve the admin UI page at /ui/admin
@ui.route("/admin", methods=["GET"])
def admin():
    return render_template("admin/admin.html")
