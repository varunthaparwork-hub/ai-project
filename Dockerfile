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
COPY data/          data/
COPY evaluation/    evaluation/
COPY graph/         graph/
COPY memory/        memory/
COPY observability/ observability/
COPY schemas/       schemas/
COPY tools/         tools/
COPY main.py        main.py

# Streamlit port
EXPOSE 8501

# Default: run Streamlit UI
CMD ["streamlit", "run", "streamlit_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
