# Local Testing Infrastructure

This directory contains mock services and testing infrastructure for developing and testing mesh-custom-metering platform integrations locally.

## Directory Structure

```
tests/
├── mocks/                      # Mock API services
│   ├── meshstack_mock.py       # meshStack API mock
│   ├── tencent_mock.py         # Tencent Cloud API mock
│   ├── ionos_mock.py           # IONOS API mock
│   ├── stackit_mock.py         # STACKIT API mock
│   ├── ovh_mock.py             # OVH API mock
│   ├── requirements.txt        # Python dependencies
│   └── Dockerfile.meshstack-mock
└── monitoring/                 # Monitoring configurations
    └── grafana-datasources.yaml
```

## Mock Services

Each mock service simulates a real API endpoint:

### meshStack Mock (Port 5000)
- `GET /health` - Health check
- `GET /api/meshobjects/meshtenants?platformIdentifier=<id>` - List tenants
- `PUT /api/meshobjects/meshresourceusagereports/<tenant_id>/<date>` - Submit usage report
- `GET /api/debug/reports` - Debug: View all stored reports
- `POST /api/debug/clear` - Debug: Clear all reports

**Authentication**: Basic Auth (user: `test_user`, password: `test_password`)

### Tencent Mock (Port 5001)
- `GET /health` - Health check
- `POST /api/billing/v20180709/DescribeBillDetail` - Get billing details

### IONOS Mock (Port 5002)
- `GET /health` - Health check
- `GET /api/v1/contracts/<contract_id>/usage` - Get usage data
- `GET /api/v1/contracts/<contract_id>/invoices` - Get invoices

**Authentication**: Bearer token

### STACKIT Mock (Port 5003)
- `GET /health` - Health check
- `GET /api/v1/projects/<project_id>/billing/usage` - Get usage data
- `GET /api/v1/projects/<project_id>/billing/invoices` - Get invoices

**Authentication**: Bearer token

### OVH Mock (Port 5004)
- `GET /health` - Health check
- `GET /cloud/project/<project_id>/usage/current` - Get current usage
- `GET /cloud/project/<project_id>/usage/history` - Get usage history
- `GET /cloud/project/<project_id>/bill` - Get bills

**Authentication**: Custom header `X-Ovh-Application`

## Quick Start

### Test a Single Platform

```bash
# Test Tencent platform
./scripts/local-test.sh tencent

# Test IONOS platform
./scripts/local-test.sh ionos

# Test STACKIT platform
./scripts/local-test.sh stackit

# Test OVH platform
./scripts/local-test.sh ovh
```

### Test All Platforms

```bash
./scripts/test-all-platforms.sh
```

### Test Parallel Mode

Test a platform with multiple worker containers:

```bash
# Test with 3 workers (default)
./scripts/test-parallel-mode.sh tencent

# Test with 5 workers
./scripts/test-parallel-mode.sh tencent 5
```

### Manual Testing

Start only the mock services:

```bash
docker-compose up -d meshstack-mock tencent-mock ionos-mock stackit-mock ovh-mock loki grafana
```

Test a specific platform manually:

```bash
# Start platform container
docker-compose --profile tencent up tencent-platform

# View logs
docker-compose logs -f tencent-platform
```

## Monitoring

Access monitoring tools:

- **Grafana**: http://localhost:3000 (admin/admin)
- **Loki**: http://localhost:3100

## Debugging

### Check Mock Service Health

```bash
curl http://localhost:5000/health  # meshStack
curl http://localhost:5001/health  # Tencent
curl http://localhost:5002/health  # IONOS
curl http://localhost:5003/health  # STACKIT
curl http://localhost:5004/health  # OVH
```

### View Submitted Reports

```bash
curl -s http://localhost:5000/api/debug/reports | jq '.'
```

### Clear Test Data

```bash
curl -X POST http://localhost:5000/api/debug/clear
```

### View Container Logs

```bash
docker-compose logs -f meshstack-mock
docker-compose logs -f tencent-platform
```

## Cleanup

Stop all services:

```bash
docker-compose down
```

Stop and remove volumes:

```bash
docker-compose down -v
```

## Environment Variables

Platform containers use these environment variables:

```bash
# meshStack API
MESHSTACK_API_HOST=http://meshstack-mock:5000
MESHSTACK_API_USER=test_user
MESHSTACK_API_PASSWORD=test_password

# Platform-specific (example: Tencent)
TENCENT_API_HOST=http://tencent-mock:5001
TENCENT_SECRET_ID=test_secret_id
TENCENT_SECRET_KEY=test_secret_key

# Common
PLATFORM_ID=<platform>.test
LOKI_URL=http://loki:3100

# Parallel mode (optional)
PARALLEL_MODE=true
NUM_WORKERS=3
```

## Adding New Mock Services

1. Create `<platform>_mock.py` in `tests/mocks/`
2. Add health check endpoint: `GET /health`
3. Implement platform-specific API endpoints
4. Add service to `docker-compose.yml`:
   - Add mock service (port 500X)
   - Add platform service with profile
5. Test with `./scripts/local-test.sh <platform>`

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs <service-name>

# Rebuild containers
docker-compose build --no-cache
```

### Port already in use
```bash
# Check what's using the port
lsof -i :5000

# Stop conflicting service or change port in docker-compose.yml
```

### Network issues
```bash
# Recreate network
docker-compose down
docker network prune
docker-compose up
```
