# Mokara api + worker image (one image, two Cloud Run services).
# api:    default CMD (uvicorn on $PORT)
# worker: deploy with `--command python --args worker.py`
#
# python:3.13-slim, not 3.14: numpy==2.2.6 (and friends) ship no cp314
# wheels, and the slim image has no compiler — a 3.14 base fails at pip
# install. The local venv runs 3.14 only because pip compiled numpy from
# source on the dev Mac; 3.13 has wheels for every pin.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Non-root; --chown sets ownership in the same layer (a post-copy chown -R
# would duplicate the whole tree). /app stays writable for the rotating log
# files and the local pdf_cache fallback (prod uses PDF_STORAGE_BACKEND=gcs).
RUN useradd --create-home appuser
COPY --chown=appuser:appuser . .
USER appuser

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
