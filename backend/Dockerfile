# 1. Use a slim Python base image
FROM python:3.10-slim

# 2. Install system dependencies: Tesseract, Poppler, build tools
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      libtesseract-dev \
      poppler-utils \
      build-essential \
 && rm -rf /var/lib/apt/lists/*

# 3. Create and set the working directory
WORKDIR /app

# 4. Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy your application code
COPY . .

# 6. Expose port 8000 for Uvicorn
EXPOSE 8001

# 7. Set an environment variable for pytesseract (optional)
ENV TESSERACT_CMD=/usr/bin/tesseract

# 8. Default command: run Uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]