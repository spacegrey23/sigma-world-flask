FROM python:3.11-slim

# Instalacja zależności systemowych potrzebnych do kompilacji psycopg2
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Port domyślny dla Render
EXPOSE 8080

ENV PORT=8080

CMD ["python", "app.py"]
