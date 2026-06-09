# Dockerfile — AI E-Commerce Operations Brain

FROM python:3.13-slim

WORKDIR /app

# System deps: gcc for compilation, libpq-dev for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY agents/        agents/
COPY api/           api/
COPY data/          data/
COPY evaluation/    evaluation/
COPY graph/         graph/
COPY memory/        memory/
COPY observability/ observability/
COPY schemas/       schemas/
COPY tools/         tools/
COPY main.py        main.py

# FastAPI port
EXPOSE 8000

# Default: run FastAPI via uvicorn
CMD ["uvicorn", "api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
