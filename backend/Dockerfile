FROM python:3.11-slim

WORKDIR /app

# Create non-root user (required by Hugging Face Spaces)
RUN useradd -m -u 1000 user

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure app directory is writable for SQLite fallback if DATABASE_URL is not set
RUN chown -R user:user /app

USER user

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
