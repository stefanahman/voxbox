#!/bin/bash
#
# VoxBox Setup Script
# Quick setup for local development and testing
#

set -e

echo "========================================="
echo "VoxBox Setup"
echo "========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from env.example..."
    cp env.example .env
    echo "✓ Created .env file"
    echo ""
    echo "⚠️  Please edit .env and add your API keys:"
    echo "   - GEMINI_API_KEY (required)"
    echo "   - TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (optional)"
    echo "   - DROPBOX_APP_KEY and DROPBOX_APP_SECRET (for Dropbox mode)"
    echo ""
    read -p "Press Enter to continue after editing .env..."
else
    echo "✓ .env file already exists"
fi

# Create data directories
echo ""
echo "Creating data directories..."
mkdir -p data/Inbox
mkdir -p data/Outbox
mkdir -p data/Archive
mkdir -p data/Logs
mkdir -p data/tokens
mkdir -p data/temp
chmod 700 data/tokens
echo "✓ Data directories created"

# Check if Docker is installed
echo ""
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi
echo "✓ Docker is installed"

# Check if Docker Compose is installed
if ! docker compose version &> /dev/null && ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi
echo "✓ Docker Compose is installed"

# Build the Docker image
echo ""
echo "Building Docker image..."
docker compose build
echo "✓ Docker image built"

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "To start VoxBox:"
echo "  docker compose up -d        # Start in background"
echo "  docker compose up           # Start with logs"
echo ""
echo "For local mode (development):"
echo "  1. Ensure MODE=local in .env"
echo "  2. Add .txt files with YouTube URLs to data/Inbox/"
echo "  3. Check output in data/Outbox/"
echo ""
echo "For Dropbox mode:"
echo "  1. Ensure MODE=dropbox in .env"
echo "  2. Start service and visit http://localhost:8080"
echo "  3. Complete OAuth authorization"
echo ""
echo "View logs:"
echo "  docker compose logs -f"
echo ""
echo "Stop service:"
echo "  docker compose down"
echo ""

