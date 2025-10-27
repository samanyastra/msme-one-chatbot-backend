# msme-one-chatbot-backend

A lightweight Flask backend for a chat-enabled RAG (Retrieval-Augmented Generation) prototype with realtime Socket.IO, document ingestion, file->text readers, FAISS vector search, optional LangChain integration and optional Bedrock (Amazon) LLM augmentation.

This README describes development setup, architecture, APIs, workflows, tradeoffs, and troubleshooting.

---

Table of contents
- Quick start (dev)
- Environment variables
- Features & silent features
- Architecture and components
- Document ingestion & storage workflow
- Indexing & retrieval workflow
- Socket / realtime chat flow
- Audio (ASR) & Multilingual support
- REST APIs
- Background workers
- Testing and debugging
- Deployment (Docker)
- Advantages & limitations
- Security notes
- Troubleshooting & tips

---

Quick start (development)
1. Create virtual environment and install deps:
   - python -m venv .venv
   - source .venv/bin/activate
   - pip install --upgrade pip
   - pip install -r requirements.txt

2. Configure environment (example):
   - Copy `.env.example` -> `.env` and set values, or export env vars:
     FLASK_ENV=development
     DATABASE_URL=sqlite:///data.db
     SECRET_KEY=change-me
     JWT_SECRET_KEY=change-me
     DATASET_S3_BUCKET=your-bucket   # optional (use S3) or omit for local storage
     AWS_DEFAULT_REGION=ap-south-1   # optional for AWS integrations
     BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0  # optional

3. Initialize DB (Flask-Migrate):
   - flask db upgrade

4. Run development server (monkeypatched for eventlet):
   - python run.py
   - OR ./start.sh dev

5. Open UI:
   - http://localhost:5000/ui/chat

---

Environment variables (important)
- SECRET_KEY: Flask secret.
- DATABASE_URL: SQLAlchemy DB URL (default sqlite:///data.db).
- JWT_SECRET_KEY: JWT signing secret.
- AWS_ACCESS_KEY_ID: Aws account key id
- AWS_SECRET_ACCESS_KEY: Aws access key (ensure proper role available to access bedrock and s3 bucket)
- AWS_DEFAULT_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY: AWS creds for S3/Bedrock/Translate.
- DATASET_S3_BUCKET: S3 bucket for uploaded docs (optional).
- TRANSCRIBE_S3_BUCKET: fallback for audio/transcribe S3 usage.
- SENTENCE_TRANSFORMER_MODEL: optional model id for sentence-transformers.
- BEDROCK_MODEL_ID: Bedrock model id for LLM augmentation.

---

Features & silent features
- Realtime chat with Socket.IO (eventlet by default).
- Document ingestion: accepts .pdf, .txt, .docx, .doc — stored in S3 and local.
- File readers implemented for txt, pdf (PyPDF2), docx (python-docx); optional textract for .doc.
- Background processing: file->read->index runs in separate process to avoid blocking.
- Vector store:
  - FAISS-backed local store persisted under app/static/vector_store by default.
  - Optional LangChain integration for building FAISS vectorstore (lazy or background build).
- Embeddings:
  - sentence-transformers (e5 or MiniLM) used locally; deterministic fallback if missing.
- LLM augmentation:
  - Optional Bedrock client wrapper to call Anthropic/BEDROCK models for final answer refinement.
  - Strict prompt patterns to reduce hallucination and enforce using retrieved excerpts.
- Modular storage client (S3 / Local) for decoupled uploads/downloads.

Silent features:
- Graceful fallbacks (local embedding fallback, local storage when S3 not configured).
- Single-thread FAISS (faiss.omp_set_num_threads(1)) to reduce resource leaks.
- Reusable socket client UI code with welcome/language toggle.

---

Architecture & components
- Flask app factory (app.create_app).
- Extensions in app/extensions.py: db, migrate, jwt, socketio.
- RAG modules in app/rag:
  - chunker, embeddings, faiss_store, faiss_rag/langchain_rag, impl_inmemory.
- File readers in app/file_readers.
- Storage clients in app/storage: S3Storage, LocalStorage; get_storage_client() factory.
- Background workers in app/rag/background.py using multiprocessing spawn context.
- Socket handlers in app/chat/socketio_events.py handling chat_message and audio_message.
- Optional LLM wrapper under app/llm/bedrock_client.py.

---

Document ingestion & storage workflow
1. POST /api/docs accepts title + (text or file). File must be .pdf/.txt/.docx/.doc.
2. Uploaded files are stored using storage client:
   - If DATASET_S3_BUCKET configured → S3 under `dataset/<uuid>`.
   - Else local store under app/static/uploads (file:// URI).
3. DB Document record created with filename pointing to URI and empty/inline text as provided.
4. Background process (start_file_process) downloads S3 (if applies), runs file reader, writes extracted text into Document.text, then triggers indexing (start_index_process).

---

Indexing & retrieval workflow
- Indexing (background):
  - Reads Document.text, chunks via chunk_text, computes embeddings (EmbeddingProvider), upserts vectors into FaissStore (or constructs LangChain FAISS).
  - Vector metadata includes doc_id, chunk_index, chunk_text.
- Retrieval (chat time):
  - Incoming query is embedded, FaissStore queried for top_k matches, matched chunks returned with scores & metadata.
  - Optionally use LangChain retriever (if LangChain FAISS vectorstore was built/persisted and injected).
- Augmentation:
  - Retrieved chunks may be passed to Bedrock LLM with a strict prompt to produce a final augmented answer.
  - If Bedrock is unavailable or fails, the service returns retrieval-only snippet summary.

---

Socket / realtime chat flow
- Events:
  - Client emits "chat_message": { query, top_k?, lang? } — server returns "chat_response": { answer, docs, llm_used?, audio_url? }.
  - Client emits "audio_message": { audio: dataURL, audio_type, audio_len, lang? } — server decodes, optionally uploads to S3, transcribes (ASR), translates if required, runs RAG, optionally augments via LLM, synthesizes audio (TTS) and returns "chat_response".
  - Server emits "system" and "welcome" messages to clients.
- Language hint:
  - Client may send lang (e.g., 'en' or 'te') for better ASR; server transcriber uses language_code when available.
  - If no lang provided, the server may rely on auto-detection or defaults.

---

Audio (ASR) & Multilingual support — NEW
This project supports audio input (voice-to-text) from the client and can optionally return audio responses (text-to-speech). It supports multiple languages (UI default is English and Telugu) and can be extended to any language supported by your ASR/TTS provider (e.g., AWS Transcribe / Polly).

Key points
- Client-side
  - The chat UI provides a language toggle (EN / TE). This sets `window.__chat_message_language` and is sent with both text and audio messages.
  - Text messages: socket.emit('chat_message', { query: "...", lang: "en" })
  - Audio messages: socket.emit('audio_message', { audio: "<dataurl>", audio_type: "audio/webm", audio_len: N, lang: "te" })
  - The UI includes an option to enable/disable audio responses (TTS) if desired.

- Server-side
  - _on_audio_message decodes the incoming data URL, saves temporary audio, and calls the configured transcriber.
  - If `lang` is provided in the payload, it is passed to the transcriber (e.g., 'en' -> 'en-US', 'te' -> 'te-IN') to improve ASR accuracy.
  - The transcribed text is optionally translated to English (if non-English) before retrieval if the retriever/reader expects English.
  - After retrieval + (optional) LLM augmentation, the final answer can be synthesized to audio (TTS) and uploaded to storage; the API returns an `audio_url` for playback.

- Providers & environment variables
  - AWS Transcribe: set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION, and TRANSCRIBE_S3_BUCKET (optional) for temporary audio storage.
    - Pass language codes like 'en-US', 'te-IN' to the transcriber where supported.
  - AWS Polly (TTS): used for audio responses. Configure voice per language via a simple mapping (e.g., 'en' -> Joanna, 'te' -> Aditi or another supported voice).
  - Bedrock / LLM: used for answer augmentation (not for ASR/TTS).
  - STORAGE: S3 (preferred) or local filesystem via the storage client.

- Language mapping (recommendation)
  - UI codes: 'en', 'te' (extendable)
  - Provider locale mapping (server-side):
    - 'en' -> 'en-US'
    - 'te' -> 'te-IN'
  - Add new languages by extending the UI and server mapping.

- Supported audio formats
  - Client records and sends audio as data URLs (webm/ogg/mp3). Server accepts audio_type and chooses appropriate file extension for temporary storage and provider upload.
  - When sending to AWS Transcribe or other ASR, ensure the format is compatible (e.g., 16k/48k sampling rate).

- Example flow (Telugu voice message)
  1. User selects "TE" in UI and records audio.
  2. Client emits audio_message with lang: 'te'.
  3. Server saves audio, calls transcriber with language_code='te-IN'.
  4. Transcribed Telugu text is optionally translated to English for retrieval.
  5. RAG returns top chunks; optionally LLM augments answer.
  6. If TTS enabled, server synthesizes response using a Telugu-capable voice and returns audio_url in chat_response.

- Costs & latency
  - ASR and TTS calls incur cloud costs and add latency. Use toggles to control TTS generation and limit LLM calls to control expenses.
  - For production, queue-intensive jobs and use worker pools.

- Privacy & retention
  - Audio files contain PII. Configure S3 lifecycle/retention or local cleanup. Limit storage duration for generated TTS audio.

---

REST APIs
- GET / -> health/status
- GET /api/users -> list users
- POST /auth/register -> create user
- POST /auth/login -> login (JWT)
- GET /api/docs -> list documents
- POST /api/docs -> upload doc (title required, text or file required)
- DELETE /api/docs/<id> -> delete doc (schedules vector deletion)
- POST /api/docs/reindex -> trigger reindex (placeholder — implement reindex job to rebuild LangChain/FAISS)

---

Background workers & concurrency
- Background tasks are spawned using multiprocessing.get_context("spawn").Process to avoid resource_tracker warnings.
- Background tasks:
  - start_file_process(doc_id, file_uri): downloads file (if s3://), reads text, updates DB, triggers indexing.
  - start_index_process(doc_id): embed chunks and upsert to FAISS.
  - start_delete_process(doc_id): delete vectors from FAISS.
- For production, prefer a worker queue (Celery/RQ) for robustness.

---

Testing & debugging
- Logs: Flask logs, worker logs (background processes print exceptions). Check console for error traces.
- Common issues:
  - "Working outside of application context": ensure background builder uses app.app_context(), use start_background_build(app).
  - FAISS resource warnings: set faiss.omp_set_num_threads(1) and use spawn context.
  - Model imports (LangChain): versions vary — check compatibility and adjust _import_langchain.
- Local validation:
  - Upload a small .txt, check that DB record created, background process reads text (check logs), and vector store updated (faiss.index file exists).

---

Deployment (Docker)
- Dockerfile included. Build:
  - docker build -t msme-chat-backend .
  - docker run -p 5000:5000 --env-file .env msme-chat-backend
- Configure env vars for AWS, DB, and Bedrock in production.
- Consider mounting persistent storage for FAISS or persist the LangChain FAISS to S3 for multi-host deployments.

---

Advantages
- Lightweight, modular, and easy to extend.
- Local-first: works offline with sentence-transformers + FAISS.
- Flexible storage: S3 or local fallback.
- Clear separation: ingestion, reading, indexing, retrieval, augmentation.

Limitations / Disadvantages
- Single-host FAISS isn't horizontally scalable.
- Local sentence-transformers may require GPU for large loads.
- LangChain + Bedrock integration can add heavy dependencies and cold-start delays (embeddings/models).
- Background processes are simple; not a production-grade worker queue. This can be achieved by the celery and rabbitmq processes. 

---

Security & operational notes
- Never commit secrets. Use environment variables or a secrets manager.
- Sanitize uploaded files and set size limits in production.
- S3 uploads must be secured with appropriate IAM policies.
- Rate-limit LLM/Bedrock calls to control costs.
- Use HTTPS and proper CORS in production.

---

Troubleshooting tips (quick)
- No chat messages: ensure eventlet is monkey-patched (run.py applies monkey_patch).
- Socket connects but no welcome: client now renders local welcome; server welcome emitted to SID on connect — check server logs.
- FAISS errors: ensure faiss-cpu installed in the same environment; check permissions on vector_store path.
- LangChain import errors: verify langchain / langchain-community / transformers versions; adjust _import_langchain shim.
- Bedrock failures: ensure AWS credentials and model id are correct and the account has Bedrock access.
- If ASR returns poor transcripts:
  - Ensure correct language_code mapping (e.g., 'te' -> 'te-IN').
  - Use short, clean audio and recommended sampling rates.
  - Check provider logs and IAM permissions.
- If audio_url is missing:
  - Verify TTS client was initialized and storage upload succeeded (S3 or local media path).
- If you see "No Flask application context" when building indexes, ensure background builds receive an app context.

---

Contact / References
- Repo owner: Satish Madem.
- Useful docs:
  - Flask, Flask-SocketIO, FAISS, sentence-transformers, LangChain, AWS Transcribe/Polly, Bedrock docs.