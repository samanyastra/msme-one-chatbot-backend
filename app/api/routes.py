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
from ..storage import get_storage_client

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
    # Title may be provided or inferred from filename; we'll require a title (filename can provide it)
    title = data.get("title") or (request.files.get("file") and request.files["file"].filename)
    text = data.get("text")
    uploaded_file = request.files.get("file")

    # Ensure title exists (either explicitly or via uploaded filename)
    if not title:
        return jsonify({"msg": "title is required (provide 'title' or upload a file with a filename)"}), 400

    # Only allow certain extensions if a file is uploaded
    allowed = {"pdf", "txt", "docx", "doc"}
    saved_uri = None

    if uploaded_file:
        orig_name = uploaded_file.filename or ""
        ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else ""
        if ext not in allowed:
            return jsonify({"msg": f"Unsupported file type '.{ext}'. Allowed types: {', '.join(sorted(allowed))}"}), 400

        unique_name = f"{uuid.uuid4().hex}_{orig_name}"
        key = f"dataset/{unique_name}"

        # use abstracted storage client to upload (may return s3://... or file://...)
        storage = get_storage_client()
        # pass bucket only if storage implementation uses it; get_storage_client handles defaults
        bucket = os.getenv("DATASET_S3_BUCKET") or os.getenv("TRANSCRIBE_S3_BUCKET")
        try:
            # upload_fileobj returns a URI on success (s3://... or file://...)
            saved_uri = storage.upload_fileobj(uploaded_file.stream, bucket, key)
        except Exception as e:
            current_app.logger.exception("Storage upload failed for %s: %s", orig_name, e)
            # include a helpful error message for admins
            return jsonify({"msg": "Failed to upload file to storage. Check storage configuration and logs."}), 500

    # Require at least one of text or file
    if not text and not saved_uri:
        return jsonify({"msg": "Provide either 'text' (the document content) or upload a supported file (.pdf, .txt, .docx, .doc)."}), 400

    # persist document (text may be empty if file will be processed)
    d = Document(title=title, text=(text or ""))
    if saved_uri:
        d.filename = saved_uri  # store URI (s3://... or file://...)
    db.session.add(d)
    db.session.commit()

    # If a file was uploaded: start background process that reads file and indexes (updates DB)
    if saved_uri:
        try:
            start_file_process(d.id, saved_uri)
        except Exception:
            current_app.logger.exception("Failed to start background file processing for doc_id=%s", d.id)
            return jsonify({"msg": "File saved but scheduling background processing failed. See server logs."}), 500
    else:
        # no file -> index the provided text in background
        try:
            start_index_process(d.id)
        except Exception:
            current_app.logger.exception("Failed to start background indexing process for doc_id=%s", d.id)
            # still return created but warn
            return jsonify({"msg": "Document created but indexing could not be scheduled. See server logs."}), 202

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
#                 os.remove(tmp_path)
#         except Exception:
#             current_app.logger.exception("failed to remove temp audio file")

#         return jsonify({"transcript": transcript, "answer": answer}), 200

#     except Exception as exc:
#         current_app.logger.error("audio processing failed: %s", traceback.format_exc())
#         return jsonify({"msg": "processing error"}), 500
