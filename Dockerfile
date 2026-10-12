FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# Run as non-root (least privilege)
RUN useradd -m appuser && mkdir /data && chown appuser /data
USER appuser
ENV TRIAGE_DB_PATH=/data/triage.db TRIAGE_AUDIT_LOG=/data/audit.log
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
