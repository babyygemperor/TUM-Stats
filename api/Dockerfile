FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY api /app/api
COPY upload/__init__.py upload/ocr.py upload/email_service.py /app/upload/

EXPOSE 6655

CMD ["gunicorn", "--bind", "0.0.0.0:6655", "--workers", "2", "--threads", "4", "--timeout", "90", "api.app:app"]
