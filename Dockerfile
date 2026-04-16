FROM python:3.11-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install ruff semgrep || true

COPY . .
RUN mkdir -p data

EXPOSE 5001

CMD ["python3", "app.py"]
