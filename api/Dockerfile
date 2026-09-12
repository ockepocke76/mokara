# Mokara api + worker image (one image, two Cloud Run services).
# api:    default CMD (uvicorn on $PORT)
# worker: deploy with `--command python --args worker.py`
#
# python:3.14-slim matches the version the pinned requirements are
# validated against locally (api/.venv).
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root; /app stays writable for the rotating log files and the local
# pdf_cache fallback (prod uses PDF_STORAGE_BACKEND=gcs).
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
