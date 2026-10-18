FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY scripts/ scripts/
COPY data/raw/ data/raw/

# Utilizador sem privilegios. So data/cache (SQLite da cache LLM) e logs/ precisam de
# escrita; os modelos do Hugging Face vao para a home do utilizador.
RUN useradd --create-home --uid 1000 docpilot     && mkdir -p data/cache logs     && chown -R docpilot:docpilot data/cache logs
USER docpilot

EXPOSE 8000

# O python-slim nao traz curl; o urllib da stdlib chega para um GET ao /health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3     CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"]

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
