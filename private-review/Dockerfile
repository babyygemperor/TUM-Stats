FROM python:3.11-slim

WORKDIR /app

COPY private-review/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY private-review/app.py /app/review_app.py
COPY private-review/templates /app/templates

EXPOSE 9981

CMD ["gunicorn", "--bind", "0.0.0.0:9981", "--workers", "2", "--threads", "4", "--timeout", "90", "review_app:app"]
