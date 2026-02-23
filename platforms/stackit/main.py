import os
import sys
import logging
from typing import Dict, List
import requests

sys.path.append('/app/core')
from meshstack_client import MeshStackClient, prepare_payload
from utils import get_current_and_last_month, format_date_for_meshstack, should_process_last_month
from logging_config import setup_logging


def get_stackit_projects(container_parent_id: str) -> Dict:
    stackit_token = os.environ.get('STACKIT_SERVICE_ACCOUNT_TOKEN')
    url = f"https://resource-manager.api.stackit.cloud/v2/projects"
    params = {"containerParentId": container_parent_id}
    
    logging.debug(f"Fetching STACKIT projects - URL: {url}, Params: {params}")
    
    try:
        response = requests.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {stackit_token}",
                "Accept": "application/json"
            }
        )
        logging.debug(f"STACKIT projects API response status: {response.status_code}")
        response.raise_for_status()
        data = response.json()
        logging.debug(f"STACKIT projects API response: {data}")
        
        active_projects = [
            p for p in data.get('items', [])
            if p.get('lifecycleState') == 'ACTIVE'
        ]
        logging.debug(f"Found {len(active_projects)} active projects")
        
        return {
            "status": "success",
            "projects": active_projects
        }
    except Exception as err:
        logging.error(f"Error retrieving STACKIT projects: {err}")
        return {
            "status": "failure",
            "message": str(err)
        }


def get_stackit_costs(container_parent_id: str, from_date: str, to_date: str) -> Dict:
    stackit_token = os.environ.get('STACKIT_SERVICE_ACCOUNT_TOKEN')
    url = f"https://cost.api.stackit.cloud/v3/costs/{container_parent_id}"
    params = {
        "from": from_date,
        "to": to_date,
        "granularity": "monthly",
        "depth": "service"
    }
    
    logging.debug(f"Fetching STACKIT costs - URL: {url}, Params: {params}")
    
    try:
        response = requests.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {stackit_token}",
                "Accept": "application/json"
            }
        )
        logging.debug(f"STACKIT costs API response status: {response.status_code}")
        response.raise_for_status()
        data = response.json()
        logging.debug(f"STACKIT costs API response: {data}")
        
        return {
            "status": "success",
            "result": data
        }
    except Exception as err:
        logging.error(f"Error retrieving STACKIT costs: {err}")
        return {
            "status": "failure",
            "message": str(err)
        }


def transform_stackit_to_line_items(cost_data: Dict, seller_id: str, seller_product_group: str) -> List[Dict]:
    line_items = []
    
    services = cost_data.get('services', [])
    logging.debug(f"Transforming {len(services)} services to line items")
    
    for service in services:
        service_name = service.get('serviceName', 'Unknown')
        service_category = service.get('serviceCategoryName', '')
        unit_label = service.get('unitLabel', '')
        
        logging.debug(f"Processing service: {service_name}, category: {service_category}")
        
        for item in service.get('reportData', []):
            quantity = item.get('quantity', 0)
            charge_cents = item.get('charge', 0)
            total_cost = charge_cents / 100
            
            if quantity == 0:
                usage_cost = 0
            else:
                usage_cost = total_cost / quantity
            
            line_item = {
                "productName": service_name,
                "usageQuantity": quantity,
                "usageType": service_category,
                "usageCost": round(usage_cost, 2),
                "currency": "EUR",
                "usageUnit": unit_label,
                "totalCost": round(total_cost, 2),
                "sellerId": seller_id,
                "sellerProductGroup": seller_product_group
            }
            logging.debug(f"Created line item: {line_item}")
            line_items.append(line_item)
    
    logging.debug(f"Total line items created: {len(line_items)}")
    return line_items


def process_project_costs(
    mesh_client: MeshStackClient,
    platform_id: str,
    container_parent_id: str,
    month: str,
    seller_id: str,
    seller_product_group: str
) -> None:
    logging.info(f"Processing STACKIT costs for container {container_parent_id}, month {month}")
    
    from datetime import datetime
    date_obj = datetime.strptime(month, "%Y-%m")
    from_date = date_obj.strftime("%Y-%m-01")
    
    import calendar
    last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
    to_date = date_obj.strftime(f"%Y-%m-{last_day:02d}")
    
    logging.debug(f"Date range: {from_date} to {to_date}")
    
    costs_result = get_stackit_costs(container_parent_id, from_date, to_date)
    
    if costs_result['status'] != 'success':
        logging.error(f"Failed to get costs: {costs_result.get('message')}")
        return
    
    cost_records = costs_result['result']
    
    if not isinstance(cost_records, list):
        cost_records = [cost_records]
    
    logging.debug(f"Processing {len(cost_records)} cost records")
    
    meshstack_date = format_date_for_meshstack(month)
    logging.debug(f"MeshStack formatted date: {meshstack_date}")
    
    for record in cost_records:
        project_id = record.get('projectId')
        
        if not project_id:
            logging.warning("Skipping record without projectId")
            continue
        
        logging.info(f"Processing project {project_id}")
        
        line_items = transform_stackit_to_line_items(record, seller_id, seller_product_group)
        
        if not line_items:
            logging.info(f"No costs for project {project_id} in {month}")
            continue
        
        logging.debug(f"Prepared {len(line_items)} line items for project {project_id}")
        
        payload = prepare_payload(line_items, platform_id, "StackIT")
        logging.debug(f"Payload for project {project_id}: {payload}")
        
        response = mesh_client.submit_usage_report(project_id, meshstack_date, payload)
        
        if response['status'] == 'success':
            logging.info(f"Successfully submitted report for project {project_id}")
        else:
            logging.error(f"Failed to submit report for {project_id}: {response.get('message')}")


def main():
    setup_logging(
        level=os.environ.get('LOG_LEVEL', 'INFO'),
        loki_url=os.environ.get('LOKI_URL'),
        platform_name='stackit'
    )
    
    logging.info("Starting STACKIT metering collection")
    
    meshfed_host = os.environ['MESHSTACK_MESHFED_URL']
    kraken_host = os.environ['MESHSTACK_KRAKEN_URL']
    mesh_user = os.environ['MESHSTACK_API_USER']
    mesh_secret = os.environ['MESHSTACK_API_SECRET']
    platform_id = os.environ['PLATFORM_ID']
    container_parent_ids = os.environ['CONTAINER_PARENT_IDS'].split(',')
    usage_period = os.environ.get('USAGE_PERIOD')
    seller_id = os.environ.get('STACKIT_SELLER_ID', "STACKIT")
    seller_product_group = os.environ.get('STACKIT_SELLER_PRODUCT_GROUP', "STACKIT")

    
    mesh_client = MeshStackClient(meshfed_host, kraken_host, mesh_user, mesh_secret)
    
    months = get_current_and_last_month(usage_period)
    months_to_process = [months['current_month']]
    
    if should_process_last_month():
        months_to_process.append(months['last_month'])
        logging.info("Processing both current and last month (first 5 days)")
    
    for container_parent_id in container_parent_ids:
        logging.info(f"Processing container parent ID: {container_parent_id}")
        
        for month in months_to_process:
            process_project_costs(mesh_client, platform_id, container_parent_id.strip(), month, seller_id, seller_product_group)
    
    logging.info("STACKIT metering collection completed")


if __name__ == '__main__':
    main()
