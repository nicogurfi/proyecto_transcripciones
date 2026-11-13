FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MODELS_DIR=/models \
    DB_PATH=/data/copiloto.db \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

COPY requirements.txt requirements-ml.txt ./
RUN pip install -r requirements.txt \
 && (pip install -r requirements-ml.txt || echo "AVISO: fastembed no disponible, se usará el fallback por hashing")

# Se hornea el modelo de embeddings en la imagen para que el runtime funcione offline.
# Capa separada del código: no se vuelve a descargar en cada cambio.
COPY app/__init__.py app/config.py app/text.py app/
COPY app/knowledge/__init__.py app/knowledge/embeddings.py app/knowledge/
RUN python -m app.knowledge.embeddings --download \
 || echo "AVISO: no se pudo descargar el modelo; se usará el fallback por hashing"

ENV HF_HUB_OFFLINE=1

COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 copiloto \
 && mkdir -p /data \
 && chown -R copiloto /data /models
USER copiloto

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=40s --retries=20 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
