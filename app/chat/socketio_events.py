from flask import current_app, request
from ..extensions import socketio
from ..rag import InMemoryRAG, Document
from flask_socketio import emit, join_room, leave_room
import time
import logging
import base64
import tempfile
import os
import uuid

logger = logging.getLogger(__name__)

# Example documents for local testing; replace with your document store loader
_SAMPLE_DOCS = [
    Document(id="1", text="Flask is a lightweight WSGI web application framework."),
    Document(id="2", text="RAG (retrieval-augmented generation) combines retrieval with a reader/generator."),
    Document(id="3", text="You can use Socket.IO to have realtime chat-like communication over WebSockets or fallbacks."),
]

_default_engine = InMemoryRAG(_SAMPLE_DOCS)

# try to import AwsTranscriber if available and configured
_transcriber = None
try:
    from ..transcribe.aws_transcribe import AwsTranscriber  # noqa: E402
    s3_bucket = os.getenv("TRANSCRIBE_S3_BUCKET")
    if s3_bucket:
        _transcriber = AwsTranscriber(
            s3_bucket=s3_bucket,
            region_name=os.getenv("AWS_DEFAULT_REGION"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        logger.info("AwsTranscriber initialized using bucket %s", s3_bucket)
    else:
        logger.info("No TRANSCRIBE_S3_BUCKET set; AwsTranscriber not initialized")
except Exception:
    logger.exception("AwsTranscriber not available; will fallback to simulated transcripts")

# ensure media folder exists (app/static/media)
_media_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "media")
os.makedirs(_media_dir, exist_ok=True)

@socketio.on("connect")
def _on_connect():
    sid = getattr(current_app, "socketio_sid", None)
    logger.info(f"Client connected: {request.sid} from {request.remote_addr}")
    emit("system", {"msg": f"connected as {request.sid}"})

@socketio.on("disconnect")
def _on_disconnect():
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on("chat_message")
def _on_chat_message(payload):
    """
    payload expected: {"query": "...", "top_k": 3, "room": optional}
    or {"audio": dataURL, "audio_type": "...", "audio_len": ...}
    Emits -> "chat_response" : {"answer": str, "docs": [{id, text, meta}]}
    """
    payload = payload or {}
    query = payload.get("query", "")
    audio_data = payload.get("audio")

    # simulate processing delay to test simultaneous users
    time.sleep(1)

    if audio_data:
        # simple handling: do not decode heavy audio; simulate transcription
        size = payload.get("audio_len", None)
        # If data URL, estimate seconds by size roughly or just report size
        answer = f"(simulated) Transcribed audio received. size={size} bytes"
        out = {"answer": answer, "docs": []}
        emit("chat_response", out)
        return

    if not query:
        emit("chat_response", {"error": "empty query"})
        return

    # run RAG pipeline (sync). Replace with async/long running job if needed.
    result = _default_engine.answer(query, top_k=int(payload.get("top_k", 5)))
    answer = result.get("answer", "")
    docs = result.get("docs", [])  # list of Document

    out = {
        "answer": answer,
        "docs": [{"id": d.id, "text": d.text, "meta": d.meta} for d in docs],
    }

    emit("chat_response", out)

@socketio.on("audio_message")
def _on_audio_message(payload):
    """
    payload expected: {"audio": "data:...;base64,...", "audio_type": "...", "audio_len": int}
    Offload processing via start_background_task and emit 'chat_response' to the origin SID.
    """
    sid = request.sid if request else None
    if not payload or not payload.get("audio"):
        emit("chat_response", {"error": "no audio provided"}, to=sid)
        return

    def _process_audio(p, target_sid):
        saved_path = None
        try:
            audio_data = p.get("audio")
            # decode data URL or base64
            if isinstance(audio_data, str) and audio_data.startswith("data:"):
                try:
                    header, b64 = audio_data.split(",", 1)
                except Exception:
                    b64 = audio_data
            else:
                b64 = audio_data
            raw = base64.b64decode(b64.split("base64,")[-1])

            # choose extension from provided audio_type if possible
            audio_type = p.get("audio_type", "") or ""
            ext = ".webm"
            if "ogg" in audio_type or "oga" in audio_type:
                ext = ".ogg"
            elif "wav" in audio_type:
                ext = ".wav"
            elif "mp3" in audio_type or "mpeg" in audio_type:
                ext = ".mp3"

            # unique filename saved for replay
            filename = f"{uuid.uuid4().hex}{ext}"
            saved_path = os.path.join(_media_dir, filename)
            with open(saved_path, "wb") as fh:
                fh.write(raw)

            public_url = f"/static/media/{filename}"
            file_size = os.path.getsize(saved_path)

            # Use real transcriber if available
            transcript = None
            if _transcriber:
                try:
                    transcript = _transcriber.transcribe_file(saved_path)
                except Exception:
                    logger.exception("AwsTranscriber failed, falling back to simulated")
                    transcript = None

            # fallback simulated transcript
            if not transcript:
                transcript = f"(simulated) Transcription of audio ({file_size} bytes)"

            # run RAG engine on transcript
            result = _default_engine.answer(transcript, top_k=3)
            answer = f"(simulated) Answer based on transcript: {transcript}\n\n{result.get('answer','')}"
            out = {
                "transcript": transcript,
                "answer": answer,
                "audio_url": public_url,
                "docs": [{"id": d.id, "text": d.text, "meta": d.meta} for d in result.get("docs", [])]
            }
            socketio.emit("chat_response", out, to=target_sid)
        except Exception:
            logger.exception("audio processing failed")
            socketio.emit("chat_response", {"error": "audio processing failed"}, to=target_sid)
        # keep saved file for replay; optionally implement retention/cleanup elsewhere

    socketio.start_background_task(_process_audio, payload, sid)
