#!/bin/bash

# Ninox2Git WebApp - Quick Start Script

echo "╔═══════════════════════════════════════╗"
echo "║   Ninox2Git WebApp - Quick Start      ║"
echo "╚═══════════════════════════════════════╝"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please configure SMTP settings first:"
    echo "  nano .env"
    echo ""
    echo "Update these lines:"
    echo "  SMTP_USER=ihre-email@gmail.com"
    echo "  SMTP_PASSWORD=ihr-google-app-passwort"
    exit 1
fi

# Create directories
echo "📁 Creating directories..."
mkdir -p data/database data/logs data/keys backups
chmod 700 data/keys
chmod 600 .env

# Check if proxy-network exists
if ! docker network inspect proxy-network &> /dev/null; then
    echo "❌ Error: proxy-network does not exist"
    echo "Creating proxy-network..."
    docker network create proxy-network
fi

# Start containers
echo "🚀 Starting containers..."
docker-compose up -d

# Wait for services
echo "⏳ Waiting for services to start..."
sleep 10

# Show status
echo ""
echo "✅ Container Status:"
docker-compose ps

echo ""
echo "📋 Logs (last 20 lines):"
docker-compose logs --tail=20 webapp

echo ""
echo "╔═══════════════════════════════════════╗"
echo "║          Setup Complete!              ║"
echo "╚═══════════════════════════════════════╝"
echo ""
echo "🌐 Access: https://nx2git.netz-fabrik.net"
echo "👤 Username: user500"
echo "🔑 Password: Quaternion1234____"
echo ""
echo "⚠️  WICHTIG: Passwort nach Login ändern!"
echo ""
echo "📖 Vollständige Anleitung: cat DEPLOYMENT_GUIDE.md"
echo "📊 Logs anzeigen: docker-compose logs -f webapp"
echo "🛑 Stoppen: docker-compose down"
echo ""
