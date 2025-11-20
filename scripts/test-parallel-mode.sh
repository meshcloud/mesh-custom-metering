#!/bin/bash

set -e

PLATFORM=${1:-"tencent"}
NUM_WORKERS=${2:-3}

echo "======================================"
echo "Testing Parallel Mode for $PLATFORM"
echo "Workers: $NUM_WORKERS"
echo "======================================"

echo ""
echo "1. Starting mock services..."
docker-compose up -d meshstack-mock ${PLATFORM}-mock loki grafana

echo ""
echo "2. Waiting for services to be healthy..."
sleep 10

echo ""
echo "3. Starting master container with $NUM_WORKERS workers..."
docker-compose --profile $PLATFORM run \
    -e PARALLEL_MODE=true \
    -e NUM_WORKERS=$NUM_WORKERS \
    ${PLATFORM}-platform

echo ""
echo "4. Checking master container logs..."
docker-compose logs ${PLATFORM}-platform

echo ""
echo "5. Checking worker container logs..."
docker ps -a | grep "${PLATFORM}-worker"
for WORKER_ID in $(docker ps -a | grep "${PLATFORM}-worker" | awk '{print $1}'); do
    echo ""
    echo "--- Worker $WORKER_ID ---"
    docker logs $WORKER_ID
done

echo ""
echo "6. Checking reports submitted to meshStack..."
curl -s http://localhost:5000/api/debug/reports | jq '.'

echo ""
echo "======================================"
echo "Parallel Mode Test Complete"
echo "======================================"
echo ""
echo "To stop all services: docker-compose down"
