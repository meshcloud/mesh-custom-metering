#!/bin/bash

set -e

PLATFORM=${1:-"tencent"}

echo "======================================"
echo "Testing Platform: $PLATFORM"
echo "======================================"

echo ""
echo "1. Starting mock services..."
docker-compose up -d meshstack-mock ${PLATFORM}-mock loki

echo ""
echo "2. Waiting for services to be healthy..."
sleep 10

echo ""
echo "3. Starting $PLATFORM platform container..."
docker-compose --profile $PLATFORM up -d ${PLATFORM}-platform

echo ""
echo "4. Checking logs for platform execution..."
sleep 5
docker-compose logs ${PLATFORM}-platform

echo ""
echo "5. Checking if reports were submitted to meshStack..."
curl -s http://localhost:5000/api/debug/reports | jq '.'

echo ""
echo "======================================"
echo "Test Summary for $PLATFORM"
echo "======================================"
docker-compose ps

echo ""
echo "To view Grafana dashboard: http://localhost:3000"
echo "To stop all services: docker-compose down"
