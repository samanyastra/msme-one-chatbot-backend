#!/usr/bin/env bash
# start.sh — local helpers to run the app with eventlet
set -e

# ensure virtualenv activated or dependencies installed
export FLASK_ENV=${FLASK_ENV:-development}
export PORT=${PORT:-5000}
export WEB_CONCURRENCY=${WEB_CONCURRENCY:-1}

echo "Options:"
echo "  1) dev : python run.py (uses socketio.run -> eventlet if installed)"
echo "  2) gunicorn : gunicorn -k eventlet -w \$WEB_CONCURRENCY run:app -b 0.0.0.0:\$PORT"
echo "  3) direct eventlet WSGI : eventlet.wsgi.server(...)"

mode="${1:-dev}"

if [ "$mode" = "dev" ]; then
  echo "Starting development server: python run.py"
  python run.py
elif [ "$mode" = "gunicorn" ]; then
  echo "Starting gunicorn with eventlet workers"
  exec gunicorn -k eventlet -w "$WEB_CONCURRENCY" run:app -b 0.0.0.0:"$PORT"
elif [ "$mode" = "eventlet" ]; then
  echo "Starting direct eventlet WSGI server"
  python - <<PY
import eventlet, os
from app import create_app
app = create_app()
listener = eventlet.listen(("0.0.0.0", int(os.environ.get("PORT", 5000))))
print("Listening on 0.0.0.0:%s" % os.environ.get("PORT", 5000))
eventlet.wsgi.server(listener, app)
PY
else
  echo "Unknown mode: $mode"
  exit 2
fi
