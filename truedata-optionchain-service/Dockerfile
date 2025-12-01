FROM python:3.10

WORKDIR /app

COPY . .

RUN apt-get update && \
    apt-get install -y --no-install-recommends caddy && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir -r requirements.txt && \
    chmod +x /app/start.sh

ENV PORT=10000

CMD ["./start.sh"]
