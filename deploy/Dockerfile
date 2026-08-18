FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV KUBEWEEKLY_SOURCES_PATH=/etc/kubeweekly/sources.yaml
ENV KUBEWEEKLY_DB_PATH=/data/kubeweekly.db
ENV KUBEWEEKLY_OUTPUT_DIR=/data/output

ENTRYPOINT ["python", "-m", "kubeweekly.main"]
