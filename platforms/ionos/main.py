import os
import sys
import logging
import base64
from typing import Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.append('/app/core')
from meshstack_client import MeshStackClient, prepare_payload
from utils import get_current_and_last_month, format_date_for_meshstack, should_process_last_month
from logging_config import setup_logging


def create_ionos_auth_headers() -> Dict[str, str]:
    """
    Creates HTTP Basic Auth headers for IONOS API.
    
    Reads IONOS_USERNAME and IONOS_PASSWORD from environment variables
    and creates a properly formatted Basic Auth header.
    
    Returns:
        Dict with 'Authorization' header containing Basic auth credentials
        
    Raises:
        ValueError: If IONOS_USERNAME or IONOS_PASSWORD is not set
    """
    username = os.environ.get('IONOS_USERNAME', '').strip()
    password = os.environ.get('IONOS_PASSWORD', '').strip()
    
    if not username:
        raise ValueError("IONOS_USERNAME environment variable is not set or empty")
    if not password:
        raise ValueError("IONOS_PASSWORD environment variable is not set or empty")
    
    # Encode credentials in Base64 for Basic Auth
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode('utf-8')
    
    logging.debug("IONOS Basic Auth header created successfully")
    
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json"
    }


def validate_ionos_credentials() -> None:
    """
    Validates that all required IONOS credentials are set.
    
    Required environment variables:
        - IONOS_USERNAME: IONOS account username/email
        - IONOS_PASSWORD: IONOS account password
        - IONOS_CONTRACT: IONOS contract/account ID
    
    Raises:
        ValueError: If any required credential is missing or empty
    """
    username = os.environ.get('IONOS_USERNAME', '').strip()
    password = os.environ.get('IONOS_PASSWORD', '').strip()
    contract = os.environ.get('IONOS_CONTRACT', '').strip()
    
    missing_vars = []
    if not username:
        missing_vars.append("IONOS_USERNAME")
    if not password:
        missing_vars.append("IONOS_PASSWORD")
    if not contract:
        missing_vars.append("IONOS_CONTRACT")
    
    if missing_vars:
        raise ValueError(
            f"Missing required IONOS environment variables: {', '.join(missing_vars)}. "
            "Please configure these in your .env file or environment."
        )
    
    logging.info("IONOS credentials validated successfully")


def create_ionos_session(timeout: int = 30, max_retries: int = 3) -> requests.Session:
    """
    Creates a requests.Session with retry strategy and timeout configuration.
    
    Args:
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts (default: 3)
        
    Returns:
        Configured requests.Session with retry strategy
    """
    session = requests.Session()
    
    # Configure retry strategy with exponential backoff
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=1,  # 1, 2, 4 seconds between retries
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    
    # Mount the retry strategy to both HTTP and HTTPS
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Store timeout for later use
    session.timeout = timeout
    
    logging.debug(f"IONOS session created with timeout={timeout}s, max_retries={max_retries}")
    
    return session



def get_ionos_product_costs(session: Optional[requests.Session] = None, timeout: int = 30) -> Dict:
    """
    Retrieves IONOS product costs from the billing API.
    
    Args:
        session: Optional requests.Session with retry strategy
        timeout: Request timeout in seconds (default: 30)
        
    Returns:
        Dict containing IONOS products with pricing information
        
    Raises:
        ValueError: If IONOS credentials are missing
        requests.RequestException: If API call fails
    """
    ionos_host = os.environ.get('IONOS_API_URL', 'https://api.ionos.com')
    contract = os.environ.get('IONOS_CONTRACT', '').strip()
    
    if not contract:
        raise ValueError("IONOS_CONTRACT environment variable is not set or empty")
    
    # Create session if not provided
    if session is None:
        session = create_ionos_session(timeout=timeout)
    
    # Get authentication headers
    headers = create_ionos_auth_headers()
    
    try:
        url = f"{ionos_host}/billing/{contract}/products"
        logging.info(f"Fetching IONOS products from {url}")
        
        response = session.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        logging.info("Successfully retrieved IONOS product catalog")
        return response.json()
        
    except requests.exceptions.Timeout as err:
        logging.error(f"IONOS API timeout after {timeout} seconds: {err}")
        raise
    except requests.exceptions.ConnectionError as err:
        logging.error(f"IONOS API connection error: {err}")
        raise
    except requests.exceptions.HTTPError as err:
        status_code = err.response.status_code if hasattr(err, 'response') and err.response else 'Unknown'
        if status_code == 401:
            logging.error("IONOS API: 401 Unauthorized - Invalid credentials")
        elif status_code == 403:
            logging.error("IONOS API: 403 Forbidden - User may not have billing access")
        else:
            logging.error(f"IONOS API HTTP error: {err}")
        raise
    except Exception as err:
        logging.error(f"Error retrieving IONOS product costs: {err}")
        raise


def get_ionos_usage(month: str, session: Optional[requests.Session] = None, timeout: int = 30) -> Dict:
    """
    Retrieves IONOS usage data for a specified period.
    
    Args:
        month: Period in YYYY-MM format (e.g., '2024-02')
        session: Optional requests.Session with retry strategy
        timeout: Request timeout in seconds (default: 30)
        
    Returns:
        Dict containing IONOS usage data by datacenter
        
    Raises:
        ValueError: If IONOS credentials are missing
        requests.RequestException: If API call fails
    """
    ionos_host = os.environ.get('IONOS_API_URL', 'https://api.ionos.com')
    contract = os.environ.get('IONOS_CONTRACT', '').strip()
    
    if not contract:
        raise ValueError("IONOS_CONTRACT environment variable is not set or empty")
    
    # Create session if not provided
    if session is None:
        session = create_ionos_session(timeout=timeout)
    
    # Get authentication headers
    headers = create_ionos_auth_headers()
    
    try:
        url = f"{ionos_host}/billing/{contract}/usage"
        logging.info(f"Fetching IONOS usage for period {month}")
        
        response = session.get(url, params={"period": month}, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        logging.info(f"Successfully retrieved IONOS usage data for {month}")
        return response.json()
        
    except requests.exceptions.Timeout as err:
        logging.error(f"IONOS API timeout after {timeout} seconds: {err}")
        raise
    except requests.exceptions.ConnectionError as err:
        logging.error(f"IONOS API connection error: {err}")
        raise
    except requests.exceptions.HTTPError as err:
        status_code = err.response.status_code if hasattr(err, 'response') and err.response else 'Unknown'
        if status_code == 401:
            logging.error("IONOS API: 401 Unauthorized - Invalid credentials")
        elif status_code == 403:
            logging.error("IONOS API: 403 Forbidden - User may not have billing access")
        else:
            logging.error(f"IONOS API HTTP error: {err}")
        raise
    except Exception as err:
        logging.error(f"Error retrieving IONOS usage: {err}")
        raise


def get_ionos_price_groups(month: str, session: Optional[requests.Session] = None, timeout: int = 30) -> Dict[str, str]:
    """
    Retrieves IONOS price group information from the billing invoices API.
    
    Price groups are IONOS's way of categorizing products by pricing tier (e.g., PG 1, PG A, PG C1, etc.).
    This information is extracted from invoices which include the productGroup field for each meter.
    
    Args:
        month: Period in YYYY-MM format (e.g., '2024-02')
        session: Optional requests.Session with retry strategy
        timeout: Request timeout in seconds (default: 30)
        
    Returns:
        Dict mapping meterId -> priceGroup (e.g., {"C01000": "PG 1", "C010EU": "PG 1"})
        Returns empty dict if no price group data is available
        
    Raises:
        ValueError: If IONOS credentials are missing
        requests.RequestException: If API call fails
    """
    ionos_host = os.environ.get('IONOS_API_URL', 'https://api.ionos.com')
    contract = os.environ.get('IONOS_CONTRACT', '').strip()
    
    if not contract:
        raise ValueError("IONOS_CONTRACT environment variable is not set or empty")
    
    # Create session if not provided
    if session is None:
        session = create_ionos_session(timeout=timeout)
    
    # Get authentication headers
    headers = create_ionos_auth_headers()
    
    try:
        url = f"{ionos_host}/billing/invoices/{month}"
        params = {"contractid": contract}
        
        logging.debug(f"Fetching IONOS invoices for price group information from {url}")
        
        response = session.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        invoices = response.json()
        if not invoices:
            logging.warning(f"No invoices found for period {month}")
            return {}
        
        # Aggregate price groups from all invoices and datacenters
        price_groups_map = {}
        
        if isinstance(invoices, list):
            # Response is a list of invoices
            for invoice in invoices:
                datacenters = invoice.get('datacenters', [])
                for datacenter in datacenters:
                    meters = datacenter.get('meters', [])
                    for meter in meters:
                        meter_id = meter.get('meterId', '')
                        price_group = meter.get('productGroup', '')
                        if meter_id and price_group:
                            price_groups_map[meter_id] = price_group
                            logging.debug(f"Mapped meterId {meter_id} to priceGroup {price_group}")
        elif isinstance(invoices, dict) and 'datacenters' in invoices:
            # Response is a single invoice object
            datacenters = invoices.get('datacenters', [])
            for datacenter in datacenters:
                meters = datacenter.get('meters', [])
                for meter in meters:
                    meter_id = meter.get('meterId', '')
                    price_group = meter.get('productGroup', '')
                    if meter_id and price_group:
                        price_groups_map[meter_id] = price_group
                        logging.debug(f"Mapped meterId {meter_id} to priceGroup {price_group}")
        
        logging.info(f"Successfully retrieved {len(price_groups_map)} price group mappings")
        return price_groups_map
        
    except requests.exceptions.Timeout as err:
        logging.error(f"IONOS API timeout after {timeout} seconds: {err}")
        raise
    except requests.exceptions.ConnectionError as err:
        logging.error(f"IONOS API connection error: {err}")
        raise
    except requests.exceptions.HTTPError as err:
        status_code = err.response.status_code if hasattr(err, 'response') and err.response else 'Unknown'
        if status_code == 401:
            logging.error("IONOS API: 401 Unauthorized - Invalid credentials")
        elif status_code == 403:
            logging.error("IONOS API: 403 Forbidden - User may not have billing access")
        else:
            logging.error(f"IONOS API HTTP error: {err}")
        raise
    except Exception as err:
        logging.error(f"Error retrieving IONOS price groups: {err}")
        raise


def calculate_datacenter_costs(usage_data: Dict, products: Dict, include_product_group: bool = False, price_groups_map: Dict[str, str] = {}) -> List[Dict]:
    results = []
    
    for datacenter in usage_data.get('datacenters', []):
        meters = []
        
        for meter in datacenter.get('meters', []):
            matched_product = None
            meter_desc = meter.get('meterDesc', '')
            
            for product in products.get('products', []):
                product_meter_desc = product.get('meterDesc', '')
                if product_meter_desc and meter_desc and product_meter_desc in meter_desc:
                    matched_product = product
                    break
            
            quantity_data = meter.get('quantity', {})
            quantity = float(quantity_data.get('quantity', 0))
            
            if matched_product:
                unit_cost_data = matched_product.get('unitCost', {})
                unit_cost = float(unit_cost_data.get('quantity', 0))
                total_cost = round(quantity * unit_cost, 2)
            else:
                unit_cost = 0
                total_cost = 0
            
            meter_info = {
                'meterId': meter.get('meterId'),
                'meterDesc': meter_desc,
                'quantity': quantity,
                'unit': quantity_data.get('unit', ''),
                'totalCost': total_cost,
                'unitCost': unit_cost
            }
            
            # Add product group if enabled and available
            if include_product_group and matched_product:
                product_group = matched_product.get('productGroup', '')
                if product_group:
                    meter_info['productGroup'] = product_group
            
            # Add price group if available from invoice data
            if price_groups_map:
                meter_id = meter.get('meterId', '')
                price_group = price_groups_map.get(meter_id, '')
                if price_group:
                    meter_info['priceGroup'] = price_group
            
            meters.append(meter_info)
        
        results.append({
            'id': datacenter.get('id'),
            'name': datacenter.get('name'),
            'meters': meters
        })
    
    return results


def transform_ionos_to_line_items(meters: List[Dict], include_product_group: bool = False) -> List[Dict]:
    line_items = []
    
    for meter in meters:
        if meter['totalCost'] > 0:
            # Build base usageType
            usage_type = f"IONOS Service {meter['meterId']}"
            
            # Prepend price group as prefix if available
            if 'priceGroup' in meter and meter['priceGroup']:
                usage_type = f"{meter['priceGroup']} - {usage_type}"
            
            line_item = {
                "productName": meter['meterDesc'],
                "usageQuantity": meter['quantity'],
                "usageType": usage_type,
                "usageCost": meter['totalCost'],
                "currency": "EUR",
                "usageUnit": meter['unit'],
                "totalCost": meter['totalCost'],
                "sellerId": "IONOS"
            }
            
            # Add product group to line item if enabled and available
            if include_product_group and 'productGroup' in meter:
                line_item['productGroup'] = meter['productGroup']
            
            line_items.append(line_item)
    
    return line_items


def process_month(
    mesh_client: MeshStackClient,
    platform_id: str,
    month: str,
    include_product_group: bool = False,
    include_price_group: bool = False,
    session: Optional[requests.Session] = None,
    timeout: int = 30
) -> None:
    """
    Processes IONOS costs for a specified month.
    
    Args:
        mesh_client: meshStack API client
        platform_id: Platform identifier in meshStack
        month: Period in YYYY-MM format
        include_product_group: Whether to include product group information
        include_price_group: Whether to include price group information from invoices
        session: Optional requests.Session with retry strategy
        timeout: Request timeout in seconds
    """
    logging.info(f"Processing IONOS costs for {month}")
    
    products = get_ionos_product_costs(session=session, timeout=timeout)
    usage = get_ionos_usage(month, session=session, timeout=timeout)
    
    # Fetch price groups if enabled
    price_groups_map = {}
    if include_price_group:
        logging.info("Fetching IONOS price group information from invoices")
        try:
            price_groups_map = get_ionos_price_groups(month, session=session, timeout=timeout)
            if price_groups_map:
                logging.info(f"Successfully retrieved {len(price_groups_map)} price group mappings")
            else:
                logging.warning("No price group data available from invoices API")
        except Exception as err:
            logging.error(f"Failed to retrieve price groups: {err}")
            raise
    
    datacenter_costs = calculate_datacenter_costs(usage, products, include_product_group, price_groups_map)
    
    meshstack_date = format_date_for_meshstack(month)
    
    for datacenter in datacenter_costs:
        datacenter_id = datacenter['id']
        logging.info(f"Processing datacenter {datacenter_id}")
        
        line_items = transform_ionos_to_line_items(datacenter['meters'], include_product_group)
        
        if not line_items:
            logging.info(f"No costs for datacenter {datacenter_id} in {month}")
            continue
        
        payload = prepare_payload(line_items, platform_id, "IONOS")
        
        response = mesh_client.submit_usage_report(datacenter_id, meshstack_date, payload)
        
        if response['status'] == 'success':
            logging.info(f"Successfully submitted report for datacenter {datacenter_id}")
        else:
            logging.error(f"Failed to submit report for {datacenter_id}: {response.get('message')}")


def main():
    setup_logging(
        level=os.environ.get('LOG_LEVEL', 'INFO'),
        loki_url=os.environ.get('LOKI_URL'),
        platform_name='ionos'
    )
    
    logging.info("Starting IONOS metering collection")
    
    # Validate IONOS credentials early
    try:
        validate_ionos_credentials()
    except ValueError as err:
        logging.error(f"IONOS configuration error: {err}")
        raise
    
    meshfed_host = os.environ.get('MESHSTACK_MESHFED_URL', os.environ.get('MESHSTACK_API_URL', ''))
    kraken_host = os.environ.get('MESHSTACK_KRAKEN_URL', os.environ.get('MESHSTACK_API_URL', ''))
    mesh_user = os.environ['MESHSTACK_API_USER']
    mesh_secret = os.environ['MESHSTACK_API_SECRET']
    platform_id = os.environ['PLATFORM_ID']
    usage_period = os.environ.get('USAGE_PERIOD')
    
    # Read configuration for product group feature
    include_product_group = os.environ.get('IONOS_INCLUDE_PRODUCT_GROUP', 'false').lower() == 'true'
    if include_product_group:
        logging.info("Product group information will be included in line items")
    
    # Read configuration for price group feature
    include_price_group = os.environ.get('IONOS_INCLUDE_PRICE_GROUP', 'true').lower() == 'true'
    if include_price_group:
        logging.info("Price group information will be included in usageType")
    
    # Read IONOS API timeout configuration
    try:
        timeout = int(os.environ.get('IONOS_API_TIMEOUT', '30'))
        max_retries = int(os.environ.get('IONOS_API_RETRIES', '3'))
    except ValueError:
        logging.warning("Invalid timeout/retries configuration, using defaults")
        timeout = 30
        max_retries = 3
    
    logging.info(f"IONOS API timeout configured to {timeout}s, max retries: {max_retries}")
    
    mesh_client = MeshStackClient(meshfed_host, kraken_host, mesh_user, mesh_secret)
    
    # Create reusable session with retry strategy and timeout
    session = create_ionos_session(timeout=timeout, max_retries=max_retries)
    
    months = get_current_and_last_month(usage_period)
    months_to_process = [months['current_month']]
    
    if should_process_last_month():
        months_to_process.append(months['last_month'])
        logging.info("Processing both current and last month (first 5 days)")
    
    try:
        for month in months_to_process:
            process_month(
                mesh_client,
                platform_id,
                month,
                include_product_group=include_product_group,
                include_price_group=include_price_group,
                session=session,
                timeout=timeout
            )
    finally:
        session.close()
        logging.debug("IONOS session closed")
    
    logging.info("IONOS metering collection completed")


if __name__ == '__main__':
    main()
