import os
import sys
import logging
from typing import Dict, List
import requests

sys.path.append('/app/core')
from meshstack_client import MeshStackClient, prepare_payload
from utils import get_current_and_last_month, format_date_for_meshstack, should_process_last_month
from logging_config import setup_logging


def get_ovh_projects() -> Dict:
    ovh_host = os.environ.get('OVH_API_URL', 'http://ovh-mock:5004')
    
    try:
        response = requests.get(f"{ovh_host}/projects")
        response.raise_for_status()
        data = response.json()
        
        return {
            "status": "success",
            "projects": data.get('projects', [])
        }
    except Exception as err:
        logging.error(f"Error retrieving OVH projects: {err}")
        return {
            "status": "failure",
            "message": str(err)
        }


def get_ovh_usage(project_id: str, from_date: str, to_date: str) -> Dict:
    ovh_host = os.environ.get('OVH_API_URL', 'http://ovh-mock:5004')
    
    try:
        response = requests.get(
            f"{ovh_host}/projects/{project_id}/usage",
            params={
                "from": from_date,
                "to": to_date
            }
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            "status": "success",
            "result": data
        }
    except Exception as err:
        logging.error(f"Error retrieving OVH usage for {project_id}: {err}")
        return {
            "status": "failure",
            "message": str(err)
        }


def transform_ovh_to_line_items(usage_data: Dict) -> List[Dict]:
    line_items = []
    
    resources = usage_data.get('resources', [])
    
    for resource in resources:
        resource_type = resource.get('type', 'Unknown')
        quantity = resource.get('quantity', 0)
        unit = resource.get('unit', '')
        total_cost = resource.get('totalPrice', 0)
        
        if quantity == 0:
            usage_cost = 0
        else:
            usage_cost = total_cost / quantity
        
        line_items.append({
            "productName": resource_type,
            "usageQuantity": quantity,
            "usageType": resource.get('region', 'default'),
            "usageCost": round(usage_cost, 2),
            "currency": "EUR",
            "usageUnit": unit,
            "totalCost": round(total_cost, 2)
        })
    
    return line_items


def process_project(
    mesh_client: MeshStackClient,
    platform_id: str,
    project_id: str,
    month: str
) -> Dict:
    logging.info(f"Processing OVH project {project_id} for {month}")
    
    from datetime import datetime
    import calendar
    
    date_obj = datetime.strptime(month, "%Y-%m")
    from_date = date_obj.strftime("%Y-%m-%d")
    
    last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
    to_date = date_obj.strftime(f"%Y-%m-{last_day:02d}")
    
    result = get_ovh_usage(project_id, from_date, to_date)
    
    if result['status'] != 'success':
        logging.error(f"Failed to get usage for {project_id}: {result.get('message')}")
        return result
    
    usage = result['result']
    
    line_items = transform_ovh_to_line_items(usage)
    
    if not line_items:
        logging.info(f"No usage for project {project_id} in {month}")
        return {"status": "success", "message": "No usage"}
    
    payload = prepare_payload(line_items, platform_id, "OVH")
    
    meshstack_date = format_date_for_meshstack(month)
    response = mesh_client.submit_usage_report(project_id, meshstack_date, payload)
    
    if response['status'] == 'success':
        logging.info(f"Successfully submitted report for {project_id}")
    else:
        logging.error(f"Failed to submit report for {project_id}: {response.get('message')}")
    
    return response


def main():
    setup_logging(
        level=os.environ.get('LOG_LEVEL', 'INFO'),
        loki_url=os.environ.get('LOKI_URL'),
        platform_name='ovh'
    )
    
    logging.info("Starting OVH metering collection")
    
    meshfed_host = os.environ.get('MESHSTACK_MESHFED_URL', os.environ.get('MESHSTACK_API_URL', ''))
    kraken_host = os.environ.get('MESHSTACK_KRAKEN_URL', os.environ.get('MESHSTACK_API_URL', ''))
    mesh_user = os.environ['MESHSTACK_API_USER']
    mesh_secret = os.environ['MESHSTACK_API_SECRET']
    platform_id = os.environ['PLATFORM_ID']
    usage_period = os.environ.get('USAGE_PERIOD')
    
    mesh_client = MeshStackClient(meshfed_host, kraken_host, mesh_user, mesh_secret)
    
    logging.info("Fetching OVH projects")
    projects_result = get_ovh_projects()
    
    if projects_result['status'] != 'success':
        logging.error(f"Failed to fetch projects: {projects_result.get('message')}")
        sys.exit(1)
    
    projects = projects_result['projects']
    logging.info(f"Found {len(projects)} projects")
    
    months = get_current_and_last_month(usage_period)
    months_to_process = [months['current_month']]
    
    if should_process_last_month():
        months_to_process.append(months['last_month'])
        logging.info("Processing both current and last month (first 5 days)")
    
    for project in projects:
        project_id = project.get('projectId')
        
        if not project_id:
            logging.warning("Skipping project without projectId")
            continue
        
        for month in months_to_process:
            process_project(mesh_client, platform_id, project_id, month)
    
    logging.info("OVH metering collection completed")


if __name__ == '__main__':
    main()
