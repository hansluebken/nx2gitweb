FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Node.js for ninox-dev-cli
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    graphviz \
    gnupg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 18+ (required for ninox-dev-cli)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy tools
COPY tools/ ./tools/

# Copy package.json for ninox-dev-cli
COPY package.json package-lock.json ./

# Install npm dependencies (ninox-dev-cli)
RUN npm install --production

# Create necessary directories
RUN mkdir -p /app/data/keys /app/data/logs /app/data/ninox-cli /app/data/debug

# Create non-root user
RUN useradd -m -u 1000 nx2git && \
    chown -R nx2git:nx2git /app

USER nx2git

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8765/ || exit 1

# Expose port
EXPOSE 8765

# Run the application
CMD ["python", "-m", "app.main"]
