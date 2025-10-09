#!/bin/bash

# Ninox2Git WebApp - Deployment Script
# This script helps with the initial setup and deployment

set -e

echo "=========================================="
echo "Ninox2Git WebApp - Deployment Script"
echo "=========================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker and Docker Compose are installed${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠ .env file not found. Creating from template...${NC}"
    cp .env.example .env

    echo ""
    echo -e "${YELLOW}Please edit .env file and configure the following:${NC}"
    echo "  1. POSTGRES_PASSWORD (database password)"
    echo "  2. SECRET_KEY (generate with: openssl rand -hex 32)"
    echo "  3. JWT_SECRET_KEY (generate with: openssl rand -hex 32)"
    echo "  4. NICEGUI_STORAGE_SECRET (generate with: openssl rand -hex 32)"
    echo "  5. SMTP configuration (for email notifications)"
    echo ""

    read -p "Press Enter to open .env file for editing..."
    ${EDITOR:-nano} .env
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

echo ""

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p data/database data/logs data/keys
chmod 700 data/keys
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Check if proxy-network exists
if ! docker network inspect proxy-network &> /dev/null; then
    echo -e "${YELLOW}⚠ proxy-network does not exist${NC}"
    read -p "Do you want to create it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker network create proxy-network
        echo -e "${GREEN}✓ proxy-network created${NC}"
    else
        echo -e "${RED}Error: proxy-network is required${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ proxy-network exists${NC}"
fi

echo ""

# Build and start containers
echo "Building and starting Docker containers..."
docker-compose build --no-cache
docker-compose up -d

echo ""
echo -e "${GREEN}✓ Containers started successfully${NC}"
echo ""

# Wait for database to be ready
echo "Waiting for PostgreSQL to be ready..."
sleep 10

# Check container status
echo ""
echo "Container status:"
docker-compose ps

echo ""
echo "=========================================="
echo -e "${GREEN}Deployment completed successfully!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Configure NGINX Proxy Manager:"
echo "   - Domain: nx2git.netz-fabrik.net"
echo "   - Forward to: nx2git-webapp:8765"
echo "   - Enable SSL with Let's Encrypt"
echo ""
echo "2. Access the application:"
echo "   - URL: https://nx2git.netz-fabrik.net"
echo "   - Default admin: user500"
echo "   - Default password: Quaternion1234____"
echo ""
echo "3. IMPORTANT: Change admin password immediately!"
echo ""
echo "View logs with: docker-compose logs -f webapp"
echo "Stop application: docker-compose down"
echo "Restart application: docker-compose restart"
echo ""
