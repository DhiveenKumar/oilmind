FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim AS production
WORKDIR /app
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV BACKEND_URL=http://localhost:8000
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY corpus/ ./corpus/
EXPOSE 8000
EXPOSE 8501
COPY start.sh .
RUN chmod +x start.sh
CMD ["./start.sh"]
