FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY triage/ ./triage/
COPY tests/ ./tests/
COPY evals/ ./evals/
COPY fixtures/ ./fixtures/
COPY scripts/ ./scripts/
COPY worker.py web.py ./

# Overridden per service in docker-compose.yml.
CMD ["python", "worker.py"]
