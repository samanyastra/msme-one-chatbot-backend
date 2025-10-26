# Note: shared extensions (db, jwt, etc.) live in app/extensions.py and are
# initialized in the app factory. Import them from ..extensions when needed.
from . import api
from flask import jsonify, request, current_app
import tempfile
import os
import uuid
import traceback
from ..models import User, Document
from ..extensions import db
from ..rag.background import start_index_process, start_delete_process, start_file_process

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
    uploaded_file = request.files.get("file")

    # If file uploaded but no inline text, we'll read file in background and set text there.
    # Validate presence of title/text/file
    if not title and not uploaded_file:
        return jsonify({"msg": "title and/or file are required"}), 400

    # Only allow certain extensions if a file is uploaded
    allowed = {"pdf", "txt", "docx", "doc"}
    saved_path = None
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    if uploaded_file:
        orig_name = uploaded_file.filename or ""
        ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else ""
        if ext not in allowed:
            return jsonify({"msg": f"file type .{ext} not allowed"}), 400
        # save file to uploads dir with unique name
        unique_name = f"{uuid.uuid4().hex}_{orig_name}"
        saved_path = os.path.join(uploads_dir, unique_name)
        uploaded_file.save(saved_path)

    # If inline text present and no file, we will index that text
    if not text and not saved_path:
        return jsonify({"msg": "text or file required"}), 400

    d = Document(title=title, text=(text or ""))  # if file will be processed later to fill text
    if saved_path:
        d.filename = unique_name
    db.session.add(d)
    db.session.commit()

    # If a file was uploaded: start background process that reads file and indexes (updates DB)
    if saved_path:
        try:
            start_file_process(d.id, saved_path)
        except Exception:
            current_app.logger.exception("Failed to start background file processing")
            return jsonify({"msg": "uploaded but scheduling failed"}), 500
    else:
        # no file -> index the provided text in background
        try:
            start_index_process(d.id)
        except Exception:
            current_app.logger.exception("Failed to start background indexing process")

    return jsonify(d.to_dict()), 201

@api.route("/docs/<int:doc_id>", methods=["DELETE"])
def delete_doc(doc_id):
    d = Document.query.get(doc_id)
    if not d:
        return jsonify({"msg": "not found"}), 404

    # kick off vector deletion in a separate process, then delete the DB row
    try:
        start_delete_process(d.id)
    except Exception:
        current_app.logger.exception("Failed to start background vector-delete process")

    db.session.delete(d)
    db.session.commit()
    return jsonify({"msg": "deleted"}), 200

@api.route("/docs/reindex", methods=["POST"])
def reindex_docs():
    # Placeholder: trigger reindexing job (vector DB creation). Implement later.
    # Here we simply return success and accepted so UI can show progress.
    return jsonify({"status": "reindex started"}), 202

# @api.route("/audio", methods=["POST"])
# def handle_audio():
#     """
#     Accepts:
#       - multipart/form-data with "file" -> audio blob
#       - or JSON with {"audio": "<dataurl or base64>"}
#     Returns JSON: {"transcript": "...", "answer": "..."}
#     """
#     # Try multipart upload first
#     try:
#         file = request.files.get("file")
#         tmp_path = None
#         if file:
#             # save to a temp file
#             suffix = os.path.splitext(file.filename)[1] or ".webm"
#             tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
#             file.save(tmp.name)
#             tmp_path = tmp.name
#             file_size = os.path.getsize(tmp_path)
#         else:
#             data = request.get_json(silent=True) or {}
#             audio_data = data.get("audio")
#             if not audio_data:
#                 return jsonify({"msg": "no audio provided"}), 400
#             # handle data URL or plain base64
#             if audio_data.startswith("data:"):
#                 # format: data:audio/webm;base64,...
#                 try:
#                     header, b64 = audio_data.split(",", 1)
#                 except Exception:
#                     b64 = audio_data
#             else:
#                 b64 = audio_data
#             raw = base64.b64decode(b64.split("base64,")[-1])
#             tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
#             with open(tmp.name, "wb") as fh:
#                 fh.write(raw)
#             tmp_path = tmp.name
#             file_size = os.path.getsize(tmp_path)

#         # Placeholder transcription: implement real ASR here (Whisper, cloud, etc.)
#         transcript = f"(simulated) Transcription of audio ({file_size} bytes)"
#         # Placeholder RAG interaction: implement actual retrieval/reader pipeline if desired
#         answer = f"(simulated) Answer based on transcript: {transcript}"

#         # remove temp file after processing
#         try:
#             if tmp_path and os.path.exists(tmp_path):
#                 os.remove(tmp_path)
#         except Exception:
#             current_app.logger.exception("failed to remove temp audio file")

#         return jsonify({"transcript": transcript, "answer": answer}), 200

#     except Exception as exc:
#         current_app.logger.error("audio processing failed: %s", traceback.format_exc())
#         return jsonify({"msg": "processing error"}), 500
#         # Placeholder RAG interaction: implement actual retrieval/reader pipeline if desired
#         answer = f"(simulated) Answer based on transcript: {transcript}"

#         # remove temp file after processing
#         try:
#             if tmp_path and os.path.exists(tmp_path):
#                 os.remove(tmp_path)
#         except Exception:
#             current_app.logger.exception("failed to remove temp audio file")

#         return jsonify({"transcript": transcript, "answer": answer}), 200

#     except Exception as exc:
#         current_app.logger.error("audio processing failed: %s", traceback.format_exc())
#         return jsonify({"msg": "processing error"}), 500
