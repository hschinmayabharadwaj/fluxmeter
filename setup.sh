#!/bin/bash

# Ledgerline Quick Setup Script
# This script helps you get started quickly with Ledgerline

set -e

echo "========================================="
echo "  Ledgerline Setup Script"
echo "========================================="
echo ""

# Check for required tools
echo "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

echo "✅ Docker and Docker Compose are installed"
echo ""

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY)"
    echo ""
    read -p "Press enter to continue after updating .env file..."
fi

# Check if API keys are set
if ! grep -q "sk-" .env; then
    echo "⚠️  Warning: API keys may not be set in .env file"
    echo "   The system will start but API calls will fail without valid keys."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Starting Ledgerline services..."
echo ""

# Start infrastructure services first
echo "Starting infrastructure (PostgreSQL, Redis, RabbitMQ, Qdrant)..."
docker-compose up -d postgres redis rabbitmq qdrant kong-database

echo "Waiting for services to be ready..."
sleep 10

# Run Kong migrations
echo "Running Kong migrations..."
docker-compose up kong-migration

# Start Kong
echo "Starting Kong Gateway..."
docker-compose up -d kong

# Start application services
echo "Starting application services..."
docker-compose up -d rate-limiter dlq-handler dispatcher

# Start observability stack
echo "Starting observability stack..."
docker-compose up -d prometheus grafana jaeger

echo ""
echo "========================================="
echo "  Ledgerline is starting up!"
echo "========================================="
echo ""
echo "Services are being initialized. This may take a minute..."
echo ""
echo "Service URLs:"
echo "  • Frontend Dashboard: http://localhost:3000"
echo "  • Dispatcher API: http://localhost:8000/docs"
echo "  • Rate Limiter: http://localhost:8081/health"
echo "  • DLQ Handler: http://localhost:8082/health"
echo "  • Kong Admin API: http://localhost:8001"
echo "  • RabbitMQ Management: http://localhost:15672 (guest/guest)"
echo "  • Qdrant Dashboard: http://localhost:6333/dashboard"
echo "  • Prometheus: http://localhost:9090"
echo "  • Grafana: http://localhost:3001 (admin/admin)"
echo "  • Jaeger UI: http://localhost:16686"
echo ""
echo "Run 'docker-compose logs -f' to see service logs"
echo "Run 'docker-compose ps' to check service status"
echo ""

# Wait for health checks
echo "Checking service health..."
sleep 5

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Services are running!"
else
    echo "❌ Some services may have failed to start. Check logs with: docker-compose logs"
fi

echo ""
echo "To start the frontend locally:"
echo "  cd frontend"
echo "  npm install"
echo "  npm run dev"
echo ""
echo "Happy orchestrating! 🚀"
