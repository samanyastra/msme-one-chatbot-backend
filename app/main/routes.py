from flask import current_app, jsonify
from . import main

@main.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "app": current_app.import_name})
