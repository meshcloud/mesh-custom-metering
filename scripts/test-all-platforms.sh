#!/bin/bash

set -e

PLATFORMS=("tencent" "ionos" "stackit" "ovh")

echo "======================================"
echo "Testing All Platforms"
echo "======================================"

echo ""
echo "1. Starting all mock services..."
docker-compose up -d meshstack-mock tencent-mock ionos-mock stackit-mock ovh-mock loki grafana

echo ""
echo "2. Waiting for all services to be healthy..."
sleep 15

echo ""
echo "3. Running tests for each platform..."
for PLATFORM in "${PLATFORMS[@]}"; do
    echo ""
    echo "--- Testing $PLATFORM ---"
    docker-compose --profile $PLATFORM up ${PLATFORM}-platform
    echo ""
done

echo ""
echo "4. Final report summary..."
curl -s http://localhost:5000/api/debug/reports | jq '.'

echo ""
echo "======================================"
echo "All Tests Complete"
echo "======================================"
echo ""
echo "View Grafana dashboard: http://localhost:3000"
echo "View Loki logs: http://localhost:3100"
echo ""
echo "To stop all services: docker-compose down"
