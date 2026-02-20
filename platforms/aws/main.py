import os
import sys
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import calendar
from functools import wraps
import time

import boto3
from botocore.exceptions import ClientError
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================================
# Configuration & Setup
# ============================================================================

def setup_logging() -> None:
    """Configure logging with optional Loki support."""
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    loki_url = os.environ.get('LOKI_URL', '').strip()
    
    if loki_url:
        logger.info(f"Loki URL configured: {loki_url}")
    
    return logger


logger = setup_logging()


def load_aws_config() -> Dict:
    """
    Loads AWS configuration from environment variables.
    
    Required environment variables:
        - AWS_REGION: AWS region (e.g., 'eu-central-1')
        - MESHSTACK_MESHFED_URL: meshStack MeshFed API endpoint
        - MESHSTACK_KRAKEN_URL: meshStack Kraken API endpoint
        - MESHSTACK_API_USER: API username
        - MESHSTACK_API_SECRET: API secret/password
        - PLATFORM_ID: Platform identifier in meshStack (e.g., 'aws')
    
    Optional environment variables:
        - AWS_COST_TYPE: 'AmortizedCost' or 'UnblendedCost' (default: 'UnblendedCost')
        - AWS_LINKED_ACCOUNTS: Comma-separated list of account IDs to process
        - INCLUDE_DELETED_TENANTS: Include deleted tenants (default: true)
        - USAGE_PERIOD: Period in YYYY-MM format (defaults to current month)
        - INCLUDE_LAST_MONTH: Process last month too (auto-detect if first 5 days)
    
    Returns:
        Dict with validated configuration
        
    Raises:
        ValueError: If required configuration is missing or invalid
    """
    # AWS Configuration
    region = os.environ.get('AWS_REGION', 'eu-central-1').strip()
    cost_type = os.environ.get('AWS_COST_TYPE', 'UnblendedCost').strip()
    linked_accounts = os.environ.get('AWS_LINKED_ACCOUNTS', '').strip()
    
    if cost_type not in ('AmortizedCost', 'UnblendedCost'):
        raise ValueError(
            f"AWS_COST_TYPE must be 'AmortizedCost' or 'UnblendedCost', got '{cost_type}'"
        )
    
    linked_accounts_list = [acc.strip() for acc in linked_accounts.split(',')] if linked_accounts else None
    
    # meshStack Configuration
    meshfed_url = os.environ.get('MESHSTACK_MESHFED_URL', '').strip()
    kraken_url = os.environ.get('MESHSTACK_KRAKEN_URL', '').strip()
    api_user = os.environ.get('MESHSTACK_API_USER', '').strip()
    api_secret = os.environ.get('MESHSTACK_API_SECRET', '').strip()
    platform_id = os.environ.get('PLATFORM_ID', '').strip()
    
    if not meshfed_url:
        raise ValueError("MESHSTACK_MESHFED_URL environment variable is not set")
    if not kraken_url:
        raise ValueError("MESHSTACK_KRAKEN_URL environment variable is not set")
    if not api_user:
        raise ValueError("MESHSTACK_API_USER environment variable is not set")
    if not api_secret:
        raise ValueError("MESHSTACK_API_SECRET environment variable is not set")
    if not platform_id:
        raise ValueError("PLATFORM_ID environment variable is not set")
    
    # Period Configuration
    usage_period = os.environ.get('USAGE_PERIOD', '').strip()
    include_deleted_tenants = os.environ.get('INCLUDE_DELETED_TENANTS', 'true').lower() == 'true'
    
    config = {
        'aws': {
            'region': region,
            'cost_type': cost_type,
            'linked_accounts': linked_accounts_list,
        },
        'meshstack': {
            'meshfed_url': meshfed_url,
            'kraken_url': kraken_url,
            'api_user': api_user,
            'api_secret': api_secret,
            'platform_id': platform_id,
        },
        'metering': {
            'usage_period': usage_period,
            'include_deleted_tenants': include_deleted_tenants,
        }
    }
    
    logger.info(f"AWS configuration loaded: region={region}, cost_type={cost_type}")
    logger.info(f"meshStack platform: {platform_id}")
    
    return config


def retry_with_backoff(max_retries: int = 3, backoff_factor: float = 1.0):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for delay between retries
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ClientError as e:
                    if attempt == max_retries - 1:
                        raise
                    
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}, "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
        
        return wrapper
    return decorator


# ============================================================================
# AWS Operations
# ============================================================================

def get_aws_clients(region: str) -> Tuple:
    """
    Creates AWS service clients for Cost Explorer and Organizations.
    
    Args:
        region: AWS region
        
    Returns:
        Tuple of (cost_explorer_client, organizations_client)
        
    Raises:
        Exception: If client initialization fails
    """
    try:
        cost_explorer = boto3.client('ce', region_name=region)
        organizations = boto3.client('organizations', region_name=region)
        
        logger.info(f"AWS clients initialized for region: {region}")
        return cost_explorer, organizations
    except Exception as e:
        logger.error(f"Failed to initialize AWS clients: {e}")
        raise


@retry_with_backoff(max_retries=3, backoff_factor=1.0)
def list_accounts(org_client, account_ids: Optional[List[str]] = None) -> List[Dict]:
    """
    Fetches all active AWS accounts from the organization.
    
    Args:
        org_client: Organizations client
        account_ids: Optional list of specific account IDs to fetch (filter)
        
    Returns:
        List of dicts with 'Id' and 'Name' keys
        
    Raises:
        ClientError: If API call fails
    """
    logger.info("🔍 Fetching AWS accounts from organization...")
    
    all_accounts: List[Dict] = []
    paginator = org_client.get_paginator('list_accounts')
    
    try:
        for page in paginator.paginate():
            accounts = page.get('Accounts', [])
            
            for account in accounts:
                # Filter for active/suspended accounts
                if account.get('Status') in ('ACTIVE', 'SUSPENDED'):
                    # Apply account filter if specified
                    if account_ids and account['Id'] not in account_ids:
                        continue
                    
                    all_accounts.append({
                        'Id': account['Id'],
                        'Name': account.get('Name', 'Unknown')
                    })
        
        logger.info(f"✅ Found {len(all_accounts)} active/suspended accounts")
        
        for account in all_accounts:
            logger.debug(f"  - {account['Name']} ({account['Id']})")
        
        return all_accounts
    
    except ClientError as e:
        logger.error(f"Failed to list accounts: {e}")
        raise


def get_month_date_range(month: str) -> Tuple[str, str]:
    """
    Generates date range for a given month in ISO 8601 format.
    
    AWS Cost Explorer expects:
    - Start date: inclusive (first day of month)
    - End date: exclusive (first day of next month)
    
    Args:
        month: Month in YYYY-MM format
        
    Returns:
        Tuple of (from_date, to_date) in YYYY-MM-DD format
        
    Raises:
        ValueError: If month format is invalid
    """
    try:
        date_obj = datetime.strptime(month, "%Y-%m")
        from_date = date_obj.strftime("%Y-%m-01")
        
        # Calculate first day of next month
        if date_obj.month == 12:
            next_month = date_obj.replace(year=date_obj.year + 1, month=1)
        else:
            next_month = date_obj.replace(month=date_obj.month + 1)
        
        to_date = next_month.strftime("%Y-%m-01")
        
        return from_date, to_date
    
    except ValueError as e:
        logger.error(f"Invalid month format '{month}': {e}")
        raise


def get_current_and_last_month() -> Tuple[str, str, bool]:
    """
    Gets current and last month in YYYY-MM format.
    
    Also determines if last month should be processed:
    - Auto-process if in first 5 days of month (to catch partial data from last month)
    - Can be overridden by INCLUDE_LAST_MONTH env var
    
    Returns:
        Tuple of (current_month, last_month, should_process_last_month)
    """
    now = datetime.now()
    current_month = now.strftime("%Y-%m")
    
    last_month_date = now - timedelta(days=now.day)
    last_month = last_month_date.strftime("%Y-%m")
    
    # Auto-detect: process last month if in first 5 days
    should_process_last = now.day <= 5
    
    # Allow explicit override via environment variable
    include_last_month = os.environ.get('INCLUDE_LAST_MONTH', '').strip().lower()
    if include_last_month in ('true', 'false'):
        should_process_last = include_last_month == 'true'
    
    logger.debug(
        f"Period: current={current_month}, last={last_month}, "
        f"process_last={should_process_last}"
    )
    
    return current_month, last_month, should_process_last


@retry_with_backoff(max_retries=3, backoff_factor=1.0)
def get_costs_for_account_for_month(
    ce_client,
    account_id: str,
    month: str,
    cost_type: str = 'UnblendedCost'
) -> List[Dict]:
    """
    Retrieves AWS cost and usage data for a specific account and month.
    
    Fetches cost information grouped by AWS service and usage type.
    
    Args:
        ce_client: Cost Explorer client
        account_id: AWS account ID to query
        month: Month in YYYY-MM format
        cost_type: 'AmortizedCost' or 'UnblendedCost'
        
    Returns:
        List of dicts with cost items, or empty list if no data
        
    Raises:
        ClientError: If API call fails
    """
    from_date, to_date = get_month_date_range(month)
    
    logger.debug(f"Querying costs for account {account_id}: {from_date} to {to_date}")
    
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': from_date,
                'End': to_date
            },
            Granularity='MONTHLY',
            Metrics=[cost_type, 'UsageQuantity'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}
            ],
            Filter={
                'And': [
                    {
                        'Dimensions': {
                            'Key': 'LINKED_ACCOUNT',
                            'Values': [account_id]
                        }
                    },
                    {
                        'Dimensions': {
                            'Key': 'RECORD_TYPE',
                            'Values': ['Usage', 'Support']
                        }
                    }
                ]
            }
        )
        
        results = response.get('ResultsByTime', [])
        
        if not results:
            logger.debug(f"No cost data for account {account_id} in {month}")
            return []
        
        groups = results[0].get('Groups', [])
        cost_items = []
        
        for group in groups:
            keys = group.get('Keys', [])
            metrics = group.get('Metrics', {})
            
            cost_value = metrics.get(cost_type, {}).get('Amount', '0')
            usage_quantity = metrics.get('UsageQuantity', {}).get('Amount', '0')
            
            item = {
                'serviceName': keys[0] if len(keys) > 0 else 'Unknown',
                'usageType': keys[1] if len(keys) > 1 else 'Unknown',
                'cost': float(cost_value),
                'usageQuantity': float(usage_quantity),
                'currency': 'USD'
            }
            
            cost_items.append(item)
        
        logger.debug(f"Found {len(cost_items)} cost items for account {account_id}")
        return cost_items
    
    except ClientError as e:
        logger.error(f"Failed to get costs for account {account_id}: {e}")
        raise


# ============================================================================
# meshStack Operations
# ============================================================================

def prepare_payload(
    account_id: str,
    account_name: str,
    cost_items: List[Dict],
    month: str,
    platform_id: str
) -> Dict:
    """
    Prepares a meshResourceUsageReport payload for meshStack.
    
    Args:
        account_id: AWS account ID
        account_name: AWS account name
        cost_items: List of cost items
        month: Month in YYYY-MM format
        platform_id: Platform identifier
        
    Returns:
        Dict with meshStack payload structure
    """
    line_items = [
        {
            'meterName': item['serviceName'],
            'meterCategory': 'AWS',
            'quantity': item['usageQuantity'],
            'cost': item['cost'],
            'currency': item['currency'],
            'usageType': item['usageType']
        }
        for item in cost_items
    ]
    
    payload = {
        'apiVersion': 'v1',
        'kind': 'meshResourceUsageReport',
        'fullPlatformIdentifier': platform_id,
        'source': 'AWS',
        'lineItems': line_items
    }
    
    return payload


def send_to_meshstack(
    meshfed_url: str,
    api_user: str,
    api_secret: str,
    account_id: str,
    month: str,
    payload: Dict
) -> bool:
    """
    Sends a usage report to meshStack via the MeshFed API.
    
    Args:
        meshfed_url: meshStack MeshFed API base URL
        api_user: API username
        api_secret: API password
        account_id: AWS account ID (used in URL path)
        month: Month in YYYY-MM format (used in URL path)
        payload: meshResourceUsageReport payload
        
    Returns:
        True if successful, False otherwise
    """
    # Format the date for the API: YYYY-MM-DD (first day of month)
    report_date = f"{month}-01"
    
    url = f"{meshfed_url}/api/meshobjects/meshresourceusagereports/{account_id}/{report_date}Z"
    
    headers = {
        'Content-Type': 'application/vnd.meshcloud.api.meshobjects.v1+json;charset=UTF-8',
        'Accept': 'application/vnd.meshcloud.api.meshobjects.v1+json'
    }
    
    # Create session with retry strategy
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["PUT"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    try:
        response = session.put(
            url,
            json=payload,
            auth=(api_user, api_secret),
            headers=headers,
            timeout=30
        )
        
        if response.status_code in (200, 204):
            logger.info(f"✅ Successfully sent usage report for {account_id}/{month}")
            logger.debug(f"Response: {response.text}")
            return True
        else:
            logger.error(
                f"❌ Failed to send usage report for {account_id}/{month}: "
                f"HTTP {response.status_code} - {response.text}"
            )
            return False
    
    except requests.RequestException as e:
        logger.error(f"❌ Error sending to meshStack for {account_id}/{month}: {e}")
        return False


# ============================================================================
# Main Orchestration
# ============================================================================

async def process_account_for_month(
    ce_client,
    account_id: str,
    account_name: str,
    month: str,
    config: Dict
) -> bool:
    """
    Processes cost data for a single account and month.
    
    Args:
        ce_client: Cost Explorer client
        account_id: AWS account ID
        account_name: AWS account name
        month: Month in YYYY-MM format
        config: Full configuration dict
        
    Returns:
        True if successful, False otherwise
    """
    aws_config = config['aws']
    meshstack_config = config['meshstack']
    
    try:
        logger.info(f"📦 Processing {account_name} ({account_id}) for {month}")
        
        # Get cost data
        cost_items = get_costs_for_account_for_month(
            ce_client,
            account_id,
            month,
            cost_type=aws_config['cost_type']
        )
        
        if not cost_items:
            logger.warning(f"⚠️ No cost data for {account_id}/{month}, skipping")
            return True
        
        logger.info(f"📊 Found {len(cost_items)} cost items")
        
        # Prepare payload
        payload = prepare_payload(
            account_id=account_id,
            account_name=account_name,
            cost_items=cost_items,
            month=month,
            platform_id=meshstack_config['platform_id']
        )
        
        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
        
        # Send to meshStack
        success = send_to_meshstack(
            meshfed_url=meshstack_config['meshfed_url'],
            api_user=meshstack_config['api_user'],
            api_secret=meshstack_config['api_secret'],
            account_id=account_id,
            month=month,
            payload=payload
        )
        
        return success
    
    except Exception as e:
        logger.error(f"❌ Error processing account {account_id}: {e}")
        return False


def main():
    """
    Main execution function that orchestrates the AWS cost collection and
    meshStack reporting process.
    
    Process flow:
    1. Load and validate configuration
    2. Initialize AWS clients
    3. Fetch all active AWS accounts
    4. For each account, collect cost data for current/last month
    5. Send collected data to meshStack
    """
    try:
        # Load configuration
        config = load_aws_config()
        
        # Initialize clients
        ce_client, org_client = get_aws_clients(config['aws']['region'])
        
        # List accounts
        accounts = list_accounts(
            org_client,
            account_ids=config['aws']['linked_accounts']
        )
        
        if not accounts:
            logger.warning("No AWS accounts found to process")
            return
        
        # Determine periods to process
        current_month, last_month, should_process_last = get_current_and_last_month()
        
        periods = [current_month]
        if should_process_last:
            periods.append(last_month)
        
        logger.info(f"Processing periods: {periods}")
        
        # Process each account
        success_count = 0
        total_count = 0
        
        for account in accounts:
            for month in periods:
                total_count += 1
                
                try:
                    # Note: using sync version here since we're not in async context
                    # If you need async, wrap this in asyncio.run()
                    success = False
                    
                    aws_config = config['aws']
                    meshstack_config = config['meshstack']
                    
                    logger.info(f"📦 Processing {account['Name']} ({account['Id']}) for {month}")
                    
                    # Get cost data
                    cost_items = get_costs_for_account_for_month(
                        ce_client,
                        account['Id'],
                        month,
                        cost_type=aws_config['cost_type']
                    )
                    
                    if not cost_items:
                        logger.warning(f"⚠️ No cost data for {account['Id']}/{month}, skipping")
                        success = True
                    else:
                        logger.info(f"📊 Found {len(cost_items)} cost items")
                        
                        # Prepare payload
                        payload = prepare_payload(
                            account_id=account['Id'],
                            account_name=account['Name'],
                            cost_items=cost_items,
                            month=month,
                            platform_id=meshstack_config['platform_id']
                        )
                        
                        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
                        
                        # Send to meshStack
                        success = send_to_meshstack(
                            meshfed_url=meshstack_config['meshfed_url'],
                            api_user=meshstack_config['api_user'],
                            api_secret=meshstack_config['api_secret'],
                            account_id=account['Id'],
                            month=month,
                            payload=payload
                        )
                    
                    if success:
                        success_count += 1
                
                except Exception as e:
                    logger.error(f"❌ Error processing {account['Id']}/{month}: {e}")
        
        # Summary
        logger.info(f"🎉 Processing complete: {success_count}/{total_count} reports sent successfully")
        
        if success_count == total_count:
            sys.exit(0)
        else:
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"🔥 Unhandled error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
