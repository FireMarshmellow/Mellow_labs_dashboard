FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/finance.db \
    UPLOADS_DIR=/data/uploads \
    PORT=5000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/uploads

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "server:app"]
