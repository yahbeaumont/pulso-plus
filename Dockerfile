FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 PULSO_PUBLIC_DEPLOY=1 \
    PORT=3000 PULSO_INTERNAL_PORT=8502

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx-light gettext-base tesseract-ocr tesseract-ocr-por poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 pulso

WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY app.py THIRD_PARTY_NOTICES.md artifact-manifest.json ./
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY static/ ./static/
COPY .streamlit/ ./.streamlit/
COPY deploy/ ./deploy/
COPY public/ ./public/
RUN python deploy/verify_artifact.py \
    && python -m compileall -q app.py src deploy/verify_artifact.py \
    && chmod 755 deploy/start.sh \
    && chown -R pulso:pulso /app

USER pulso
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','3000')+'/_stcore/health',timeout=4)" || exit 1
CMD ["bash", "deploy/start.sh"]
