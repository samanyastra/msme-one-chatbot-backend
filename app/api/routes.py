# Note: shared extensions (db, jwt, etc.) live in app/extensions.py and are
# initialized in the app factory. Import them from ..extensions when needed.
from . import api
from flask import jsonify, request
from ..models import User, Document
from ..extensions import db

@api.route("/users", methods=["GET"])
def list_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])

# Documents endpoints for admin UI

@api.route("/docs", methods=["GET"])
def list_docs():
    docs = Document.query.order_by(Document.created_at.desc()).all()
    return jsonify([d.to_dict() for d in docs])

@api.route("/docs", methods=["POST"])
def create_doc():
    # Accept JSON or form data
    data = request.get_json(silent=True) or request.form or {}
    title = data.get("title") or (request.files.get("file") and request.files["file"].filename)
    text = data.get("text")
    # If file uploaded, read its text
    if not text and request.files.get("file"):
        f = request.files["file"]
        try:
            text = f.read().decode("utf-8")
        except Exception:
            text = None
    if not title or not text:
        return jsonify({"msg": "title and text are required"}), 400
    d = Document(title=title, text=text)
    db.session.add(d)
    db.session.commit()
    return jsonify(d.to_dict()), 201

@api.route("/docs/<int:doc_id>", methods=["DELETE"])
def delete_doc(doc_id):
    d = Document.query.get(doc_id)
    if not d:
        return jsonify({"msg": "not found"}), 404
    db.session.delete(d)
    db.session.commit()
    return jsonify({"msg": "deleted"}), 200

@api.route("/docs/reindex", methods=["POST"])
def reindex_docs():
    # Placeholder: trigger reindexing job (vector DB creation). Implement later.
    # Here we simply return success and accepted so UI can show progress.
    return jsonify({"status": "reindex started"}), 202
