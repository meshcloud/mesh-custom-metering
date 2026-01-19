#!/bin/bash

set -e

echo "======================================"
echo "Building All Platform Containers"
echo "======================================"

PLATFORMS=("tencent" "ionos" "stackit" "ovh" "oci")

for PLATFORM in "${PLATFORMS[@]}"; do
    if [ -f "platforms/$PLATFORM/Dockerfile" ]; then
        echo ""
        echo "Building $PLATFORM platform..."
        docker build -t mesh-metering-$PLATFORM:latest -f platforms/$PLATFORM/Dockerfile .
    else
        echo ""
        echo "Warning: Dockerfile not found for $PLATFORM (expected at platforms/$PLATFORM/Dockerfile)"
    fi
done

echo ""
echo "======================================"
echo "Build Complete"
echo "======================================"
echo ""
echo "Available images:"
docker images | grep mesh-metering
