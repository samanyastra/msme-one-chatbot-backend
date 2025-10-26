from flask import current_app, request
from ..extensions import socketio
from ..rag import InMemoryRAG, Document
from flask_socketio import emit, join_room, leave_room
from typing import List
import time
import logging

logger = logging.getLogger(__name__)

# Example documents for local testing; replace with your document store loader
_SAMPLE_DOCS = [
    Document(id="1", text="Flask is a lightweight WSGI web application framework."),
    Document(id="2", text="RAG (retrieval-augmented generation) combines retrieval with a reader/generator."),
    Document(id="3", text="You can use Socket.IO to have realtime chat-like communication over WebSockets or fallbacks."),
]

# Create a default engine instance. In production you may create per-app engine and attach to app context.
_default_engine = InMemoryRAG(_SAMPLE_DOCS)

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
    Emits -> "chat_response" : {"answer": str, "docs": [{id, text, meta}]}
    """
    query = (payload or {}).get("query", "")
    top_k = int((payload or {}).get("top_k", 5))
    room = (payload or {}).get("room")
    if not query:
        emit("chat_response", {"error": "empty query"})
        return

    # simulate processing delay to test simultaneous users
    time.sleep(1)

    # run RAG pipeline (sync). Replace with async/long running job if needed.
    result = _default_engine.answer(query, top_k=top_k)
    answer = result.get("answer", "")
    docs = result.get("docs", [])  # list of Document

    out = {
        "answer": answer,
        "docs": [{"id": d.id, "text": d.text, "meta": d.meta} for d in docs],
    }

    if room:
        emit("chat_response", out, room=room)
    else:
        emit("chat_response", out)
