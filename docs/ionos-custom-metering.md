# IONOS Custom Metering with Product Group Support and Authentication

This document describes the custom IONOS metering implementation that includes product group information and comprehensive authentication support.

## Overview

The IONOS custom metering solution integrates IONOS cloud platform cost and usage data with meshStack. It now supports:
- **HTTP Basic Authentication** with IONOS APIs using username and password
- **Automatic retry logic** with exponential backoff for resilience
- **Configurable timeouts** for API requests
- **Product group information** for enhanced service categorization
- **Connection pooling** for efficient resource usage

## Architecture

```
IONOS APIs
├── /products         [Product catalog with pricing and product groups]
└── /usage           [Usage data by datacenter and meter type]
        ↓
[Data Retrieval Layer]
├── get_ionos_product_costs()     → Fetches product catalog
└── get_ionos_usage(month)        → Fetches usage by period
        ↓
[Data Processing Layer]
├── calculate_datacenter_costs()  → Matches products to usage + extracts product groups
└── transform_ionos_to_line_items() → Formats for meshStack with optional product group
        ↓
[meshStack Integration]
└── MeshStackClient.submit_usage_report() → Submits usage report with product groups
        ↓
meshStack Usage Reports API
```

## Features

### Core Features
- **HTTP Basic Authentication**: Securely authenticate with IONOS APIs using username and password
- **Retry Logic with Exponential Backoff**: Automatic retries for failed requests (1s, 2s, 4s delays)
- **Configurable Timeouts**: Set API request timeout to handle slow networks
- **Connection Pooling**: Efficient resource usage through session reuse
- **Error Handling**: Clear error messages for authentication failures
- **Modular Design**: Shared core libraries with platform-specific implementations
- **Observability**: Integrated Loki logging with structured logs

### Custom Metering Feature: Product Groups
- **Service categorization**: Enrich line items with product group information
- **Optional inclusion**: Enable/disable via environment variable
- **Backward compatible**: Existing functionality unchanged when disabled
- **Graceful handling**: Missing product groups don't cause errors
- **Datacenter-based grouping**: Groups metrics within each datacenter

## Configuration

### Required Environment Variables

```bash
# meshStack Configuration
MESHSTACK_MESHFED_URL=https://meshfed.example.com
MESHSTACK_KRAKEN_URL=https://kraken.example.com
MESHSTACK_API_USER=mesh-custom-metering
MESHSTACK_API_SECRET=your-secret-here
PLATFORM_ID=ionos

# IONOS Authentication (Required)
IONOS_USERNAME=your-ionos-username-or-email@example.com
IONOS_PASSWORD=your-ionos-password
IONOS_CONTRACT=your-contract-id

# IONOS API Configuration
IONOS_API_URL=https://api.ionos.com
```

### Optional Configuration

```bash
# Usage period (defaults to current month, format: YYYY-MM)
USAGE_PERIOD=2024-01

# Logging level (DEBUG, INFO, WARN, ERROR - default: INFO)
LOG_LEVEL=INFO

# Loki endpoint for log aggregation (optional)
LOKI_URL=http://loki:3100

# Include deleted tenants (default: true)
INCLUDE_DELETED_TENANTS=true

# IONOS API Performance (Optional)
# API timeout in seconds (default: 30)
IONOS_API_TIMEOUT=30

# Maximum number of retry attempts (default: 3)
IONOS_API_RETRIES=3

# CUSTOM METERING FEATURE: Enable product group information
IONOS_INCLUDE_PRODUCT_GROUP=false
```

### Quick Start with .env.example

1. Copy the example environment file:
```bash
cp platforms/ionos/.env.example platforms/ionos/.env
```

2. Update with your values:
```bash
# Edit .env with your IONOS and meshStack credentials
nano platforms/ionos/.env
```

3. Set the product group feature:
```bash
# Enable product group information in line items
IONOS_INCLUDE_PRODUCT_GROUP=true
```

## Product Group Feature

### What are Product Groups?

Product groups are categorical classifications from IONOS that identify service types:
- **Compute**: Virtual machines, dedicated servers, cloud functions
- **Storage**: Object storage, block storage, backup services
- **Network**: Bandwidth, load balancing, VPN services
- **Database**: Managed databases, data warehouses
- **Other**: Additional service categories

### Enabling Product Groups

```bash
# In your .env file or environment:
IONOS_INCLUDE_PRODUCT_GROUP=true
```

When enabled:
1. Product groups are extracted from IONOS product catalog
2. Matched to usage meters by product ID
3. Included in the `productGroup` field of each line item
4. Submitted to meshStack for categorization and reporting

### Example Output

#### Without Product Groups
```json
{
  "lineItems": [
    {
      "productName": "VM Instance",
      "usageQuantity": 5,
      "usageType": "IONOS Service vm-123",
      "usageCost": 52.50,
      "currency": "EUR",
      "usageUnit": "hours",
      "totalCost": 52.50,
      "sellerId": "IONOS"
    }
  ]
}
```

#### With Product Groups
```json
{
  "lineItems": [
    {
      "productName": "VM Instance",
      "usageQuantity": 5,
      "usageType": "IONOS Service vm-123",
      "usageCost": 52.50,
      "currency": "EUR",
      "usageUnit": "hours",
      "totalCost": 52.50,
      "sellerId": "IONOS",
      "productGroup": "Compute"
    }
  ]
}
```

## Data Flow

### 1. Product Retrieval

The implementation fetches the IONOS product catalog:

```python
GET /products
Response: {
  "products": [
    {
      "meterId": "compute-1",
      "meterDesc": "VM Instance",
      "unitCost": {"quantity": 10.50},
      "productGroup": "Compute"      # ← Product group from IONOS
    }
  ]
}
```

### 2. Usage Retrieval

Usage data is fetched for the specified period:

```python
GET /usage?period=2024-01
Response: {
  "datacenters": [
    {
      "id": "de-1",
      "name": "Germany 1",
      "meters": [
        {
          "meterId": "vm-123",
          "meterDesc": "VM Instance",
          "quantity": {"quantity": 5, "unit": "hours"}
        }
      ]
    }
  ]
}
```

### 3. Cost Calculation with Product Groups

```python
def calculate_datacenter_costs(usage_data, products, include_product_group=False):
    # For each meter in usage:
    # 1. Match to product by meterDesc
    # 2. Calculate cost: usage_quantity × unit_cost
    # 3. Extract product group (if enabled)
    # 4. Return enriched meter data
```

**Result with product groups enabled:**
```python
{
  'meterId': 'vm-123',
  'meterDesc': 'VM Instance',
  'quantity': 5,
  'unit': 'hours',
  'totalCost': 52.50,      # 5 × €10.50
  'productGroup': 'Compute' # ← Added when enabled
}
```

### 4. Transform to meshStack Format

```python
def transform_ionos_to_line_items(meters, include_product_group=False):
    # For each meter:
    # 1. Create line item with standard fields
    # 2. Include productGroup field (if present in meter)
    # 3. Return formatted line items
```

**Result:**
```json
{
  "productName": "VM Instance",
  "usageQuantity": 5,
  "usageType": "IONOS Service vm-123",
  "usageCost": 52.50,
  "currency": "EUR",
  "usageUnit": "hours",
  "totalCost": 52.50,
  "sellerId": "IONOS",
  "productGroup": "Compute"  # ← Optional, included if enabled
}
```

### 5. Submit to meshStack

```python
def submit_usage_report(tenant_id, date, payload):
    # Submit to meshStack API:
    # PUT /api/meshobjects/meshresourceusagereports/{tenantId}/{date}
    # Payload includes all line items with product groups (if enabled)
```

## Implementation Details

### Modified Functions

#### `calculate_datacenter_costs(usage_data, products, include_product_group=False)`

**Purpose**: Calculate datacenter costs and optionally extract product groups

**Parameters**:
- `usage_data`: IONOS usage response
- `products`: IONOS product catalog
- `include_product_group`: Enable product group extraction (default: False)

**Logic**:
1. For each datacenter in usage data
2. For each meter in datacenter
3. Find matching product by `meterDesc`
4. Calculate `totalCost = quantity × unitCost`
5. If `include_product_group` and product has `productGroup`:
   - Add `productGroup` to meter data

**Returns**: List of datacenters with calculated costs and optional product groups

#### `transform_ionos_to_line_items(meters, include_product_group=False)`

**Purpose**: Transform meter data to meshStack line item format

**Parameters**:
- `meters`: List of meter objects
- `include_product_group`: Include product group in output (default: False)

**Logic**:
1. For each meter with cost > 0
2. Create line item with standard meshStack fields
3. If `include_product_group` and `productGroup` in meter:
   - Add `productGroup` field to line item

**Returns**: List of line items ready for meshStack submission

#### `process_month(mesh_client, platform_id, month, include_product_group=False)`

**Purpose**: Orchestrate monthly processing

**Changes**:
- Accepts `include_product_group` parameter
- Passes to `calculate_datacenter_costs()` and `transform_ionos_to_line_items()`

#### `main()`

**Purpose**: Entry point with configuration

**Changes**:
- Reads `IONOS_INCLUDE_PRODUCT_GROUP` environment variable
- Passes to `process_month()` function
- Logs when product group feature is enabled

## Testing

### Running Tests

```bash
# Install test dependencies
pip install pytest

# Run all tests
pytest tests/

# Run only IONOS tests
pytest tests/ionos/

# Run with verbose output
pytest -v tests/ionos/

# Run with coverage
pytest --cov=platforms/ionos tests/ionos/
```

### Test Coverage

The test suite includes:

1. **Unit Tests**: `tests/ionos/test_product_group.py`
   - `TestCalculateDatacenterCosts`: Cost calculation and product group extraction
   - `TestTransformIonosToLineItems`: Line item transformation
   - `TestEndToEnd`: Complete workflow testing

2. **Test Cases**:
   - Calculate costs without product groups
   - Calculate costs with product groups
   - Handle missing product groups gracefully
   - Cost calculation accuracy
   - Line item transformation without product groups
   - Line item transformation with product groups
   - Exclude zero-cost items
   - Include product group only when present
   - Complete end-to-end flow

### Example Test Run

```bash
$ pytest -v tests/ionos/test_product_group.py

tests/ionos/test_product_group.py::TestCalculateDatacenterCosts::test_without_product_group PASSED
tests/ionos/test_product_group.py::TestCalculateDatacenterCosts::test_with_product_group PASSED
tests/ionos/test_product_group.py::TestCalculateDatacenterCosts::test_product_group_missing_gracefully_handled PASSED
tests/ionos/test_product_group.py::TestCalculateDatacenterCosts::test_cost_calculation_accuracy PASSED
tests/ionos/test_product_group.py::TestTransformIonosToLineItems::test_line_items_without_product_group PASSED
tests/ionos/test_product_group.py::TestTransformIonosToLineItems::test_line_items_with_product_group PASSED
tests/ionos/test_product_group.py::TestTransformIonosToLineItems::test_zero_cost_items_excluded PASSED
tests/ionos/test_product_group.py::TestTransformIonosToLineItems::test_product_group_only_included_when_present PASSED
tests/ionos/test_product_group.py::TestEndToEnd::test_complete_flow_with_product_group PASSED

====== 9 passed in 0.23s ======
```

## Deployment

### Docker Build

```bash
# Build IONOS container
docker build -t mesh-metering-ionos:latest -f platforms/ionos/Dockerfile .

# Tag for registry
docker tag mesh-metering-ionos:latest your-registry/mesh-metering-ionos:latest

# Push to registry
docker push your-registry/mesh-metering-ionos:latest
```

### Docker Compose

```bash
# Start with observability stack
docker-compose up -d loki grafana
docker-compose up ionos-platform

# View logs
docker-compose logs -f ionos-platform

# Stop
docker-compose down
```

### Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mesh-metering-ionos
  namespace: metering
spec:
  # Run daily at 6 AM UTC
  schedule: "0 6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: mesh-metering
          containers:
          - name: metering
            image: mesh-metering-ionos:latest
            imagePullPolicy: IfNotPresent
            envFrom:
            - secretRef:
                name: mesh-metering-secrets
            - configMapRef:
                name: mesh-metering-config
            resources:
              requests:
                memory: "128Mi"
                cpu: "100m"
              limits:
                memory: "512Mi"
                cpu: "500m"
          restartPolicy: OnFailure
          backoffLimit: 3
```

### Environment Variables for Kubernetes

```bash
# Create secret with sensitive credentials
kubectl create secret generic mesh-metering-secrets \
  --from-literal=MESHSTACK_API_USER=mesh-custom-metering \
  --from-literal=MESHSTACK_API_SECRET=your-secret-here \
  -n metering

# Create configmap with general configuration
kubectl create configmap mesh-metering-config \
  --from-literal=MESHSTACK_MESHFED_URL=https://meshfed.example.com \
  --from-literal=MESHSTACK_KRAKEN_URL=https://kraken.example.com \
  --from-literal=PLATFORM_ID=ionos \
  --from-literal=IONOS_API_URL=https://api.ionos.com \
  --from-literal=IONOS_INCLUDE_PRODUCT_GROUP=true \
  --from-literal=LOG_LEVEL=INFO \
  -n metering
```

## Troubleshooting

### Product Group Not Appearing in Line Items

**Problem**: Product group field is missing from submitted line items

**Solutions**:
1. Check environment variable is set: `IONOS_INCLUDE_PRODUCT_GROUP=true`
2. Verify IONOS product catalog includes `productGroup` field
3. Check logs for "Product group information will be included"
4. Verify product matching logic (products matched by `meterDesc`)

### Missing Product Groups in IONOS Response

**Problem**: IONOS product catalog doesn't include product group data

**Solutions**:
1. Verify IONOS API endpoint is correct
2. Check IONOS API documentation for product group field name
3. May need to update product matching logic if field name differs
4. Contact IONOS support for API schema details

### Cost Calculation Errors

**Problem**: Incorrect cost calculations

**Solutions**:
1. Verify unit cost values in IONOS product catalog
2. Check quantity values from usage data
3. Enable DEBUG logging: `LOG_LEVEL=DEBUG`
4. Review calculation formula: `totalCost = quantity × unitCost`

### Incomplete Data Submission

**Problem**: Usage report submitted but some line items missing

**Solutions**:
1. Check meshStack API response in logs
2. Verify all line items have cost > 0 (zero-cost items are filtered)
3. Check datacenter IDs match meshStack tenant IDs
4. Review meshStack API rate limits

## Logging

### Log Levels

```bash
# DEBUG: Detailed trace information
LOG_LEVEL=DEBUG

# INFO: General information (default)
LOG_LEVEL=INFO

# WARN: Warning messages
LOG_LEVEL=WARN

# ERROR: Error messages only
LOG_LEVEL=ERROR
```

### Example Logs with Product Group

```
2024-02-16 10:30:45 INFO Starting IONOS metering collection
2024-02-16 10:30:45 INFO Product group information will be included in line items
2024-02-16 10:30:45 INFO Processing IONOS costs for 2024-02
2024-02-16 10:30:46 INFO Processing datacenter de-1
2024-02-16 10:30:46 INFO Successfully submitted report for datacenter de-1
```

### Loki Log Aggregation

```bash
# Query logs by platform
{platform="ionos"}

# Query error logs
{platform="ionos"} | json | level="ERROR"

# Query product group feature logs
{platform="ionos"} | "product group"
```

## Performance Considerations

- **Sequential processing**: Datacenters processed sequentially to avoid rate limiting
- **Retry logic**: 3 attempts with exponential backoff (4-10 seconds)
- **Memory efficient**: Streams data to avoid large in-memory objects
- **Container optimized**: ~250MB max memory usage for typical deployments

## Backward Compatibility

The product group feature is **fully backward compatible**:
- Default: `IONOS_INCLUDE_PRODUCT_GROUP=false`
- Existing configurations continue to work unchanged
- No breaking changes to core functionality
- Can be enabled/disabled per deployment

## Next Steps

1. **Copy `.env.example`**: `cp platforms/ionos/.env.example platforms/ionos/.env`
2. **Update configuration**: Add your IONOS and meshStack credentials
3. **Enable product groups**: Set `IONOS_INCLUDE_PRODUCT_GROUP=true`
4. **Run tests**: `pytest tests/ionos/test_product_group.py`
5. **Build container**: `docker build -t mesh-metering-ionos:latest -f platforms/ionos/Dockerfile .`
6. **Deploy**: Use Docker Compose or Kubernetes examples above

## References

- Main implementation: `platforms/ionos/main.py`
- Test suite: `tests/ionos/test_product_group.py`
- Configuration template: `platforms/ionos/.env.example`
- Core libraries: `src/core/`
- Legacy implementation: `oldcode/ionos/metering/index.ts`

## Support

For issues or questions:
1. Check logs for error messages
2. Review configuration against `.env.example`
3. Run test suite to verify functionality
4. Enable DEBUG logging for detailed information
