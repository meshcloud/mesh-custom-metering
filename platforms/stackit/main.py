import os
import sys
import logging
import calendar
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List
import requests
from stackit_auth import build_stackit_auth

STACKIT_COST_API_BASE_URL = "https://cost.api.stackit.cloud"

# We have to load the core libraries from different locations depending on whether its running in Docker or not.
DOCKER_CORE_PATH = Path('/app/core')
LOCAL_CORE_PATH = Path(__file__).parent.parent.parent / 'src' / 'core'
sys.path.append(str(DOCKER_CORE_PATH if DOCKER_CORE_PATH.is_dir() else LOCAL_CORE_PATH))
from meshstack_client import MeshStackClient, prepare_payload
from utils import get_current_and_last_month, format_date_for_meshstack, should_process_last_month
from logging_config import setup_logging


def get_stackit_costs(auth: requests.auth.AuthBase, container_parent_id: str, from_date: date, to_date: date) -> Dict:
    logging.debug(f"Fetching STACKIT costs - customer account: {container_parent_id}, from: {from_date}, to: {to_date}")

    try:
        response = requests.get(
            f"{STACKIT_COST_API_BASE_URL}/v3/costs/{container_parent_id}",
            params={
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "granularity": "monthly",
                "depth": "service",
            },
            headers={"Accept": "application/json"},
            auth=auth,
        )
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


def transform_stackit_to_line_items(cost_data: Dict) -> List[Dict]:
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
                "sellerId": "STACKIT"
            }
            logging.debug(f"Created line item: {line_item}")
            line_items.append(line_item)

    logging.debug(f"Total line items created: {len(line_items)}")
    return line_items


def process_project_costs(
    mesh_client: MeshStackClient,
    auth: requests.auth.AuthBase,
    platform_id: str,
    container_parent_id: str,
    month: str
) -> None:
    logging.info(f"Processing STACKIT costs for container {container_parent_id}, month {month}")

    date_obj = datetime.strptime(month, "%Y-%m")
    from_date = date_obj.date().replace(day=1)
    last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
    to_date = date_obj.date().replace(day=last_day)

    logging.debug(f"Date range: {from_date} to {to_date}")

    costs_result = get_stackit_costs(auth, container_parent_id, from_date, to_date)

    if costs_result['status'] != 'success':
        logging.error(f"Failed to get costs: {costs_result.get('message')}")
        return

    cost_records = costs_result['result']

    logging.debug(f"Processing {len(cost_records)} cost records")

    meshstack_date = format_date_for_meshstack(month)
    logging.debug(f"MeshStack formatted date: {meshstack_date}")

    for record in cost_records:
        project_id = record.get('projectId')

        if not project_id:
            logging.warning("Skipping record without projectId")
            continue

        logging.info(f"Processing project {project_id}")

        line_items = transform_stackit_to_line_items(record)

        if not line_items:
            logging.info(f"No costs for project {project_id} in {month}")
            continue

        logging.debug(f"Prepared {len(line_items)} line items for project {project_id}")

        payload = prepare_payload(line_items, platform_id, "STACKIT")
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

    mesh_client = MeshStackClient(meshfed_host, kraken_host, mesh_user, mesh_secret)

    # Built once so the JWT-bearer exchange (and key JSON parsing) isn't repeated per container/month.
    stackit_auth = build_stackit_auth()

    months = get_current_and_last_month(usage_period)
    months_to_process = [months['current_month']]

    if should_process_last_month():
        months_to_process.append(months['last_month'])
        logging.info("Processing both current and last month (first 5 days)")

    for container_parent_id in container_parent_ids:
        logging.info(f"Processing container parent ID: {container_parent_id}")

        for month in months_to_process:
            process_project_costs(mesh_client, stackit_auth, platform_id, container_parent_id.strip(), month)

    logging.info("STACKIT metering collection completed")


if __name__ == '__main__':
    main()
