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
import textwrap
import io

logger = logging.getLogger(__name__)

# Example documents for local testing; replace with your document store loader
_SAMPLE_DOCS = [
    Document(id="1", text="Flask is a lightweight WSGI web application framework."),
    Document(id="2", text="RAG (retrieval-augmented generation) combines retrieval with a reader/generator."),
    Document(id="3", text="You can use Socket.IO to have realtime chat-like communication over WebSockets or fallbacks."),
]

# lazy default engine holder
_default_engine = None

def get_default_engine():
    """
    Return either a LangchainFaissRAG (preferred) or InMemoryRAG fallback.
    If LangchainFaissRAG is created, kick off its index build in background.
    """
    global _default_engine
    if _default_engine is None:
        try:
            from ..rag.langchain_rag import LangchainFaissRAG
            engine = LangchainFaissRAG()
            # start build in background so handler is non-blocking
            try:
                # try to pass the real Flask app object so the build runs inside app.app_context()
                try:
                    app_obj = current_app._get_current_object()
                except Exception:
                    app_obj = None
                    logger.warning("No Flask current_app available when starting Langchain build; build will abort gracefully if needed.")
                engine.start_background_build(app=app_obj)
            except Exception:
                logger.exception("Failed to start background build for LangchainFaissRAG")
            _default_engine = engine
        except Exception:
            logger.exception("Failed to initialize LangchainFaissRAG; falling back to InMemoryRAG")
            _default_engine = InMemoryRAG(_SAMPLE_DOCS)
    return _default_engine

# try to initialize AwsTranscriber if available and configured via env
_transcriber = None
_translator = None
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
        logger.info("TRANSCRIBE_S3_BUCKET not set; AwsTranscriber not initialized")
except Exception:
    logger.exception("AwsTranscriber not available; audio will use simulated transcription")

# try to initialize AwsTranslator if boto3 translate available and AWS region/creds present
try:
    from ..translate.aws_translate import AwsTranslator  # noqa: E402
    # initialize translator if AWS region is set (or creds present)
    if os.getenv("AWS_DEFAULT_REGION") or (os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")):
        _translator = AwsTranslator(
            region_name=os.getenv("AWS_DEFAULT_REGION"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        logger.info("AwsTranslator initialized")
    else:
        logger.info("AWS credentials/region not present; AwsTranslator not initialized")
except Exception:
    logger.exception("AwsTranslator not available; translation disabled")

# ensure media folder exists (app/static/media)
_media_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "media")
os.makedirs(_media_dir, exist_ok=True)

# Bedrock LLM client (optional)
_bedrock = None
try:
    from ..llm.bedrock_client import BedrockClient  # noqa: E402
    # initialize with env model id or default; region optional
    try:
        _bedrock = BedrockClient(model_id=os.getenv("BEDROCK_MODEL_ID"), region=os.getenv("AWS_DEFAULT_REGION"))
        logger.info("Bedrock client initialized (model=%s)", _bedrock.model_id)
    except Exception:
        logger.exception("Failed to initialize BedrockClient")
        _bedrock = None
except Exception:
    logger.info("Bedrock client module not available; LLM augmentation disabled")

# New: initialize TTS client if available
_tts = None
try:
    from ..llm.tts import TTSClient  # noqa: E402
    try:
        _tts = TTSClient(region=os.getenv("AWS_DEFAULT_REGION"))
        logger.info("TTS client initialized")
    except Exception:
        logger.exception("Failed to initialize TTSClient")
        _tts = None
except Exception:
    logger.info("TTS module not available; TTS disabled")

def _augment_with_bedrock(query: str, docs: list, model_max_tokens: int = 1200) -> str:
    """
    Build a robust prompt combining query + retrieved docs and call Bedrock to produce a final answer.

    Improvements over prior prompt:
      - Prefer answering from excerpts when any relevant text exists (match keywords / phrases).
      - Only use the strict apology fallback when NO excerpt is relevant.
      - Handle greetings explicitly and only as greetings.
      - Provide short examples to guide the model's behavior.
      - Instruct the model to output ONLY the final answer (no analysis / chain-of-thought).
    """
    # System instructions: concise, precise, and include behavior examples
    system = [
        "You are an assistant that MUST answer using ONLY the provided retrieved excerpts.",
        "Do not use external knowledge except to rephrase or summarize the provided excerpts.",
        "Do not hallucinate. If you cannot find supporting information in the excerpts, use the exact fallback sentence:",
        "  Sorry — I can assist only with MSME-related information based on the provided documents.",
        "Behaviors (in order):",
        "  1) If the user's message is a simple greeting (examples: 'hi', 'hello', 'hey', 'good morning'), reply exactly:",
        "     Hello — how can I help you?",
        "     and STOP.",
        "  2) Otherwise, try to find relevant excerpt(s):",
        "     - Look for exact words or close phrases from the user's query inside the excerpts.",
        "     - If at least one excerpt contains relevant information, produce a concise answer (1-3 sentences) based ONLY on those excerpts.",
        "     - When you use an excerpt, cite it inline by doc_id and chunk_index, e.g. [doc_id=5 chunk_index=2].",
        "  3) If NONE of the excerpts contain relevant information (no overlap of key terms or concepts), reply EXACTLY:",
        "     Sorry — I can assist only with MSME-related information based on the provided documents.",
        "     Do NOT add any additional text.",
        "Output requirements:",
        "  - Return only the final answer text (no internal reasoning, no diagnostics).",
        "  - Keep the answer concise and helpful.",
    ]

    # Add a couple of short examples to reduce ambiguity
    examples = [
        "EXAMPLE 1 (greeting):",
        "  User: 'hi'",
        "  Assistant: 'Hello — how can I help you?'",
        "",
        "EXAMPLE 2 (use excerpt):",
        "  User: 'How do I register a small business in state X?'",
        "  Excerpts include a paragraph describing registration steps for state X.",
        "  Assistant: Summarize the steps and cite the excerpt, e.g. 'To register in State X, follow these steps: ... [doc_id=12 chunk_index=0].'",
        "",
        "EXAMPLE 3 (no info):",
        "  User: 'What is the population of City Y?'",
        "  If no excerpt mentions City Y or population, Assistant:",
        "  'Sorry — I can assist only with MSME-related information based on the provided documents.'"
    ]

    # Build prompt with system, examples, user query, and strict context block
    parts = []
    parts.append("SYSTEM INSTRUCTIONS:")
    parts.extend(system)
    parts.append("\nGUIDING EXAMPLES:")
    parts.extend(examples)
    parts.append("\nUSER QUESTION:")
    parts.append(query)
    parts.append("\nRETRIEVED EXCERPTS (use ONLY these; numbered):")

    # include top N excerpts as strict context
    for i, d in enumerate(docs[:8]):
        meta = d.get("meta") or {}
        doc_id = meta.get("doc_id") or meta.get("id") or d.get("id")
        chunk_index = meta.get("chunk_index", None)
        text_snip = (meta.get("chunk_text") or d.get("text") or "")[:1600]
        parts.append(f"[{i+1}] doc_id={doc_id} chunk_index={chunk_index}\n{textwrap.indent(text_snip, '  ')}\n")

    parts.append("\nINSTRUCTIONS TO MODEL:")
    parts.append("  - First check if the user query is a simple greeting. If so, return the greeting response and stop.")
    parts.append("  - Otherwise, look for direct matches of important words/phrases from the user query in the excerpts above.")
    parts.append("  - If you find any supporting excerpt(s), answer concisely and cite them by doc_id and chunk_index.")
    parts.append("  - If you find NO supporting excerpt, return the exact fallback sentence (no extra text).")
    parts.append("  - Output ONLY the final answer (no analysis).")

    prompt = "\n".join(parts)

    if not _bedrock:
        raise RuntimeError("Bedrock client not configured")

    try:
        resp = _bedrock.generate(prompt, max_tokens=model_max_tokens, temperature=0.0)
        return resp.strip()
    except Exception:
        logger.exception("Bedrock generation failed")
        raise

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

    engine = get_default_engine()

    # If engine supports is_ready() and is not ready yet, use lightweight fallback to avoid blocking
    try:
        if hasattr(engine, "is_ready") and not engine.is_ready():
            logger.info("Langchain index not ready yet; using in-memory fallback for query")
            fallback = InMemoryRAG(_SAMPLE_DOCS)
            result = fallback.answer(query, top_k=int(payload.get("top_k", 5)))
        else:
            result = engine.answer(query, top_k=int(payload.get("top_k", 5)))
    except Exception:
        logger.exception("RAG answering failed")
        emit("chat_response", {"error": "internal error during retrieval"})
        return

    # Attempt LLM augmentation (Bedrock). Fall back to retrieval answer on any failure.
    final_answer = result.get("answer", "")
    try:
        if _bedrock and result.get("docs"):
            # send docs as list of dicts to the prompt builder
            docs_for_prompt = [{"id": d.id, "text": d.text, "meta": d.meta} for d in result.get("docs", [])]
            augmented = _augment_with_bedrock(query, docs_for_prompt)
            if augmented:
                final_answer = augmented
    except Exception:
        logger.exception("Augmented LLM step failed; using retrieval-only answer")

    # New: produce TTS audio and upload to storage; include audio_url in response if successful
    audio_url = None
    try:
        if _tts and final_answer:
            # prefer language hint from payload if present
            req_lang = (payload or {}).get("lang") or "en"
            # simple voice map -- customize per available voices in your region
            voice_map = {"en": "Joanna", "te": "Aditi"}
            voice = voice_map.get(req_lang, "Joanna")
            audio_bytes = _tts.synthesize(final_answer, voice=voice)
            if audio_bytes:
                storage = get_storage_client()
                # prefer S3 presigned URL if S3Storage available
                try:
                    from ..storage.s3 import S3Storage  # noqa: E402
                    is_s3 = isinstance(storage, S3Storage)
                except Exception:
                    is_s3 = False

                if is_s3:
                    # upload to dataset/tts/<uuid>.mp3 in S3 and generate presigned URL
                    key = f"dataset/tts/{uuid.uuid4().hex}.mp3"
                    bucket = os.getenv("DATASET_S3_BUCKET") or os.getenv("TRANSCRIBE_S3_BUCKET")
                    # upload via file-like object
                    storage.s3.upload_fileobj(io.BytesIO(audio_bytes), bucket, key)
                    try:
                        audio_url = storage.s3.generate_presigned_url(
                            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
                        )
                    except Exception:
                        # fallback to s3:// URI if presign fails
                        audio_url = f"s3://{bucket}/{key}"
                else:
                    # local: write into app/static/media so web client can fetch via /static/media/...
                    fname = f"{uuid.uuid4().hex}.mp3"
                    dest = os.path.join(_media_dir, fname)
                    with open(dest, "wb") as fh:
                        fh.write(audio_bytes)
                    audio_url = f"/static/media/{fname}"
    except Exception:
        logger.exception("TTS generation/upload failed; continuing without audio")

    out = {
        "answer": final_answer,
        "docs": [{"id": d.id, "text": d.text, "meta": d.meta} for d in result.get("docs", [])],
        "llm_used": _bedrock.model_id if _bedrock else None,
        "audio_url": audio_url
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

            # Attempt real transcription if transcriber is configured
            transcript = None
            input_lang = None
            if _transcriber:
                try:
                    trans_result = _transcriber.transcribe_file(saved_path)
                    if isinstance(trans_result, dict):
                        transcript = trans_result.get("text", "")
                        input_lang = trans_result.get("input_lang")
                    else:
                        transcript = trans_result or ""
                except Exception:
                    logger.exception("AwsTranscriber failed, falling back to simulated transcript")
                    transcript = None

            # fallback simulated transcript
            if not transcript:
                transcript = f"(simulated) Transcription of audio ({file_size} bytes)"
                input_lang = input_lang or None

            # If detected language is not english, translate to English for RAG/search
            transcript_en = transcript
            if input_lang:
                try:
                    # normalize primary code (e.g., "te-IN" -> "te")
                    primary = input_lang.split("-")[0].lower()
                except Exception:
                    primary = input_lang.lower()
                if primary and not primary.startswith("en"):
                    if _translator:
                        try:
                            transcript_en = _translator.translate_text(transcript, source_lang=input_lang, target_lang="en")
                        except Exception:
                            logger.exception("Translator failed; using original transcript for RAG")
                            transcript_en = transcript
                    else:
                        # translator not configured; leave transcript_en as original
                        transcript_en = transcript

            # run RAG engine on English text (transcript_en)
            engine = get_default_engine()

    # If engine supports is_ready() and is not ready yet, use lightweight fallback to avoid blocking
            try:
                if hasattr(engine, "is_ready") and not engine.is_ready():
                    logger.info("Langchain index not ready yet; using in-memory fallback for query")
                    fallback = InMemoryRAG(_SAMPLE_DOCS)
                    result = fallback.answer(transcript_en, top_k=int(payload.get("top_k", 5)))
                else:
                    result = engine.answer(transcript_en, top_k=int(payload.get("top_k", 5)))
            except Exception:
                logger.exception("RAG answering failed")
                emit("chat_response", {"error": "internal error during retrieval"})
                return

            # Attempt LLM augmentation (Bedrock). Fall back to retrieval answer on any failure.
            final_answer = result.get("answer", "")
            try:
                if _bedrock and result.get("docs"):
                    docs_for_prompt = [{"id": d.id, "text": d.text, "meta": d.meta} for d in result.get("docs", [])]
                    augmented = _augment_with_bedrock(transcript_en, docs_for_prompt)
                    if augmented:
                        final_answer = augmented
            except Exception:
                logger.exception("Augmented LLM step failed for audio; using retrieval-only answer")

            # New: synthesize TTS for audio responses (respect requested_lang if present in p)
            audio_url = None
            try:
                if _tts and final_answer:
                    req_lang = (p or {}).get("lang") or "en"
                    voice_map = {"en": "Joanna", "te": "Aditi"}
                    voice = voice_map.get(req_lang, "Joanna")
                    audio_bytes = _tts.synthesize(final_answer, voice=voice)
                    if audio_bytes:
                        storage = get_storage_client()
                        try:
                            from ..storage.s3 import S3Storage  # noqa: E402
                            is_s3 = isinstance(storage, S3Storage)
                        except Exception:
                            is_s3 = False

                        if is_s3:
                            key = f"dataset/tts/{uuid.uuid4().hex}.mp3"
                            bucket = os.getenv("DATASET_S3_BUCKET") or os.getenv("TRANSCRIBE_S3_BUCKET")
                            storage.s3.upload_fileobj(io.BytesIO(audio_bytes), bucket, key)
                            try:
                                audio_url = storage.s3.generate_presigned_url(
                                    "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
                                )
                            except Exception:
                                audio_url = f"s3://{bucket}/{key}"
                        else:
                            fname = f"{uuid.uuid4().hex}.mp3"
                            dest = os.path.join(_media_dir, fname)
                            with open(dest, "wb") as fh:
                                fh.write(audio_bytes)
                            audio_url = f"/static/media/{fname}"
            except Exception:
                logger.exception("TTS generation/upload failed for audio; continuing without audio_url")

            out = {
                "transcript": transcript,
                "transcript_en": transcript_en,
                "input_lang": input_lang,
                "answer": final_answer,
                "audio_url": audio_url,
                "docs": [{"id": d.id, "text": d.text, "meta": d.meta} for d in result.get("docs", [])],
                "llm_used": _bedrock.model_id if _bedrock else None
            }
            socketio.emit("chat_response", out, to=target_sid)
        except Exception:
            logger.exception("audio processing failed")
            socketio.emit("chat_response", {"error": "audio processing failed"}, to=target_sid)
        # keep saved file for replay; optionally implement retention/cleanup elsewhere

    socketio.start_background_task(_process_audio, payload, sid)
