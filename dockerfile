FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for WeasyPrint
RUN apt-get update && apt-get install -y \
    build-essential \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libpq-dev \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy the application code
COPY . .

# Expose the port
EXPOSE 5000

# Command to run the application
CMD ["gunicorn", "--timeout", "60", "--workers", "2", "--bind", "0.0.0.0:5000", "runserver:app"]
