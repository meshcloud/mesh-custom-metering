# AWS meshStack Custom Metering

A production-ready metering module that collects cost and usage data from AWS and submits it to meshStack for billing and chargeback.

## Features

- **Configurable Cost Metrics**: Choose between `UnblendedCost` (itemized) and `AmortizedCost` (smoothed)
- **Multi-Account Support**: Automatically discovers and processes all AWS organization accounts
- **Flexible Filtering**: Optional account ID filtering and period selection
- **Robust Error Handling**: Retry logic with exponential backoff for resilience
- **Comprehensive Logging**: Structured logging with optional Loki integration
- **Production-Ready**: Security-hardened containerized deployment
- **Cost Effective**: Optimized for serverless environments

## Quick Start

### Prerequisites

- AWS Organization setup with Cost Explorer enabled
- meshStack instance with credentials
- Python 3.10+ (for local development)
- Docker (for containerized deployment)
- AWS IAM credentials with appropriate permissions

### Configuration

1. Copy the environment template:
```bash
cp .env.example .env
```

2. Configure required values:
```bash
# meshStack Configuration
MESHSTACK_MESHFED_URL=https://meshfed.example.com
MESHSTACK_KRAKEN_URL=https://kraken.example.com
MESHSTACK_API_USER=mesh-custom-metering
MESHSTACK_API_SECRET=your-secret-here
PLATFORM_ID=aws

# AWS Configuration
AWS_REGION=eu-central-1
AWS_COST_TYPE=UnblendedCost
```

3. Set up AWS credentials (see [AWS Authentication](#aws-authentication) section)

### Local Execution

```bash
# Install dependencies
pip install -r requirements.txt

# Run the metering collection
python main.py
```

### Docker Execution

```bash
# Build the image
docker build -t mesh-metering-aws:latest -f Dockerfile .

# Run the container
docker run --rm \
  --env-file .env \
  -v ~/.aws/credentials:/home/metering/.aws/credentials:ro \
  mesh-metering-aws:latest
```

## Configuration

### Environment Variables

#### Required

| Variable | Description | Example |
|----------|---|---|
| `MESHSTACK_MESHFED_URL` | meshStack MeshFed API endpoint | `https://meshfed.example.com` |
| `MESHSTACK_KRAKEN_URL` | meshStack Kraken API endpoint | `https://kraken.example.com` |
| `MESHSTACK_API_USER` | API username | `mesh-custom-metering` |
| `MESHSTACK_API_SECRET` | API password/secret | `your-secret-here` |
| `PLATFORM_ID` | Platform identifier in meshStack | `aws` |

#### AWS Configuration

| Variable | Description | Default | Options |
|----------|---|---|---|
| `AWS_REGION` | AWS region for API calls | `eu-central-1` | Any valid AWS region |
| `AWS_COST_TYPE` | Cost metric to report | `UnblendedCost` | `UnblendedCost`, `AmortizedCost` |
| `AWS_LINKED_ACCOUNTS` | Specific accounts to process (optional) | All accounts | Comma-separated account IDs |
| `INCLUDE_DELETED_TENANTS` | Include deleted accounts | `true` | `true`, `false` |

#### Metering Configuration

| Variable | Description | Default | Notes |
|----------|---|---|---|
| `USAGE_PERIOD` | Period to process | Current month | `YYYY-MM` format |
| `INCLUDE_LAST_MONTH` | Process last month too | Auto (first 5 days) | `true`, `false`, or unset for auto |

#### Logging Configuration

| Variable | Description | Default | Options |
|----------|---|---|---|
| `LOG_LEVEL` | Logging verbosity | `INFO` | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `LOKI_URL` | Loki log aggregation endpoint | Not set | URL with protocol |

### Cost Type Comparison

#### UnblendedCost (Default)
- **Best for**: Detailed cost analysis, precise chargeback
- **Characteristics**:
  - Shows actual itemized costs per service/usage type
  - Reflects real charges without any smoothing
  - Can vary significantly day-to-day
  - Includes all discounts applied at the time of purchase

#### AmortizedCost
- **Best for**: Smooth cost trends, budget forecasting
- **Characteristics**:
  - Spreads upfront commitments across usage period
  - Amortizes one-time fees evenly
  - Creates consistent daily/monthly costs
  - Better for predictable chargeback models

### Configuration Examples

#### Example 1: Basic Setup (Default UnblendedCost)
```bash
MESHSTACK_MESHFED_URL=https://meshfed.example.com
MESHSTACK_KRAKEN_URL=https://kraken.example.com
MESHSTACK_API_USER=mesh-custom-metering
MESHSTACK_API_SECRET=abc123
PLATFORM_ID=aws
AWS_REGION=eu-central-1
# Uses default UnblendedCost
```

#### Example 2: Amortized Cost for Budget Planning
```bash
MESHSTACK_MESHFED_URL=https://meshfed.example.com
MESHSTACK_KRAKEN_URL=https://kraken.example.com
MESHSTACK_API_USER=mesh-custom-metering
MESHSTACK_API_SECRET=abc123
PLATFORM_ID=aws
AWS_REGION=us-east-1
AWS_COST_TYPE=AmortizedCost
```

#### Example 3: Multi-Account with Selective Filtering
```bash
MESHSTACK_MESHFED_URL=https://meshfed.example.com
MESHSTACK_KRAKEN_URL=https://kraken.example.com
MESHSTACK_API_USER=mesh-custom-metering
MESHSTACK_API_SECRET=abc123
PLATFORM_ID=aws
AWS_REGION=eu-central-1
AWS_LINKED_ACCOUNTS=123456789012,210987654321
INCLUDE_LAST_MONTH=false
```

#### Example 4: Debug Logging with Loki
```bash
MESHSTACK_MESHFED_URL=https://meshfed.example.com
MESHSTACK_KRAKEN_URL=https://kraken.example.com
MESHSTACK_API_USER=mesh-custom-metering
MESHSTACK_API_SECRET=abc123
PLATFORM_ID=aws
AWS_REGION=eu-central-1
LOG_LEVEL=DEBUG
LOKI_URL=http://loki:3100
```

## AWS Authentication

The module uses the standard AWS SDK authentication chain:

1. **Environment Variables** (highest priority)
   ```bash
   export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
   export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
   python main.py
   ```

2. **AWS Credentials File**
   ```bash
   # ~/.aws/credentials
   [default]
   aws_access_key_id = AKIAIOSFODNN7EXAMPLE
   aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
   ```

3. **IAM Role** (Recommended for cloud deployments)
   - Attach the role to EC2, ECS, Lambda, or other compute service
   - No credentials needed; automatic authentication

4. **Temporary Credentials** via STS
   ```bash
   export AWS_ACCESS_KEY_ID=ASIATEMP...
   export AWS_SECRET_ACCESS_KEY=...
   export AWS_SESSION_TOKEN=...
   python main.py
   ```

### Required IAM Permissions

Create an IAM policy with the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CostExplorerReadOnly",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage"
      ],
      "Resource": "*"
    },
    {
      "Sid": "OrganizationsReadOnly",
      "Effect": "Allow",
      "Action": [
        "organizations:ListAccounts"
      ],
      "Resource": "*"
    }
  ]
}
```

### Docker with AWS Credentials

#### Option 1: Mount AWS Credentials File
```bash
docker run --rm \
  --env-file .env \
  -v ~/.aws/credentials:/home/metering/.aws/credentials:ro \
  mesh-metering-aws:latest
```

#### Option 2: Pass Credentials as Environment Variables
```bash
docker run --rm \
  --env-file .env \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  mesh-metering-aws:latest
```

#### Option 3: Use IAM Role (AWS/ECS/Lambda)
```bash
# Attach IAM role to the compute service
docker run --rm \
  --env-file .env \
  mesh-metering-aws:latest
```

## How It Works

### Process Flow

```mermaid
graph LR;
    A["Configuration<br/>(Environment Variables)"]
    B["AWS Organizations API<br/>(List Accounts)"]
    C["AWS Cost Explorer API<br/>(Get Costs)"]
    D["Data Transformation<br/>(meshResourceUsageReport)"]
    E["meshStack MeshFed API<br/>(Submit Report)"]
    
    A --> B
    B --> C
    C --> D
    D --> E
```

### Step-by-Step

1. **Load Configuration**: Validates all required environment variables
2. **Initialize AWS Clients**: Creates Cost Explorer and Organizations clients
3. **List Accounts**: Fetches all active/suspended accounts from AWS Organization
4. **For Each Account**:
   - Query Cost Explorer for the specified period(s)
   - Filter by specified cost type (UnblendedCost or AmortizedCost)
   - Group costs by service and usage type
5. **Transform Data**: Convert AWS cost data to meshStack `meshResourceUsageReport` format
6. **Submit Reports**: Send to meshStack MeshFed API using Basic Auth
7. **Handle Errors**: Log failures and continue with next account

### Data Grouping

Costs are aggregated by:
- **Service**: EC2, S3, RDS, Lambda, etc.
- **Usage Type**: On-Demand, Reserved Instances, Spot, etc.

This provides granular cost visibility within meshStack.

## Logging

### Log Levels

| Level | Use Case | Examples |
|-------|----------|----------|
| `DEBUG` | Development & troubleshooting | AWS API calls, detailed state transitions |
| `INFO` | Production monitoring | Accounts processed, reports sent |
| `WARN` | Issues that don't stop execution | No cost data found, API warnings |
| `ERROR` | Failures that need attention | API errors, invalid configuration |

### Log Examples

```
2024-01-15 10:30:45 - __main__ - INFO - AWS configuration loaded: region=eu-central-1, cost_type=UnblendedCost
2024-01-15 10:30:46 - __main__ - INFO - 🔍 Fetching AWS accounts from organization...
2024-01-15 10:30:47 - __main__ - INFO - ✅ Found 3 active/suspended accounts
2024-01-15 10:30:48 - __main__ - INFO - 📦 Processing Production (123456789012) for 2024-01
2024-01-15 10:30:49 - __main__ - INFO - 📊 Found 45 cost items
2024-01-15 10:30:50 - __main__ - INFO - ✅ Successfully sent usage report for 123456789012/2024-01
2024-01-15 10:30:51 - __main__ - INFO - 🎉 Processing complete: 3/3 reports sent successfully
```

## Troubleshooting

### Common Issues

#### 1. "MESHSTACK_MESHFED_URL environment variable is not set"
```bash
# Check environment variable
echo $MESHSTACK_MESHFED_URL

# Fix: Set the variable
export MESHSTACK_MESHFED_URL=https://meshfed.example.com
```

#### 2. "Unable to locate credentials"
```bash
# Check AWS credentials
aws sts get-caller-identity

# Fix: Configure AWS credentials (see AWS Authentication section)
```

#### 3. "HTTP 401 - Unauthorized"
```bash
# Check meshStack credentials
echo $MESHSTACK_API_USER
echo $MESHSTACK_API_SECRET

# Verify credentials are correct in meshStack
# Check for special characters that might need escaping
```

#### 4. "No cost data found"
- Verify Cost Explorer is enabled in AWS account
- Check that the account has actual usage/costs
- Verify AWS_COST_TYPE is correctly set
- Check date range is correct (YYYY-MM format)

#### 5. "Timeout error"
- Increase timeout for large accounts with many services
- Check network connectivity to AWS and meshStack APIs
- Verify AWS API rate limits aren't exceeded

### Debug Mode

Enable debug logging to see detailed operation:

```bash
export LOG_LEVEL=DEBUG
python main.py
```

Debug output includes:
- AWS API parameters and responses
- meshStack payload details
- Retry attempts and backoff timing
- Configuration values

## Deployment

### Docker Compose Example

```yaml
version: '3.8'

services:
  aws-metering:
    build:
      context: .
      dockerfile: platforms/aws/Dockerfile
    environment:
      - MESHSTACK_MESHFED_URL=https://meshfed.example.com
      - MESHSTACK_KRAKEN_URL=https://kraken.example.com
      - MESHSTACK_API_USER=mesh-custom-metering
      - MESHSTACK_API_SECRET=${MESHSTACK_API_SECRET}
      - PLATFORM_ID=aws
      - AWS_REGION=eu-central-1
      - AWS_COST_TYPE=UnblendedCost
      - LOG_LEVEL=INFO
    volumes:
      - ~/.aws/credentials:/home/metering/.aws/credentials:ro
    restart: on-failure
```

### Kubernetes CronJob Example

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: aws-metering
spec:
  schedule: "5 1 * * *"  # Daily at 01:05 UTC
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: aws-metering
            image: mesh-metering-aws:latest
            env:
            - name: MESHSTACK_MESHFED_URL
              value: https://meshfed.example.com
            - name: MESHSTACK_KRAKEN_URL
              value: https://kraken.example.com
            - name: MESHSTACK_API_USER
              valueFrom:
                secretKeyRef:
                  name: meshstack
                  key: api-user
            - name: MESHSTACK_API_SECRET
              valueFrom:
                secretKeyRef:
                  name: meshstack
                  key: api-secret
            - name: PLATFORM_ID
              value: aws
            - name: AWS_COST_TYPE
              value: UnblendedCost
            volumeMounts:
            - name: aws-credentials
              mountPath: /home/metering/.aws
              readOnly: true
          restartPolicy: OnFailure
          volumes:
          - name: aws-credentials
            secret:
              secretName: aws-credentials
```

### AWS Lambda Example

```python
# lambda_handler.py
import subprocess
import os
import json

def lambda_handler(event, context):
    # Set environment variables from Lambda config
    env_vars = os.environ.copy()
    
    # Run the metering script
    result = subprocess.run(['python', 'main.py'], 
                          env=env_vars,
                          capture_output=True,
                          text=True)
    
    return {
        'statusCode': result.returncode,
        'body': json.dumps({
            'stdout': result.stdout,
            'stderr': result.stderr
        })
    }
```

## API Reference

### meshResourceUsageReport Format

The module generates reports in the following format:

```json
{
  "apiVersion": "v1",
  "kind": "meshResourceUsageReport",
  "fullPlatformIdentifier": "aws",
  "source": "AWS",
  "lineItems": [
    {
      "meterName": "Amazon EC2",
      "meterCategory": "AWS",
      "quantity": 730,
      "cost": 123.45,
      "currency": "USD",
      "usageType": "BoxUsage:t3.medium"
    },
    {
      "meterName": "Amazon S3",
      "meterCategory": "AWS",
      "quantity": 1024,
      "cost": 23.55,
      "currency": "USD",
      "usageType": "StandardStorage"
    }
  ]
}
```

## Performance Considerations

### Execution Time

- Typical execution: 30-60 seconds per 50 accounts
- Cost Explorer API: ~1-2 seconds per account
- Network I/O: ~5-10 seconds for API calls to meshStack
- Scales linearly with number of accounts

### API Rate Limits

- AWS Cost Explorer: 20 requests/second per account
- AWS Organizations: 20 requests/second
- meshStack MeshFed: Configurable per deployment

### Optimization Tips

1. **Batch Processing**: Process multiple months in separate runs if needed
2. **Account Filtering**: Use `AWS_LINKED_ACCOUNTS` to process only relevant accounts
3. **Scheduling**: Run during off-peak hours to reduce API contention
4. **Concurrency**: Don't run multiple instances simultaneously for the same accounts

## Security

### Best Practices

1. **Credentials**:
   - Use IAM roles whenever possible (avoid long-lived keys)
   - Rotate access keys regularly
   - Never commit credentials to version control

2. **Network**:
   - Use HTTPS for all API calls (enforced)
   - Run in private subnets with NAT gateway access
   - Use VPC endpoints for AWS services

3. **Permissions**:
   - Follow principle of least privilege
   - Restrict IAM policy to only needed permissions
   - Use separate credentials for different environments

4. **Logging**:
   - Don't log sensitive data (credentials, secrets)
   - Use centralized logging with access controls
   - Rotate and archive logs regularly

## License

This module is part of the meshStack Custom Metering Framework. See the main README for licensing information.

## Support

For issues, questions, or contributions:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review configuration examples
3. Enable DEBUG logging for detailed diagnostics
4. Contact meshcloud support with logs and configuration details

## Changelog

### Version 1.0.0 (2024-01)
- Initial release
- Support for UnblendedCost and AmortizedCost metrics
- Multi-account AWS Organization support
- Flexible period configuration
- Retry logic with exponential backoff
- Structured logging with optional Loki integration
