FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
# asyncpg needed for PostgreSQL on Render (not needed for local SQLite dev)
RUN pip install --no-cache-dir -r requirements.txt asyncpg>=0.29.0

# Copy application source
COPY . .

# Runtime environment
ENV PORT=8080

EXPOSE 8080

CMD ["python", "run.py"]
