# VARUNA AI backend, built from the repo root so the trained models and the
# explainability packages come along (backend/Dockerfile only ships the API).
#
# Port 7860 and the layout below suit Hugging Face Spaces (Docker SDK); any
# container host works — see docs/deployment.md.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # SQLite lives on the writable ephemeral disk, not in the image.
    DATABASE_URL=sqlite:////tmp/varuna.db \
    GEO_DATA_DIR=/app/data/geo \
    PYTHONPATH=/app:/app/backend

WORKDIR /app

# CPU-only torch: the default wheels bundle CUDA and are several GB.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Paths inside the code resolve relative to the repo root, so keep the layout.
COPY backend/app backend/app
COPY ai_models ai_models
COPY explainability explainability
COPY config config
COPY data/geo data/geo

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/api/v1/health')"

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "7860"]
