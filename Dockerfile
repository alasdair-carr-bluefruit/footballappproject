# Level — multi-user deploy image (FastAPI + uvicorn, Postgres via DATABASE_URL).
# Serves the API and the static frontend/assets from one always-on instance.
FROM python:3.12-slim

# psycopg2-binary ships wheels, so no build toolchain is needed.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# App code (frontend/ and assets/ are served by StaticFiles; alembic.ini at root).
COPY . .
RUN pip install --upgrade pip && pip install -e ".[api]"

# Railway/Koyeb/Fly inject $PORT; default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

# Exec form + main.py reads $PORT in Python — no shell-expansion dependency
# (avoids the literal-"$PORT" crash when a platform runs the command without a shell).
CMD ["python", "main.py"]
