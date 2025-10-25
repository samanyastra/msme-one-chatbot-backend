# msme-one-chatbot-backend

A lightweight Flask backend for a chat-enabled RAG prototype with realtime Socket.IO, simple auth, and a small UI. Intended for local development and as a starting point for integrating real retrieval/reader components.

## Key features
- Flask app factory pattern
- Realtime chat over Socket.IO (Flask-SocketIO with eventlet)
- Simple in-memory RAG implementation for local testing
- User model with password hashing and JWT login
- REST endpoint to list users (/api/users)
- Basic UI templates including a chat page (/ui/chat)
- Alembic / Flask-Migrate database migrations
- Dockerfile for containerized runs

## Quick start (local)
1. Create a virtualenv and install deps:
    python -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt

2. Configure environment (example in .env.example):
    export FLASK_ENV=development
    export DATABASE_URL=sqlite:///data.db
    export SECRET_KEY=change-me
    export JWT_SECRET_KEY=change-me
    export FLASK_APP=run.py

3. Initialize or upgrade the database:
    flask db upgrade

4. Run locally (development):
    python run.py
    or use helper script:
    ./start.sh dev

5. Open the chat UI:
    http://localhost:5000/ui/chat

## Docker
Build and run:
  docker build -t msme-chat-backend .
  docker run -p 5000:5000 --env-file .env.example msme-chat-backend

The container runs gunicorn with eventlet workers as configured in the Dockerfile.

## API & Auth
- GET / -> health/status (JSON)
- GET /api/users -> list users
- POST /auth/register -> register (JSON or form)
- POST /auth/login -> login (returns JWT access token)

Socket events (client-side chat):
- emit "chat_message" with payload { query, top_k?, room? }
- receive "chat_response" with { answer, docs } and "system" messages

Chat UI client lives at app/static/js/chat.js and template at /ui/chat.

## RAG implementation
- app/rag/impl_inmemory.py provides InMemoryRetriever, SimpleReader and InMemoryRAG for quick testing.
- Replace or extend these components to plug in real vector DBs / embedding models for production.

## Migrations
Alembic scripts are under migrations/. Use Flask-Migrate commands (flask db revision / upgrade) as the app factory exposes DB via app factory.

## Notes & development tips
- Socket.IO is configured to use eventlet; install eventlet (requirements.txt includes it).
- For production, swap the in-memory RAG with a persistent index and secure secrets (do not use plaintext env defaults).
- The Dockerfile exposes port 5000 and launches gunicorn with eventlet workers.

## License
See repository for license information.