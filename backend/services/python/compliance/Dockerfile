FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8085 8086

CMD ["sh", "-c", "uvicorn gdpr:app --host 0.0.0.0 --port 8085 & uvicorn eeoc:app --host 0.0.0.0 --port 8086 & wait"]
