import os
import sys
import logging
from typing import Dict, List
import requests

sys.path.append('/app/core')
from meshstack_client import MeshStackClient, prepare_payload
from utils import get_current_and_last_month, format_date_for_meshstack, should_process_last_month
from logging_config import setup_logging


def get_tencent_costs(tenant_id: str, month: str) -> Dict:
    tencent_host = os.environ.get('TENCENT_API_URL', 'http://tencent-mock:5001')
    
    try:
        response = requests.get(
            f"{tencent_host}/billing/{tenant_id}",
            params={"month": month}
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'success':
            return {
                "status": "success",
                "result": data.get('costs', [])
            }
        else:
            return {
                "status": "failure",
                "message": data.get('message', 'Unknown error')
            }
    except Exception as err:
        logging.error(f"Error retrieving Tencent costs: {err}")
        return {
            "status": "failure",
            "message": str(err)
        }


def transform_tencent_to_line_items(costs: List[Dict]) -> List[Dict]:
    line_items = []
    
    for cost_item in costs:
        line_items.append({
            "productName": cost_item.get("BusinessCodeName", "Unknown"),
            "usageQuantity": cost_item.get("UsedAmount", 0),
            "usageType": cost_item.get("PriceUnit", ""),
            "usageCost": cost_item.get("SinglePrice", 0),
            "currency": "USD",
            "usageUnit": cost_item.get("UsedAmountUnit", ""),
            "totalCost": cost_item.get("RealCost", 0),
            "sellerId": "Tencent Cloud"
        })
    
    return line_items


def process_tenant(
    mesh_client: MeshStackClient,
    tenant_id: str,
    platform_id: str,
    month: str
) -> Dict:
    logging.info(f"Processing tenant {tenant_id} for {month}")
    
    result = get_tencent_costs(tenant_id, month)
    
    if result['status'] != 'success':
        logging.error(f"Failed to get costs for {tenant_id}: {result.get('message')}")
        return result
    
    costs = result['result']
    
    if not costs:
        logging.info(f"No costs for tenant {tenant_id} in {month}")
        return {"status": "success", "message": "No costs"}
    
    line_items = transform_tencent_to_line_items(costs)
    payload = prepare_payload(line_items, platform_id, "Tencent integration")
    
    meshstack_date = format_date_for_meshstack(month)
    response = mesh_client.submit_usage_report(tenant_id, meshstack_date, payload)
    
    if response['status'] == 'success':
        logging.info(f"Successfully submitted report for {tenant_id}")
    else:
        logging.error(f"Failed to submit report for {tenant_id}: {response.get('message')}")
    
    return response


def main():
    setup_logging(
        level=os.environ.get('LOG_LEVEL', 'INFO'),
        loki_url=os.environ.get('LOKI_URL'),
        platform_name='tencent'
    )
    
    logging.info("Starting Tencent metering collection")
    
    meshfed_host = os.environ['MESHSTACK_MESHFED_URL']
    kraken_host = os.environ['MESHSTACK_KRAKEN_URL']
    mesh_user = os.environ['MESHSTACK_API_USER']
    mesh_secret = os.environ['MESHSTACK_API_SECRET']
    platform_id = os.environ['PLATFORM_ID']
    usage_period = os.environ.get('USAGE_PERIOD')
    
    mesh_client = MeshStackClient(meshfed_host, kraken_host, mesh_user, mesh_secret)
    
    logging.info(f"Fetching tenants for platform {platform_id}")
    tenants_result = mesh_client.get_tenants(platform_id)
    
    if tenants_result['status'] != 'success':
        logging.error(f"Failed to fetch tenants: {tenants_result.get('message')}")
        sys.exit(1)
    
    tenant_ids = tenants_result['tenant_ids']
    logging.info(f"Found {len(tenant_ids)} tenants")
    
    months = get_current_and_last_month(usage_period)
    months_to_process = [months['current_month']]
    
    if should_process_last_month():
        months_to_process.append(months['last_month'])
        logging.info("Processing both current and last month (first 5 days)")
    
    for tenant_id in tenant_ids:
        for month in months_to_process:
            process_tenant(mesh_client, tenant_id, platform_id, month)
    
    logging.info("Tencent metering collection completed")


if __name__ == '__main__':
    main()
