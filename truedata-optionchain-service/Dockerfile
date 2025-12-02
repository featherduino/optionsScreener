FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build deps only if needed by requirements
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Expose backend port (for local clarity; platform may override)
EXPOSE 8000

# Backend-only start command (no proxy/streamlit)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
