import os
import sys
import logging
from typing import Dict, List
import oci

sys.path.append('/app/core')
from meshstack_client import MeshStackClient, prepare_payload
from utils import get_current_and_last_month, format_date_for_meshstack, should_process_last_month
from logging_config import setup_logging


def get_oci_config() -> Dict:
    config_file = os.environ.get('OCI_CONFIG_FILE')
    config_profile = os.environ.get('OCI_CONFIG_PROFILE', 'DEFAULT')

    if config_file and os.path.exists(config_file):
        return oci.config.from_file(config_file, config_profile)

    return {
        'user': os.environ['OCI_USER_OCID'],
        'key_file': os.environ['OCI_KEY_FILE'],
        'fingerprint': os.environ['OCI_FINGERPRINT'],
        'tenancy': os.environ['OCI_TENANCY_OCID'],
        'region': os.environ['OCI_REGION']
    }


def get_leaf_compartments(root_compartment_id: str, config: Dict) -> List[Dict]:
    identity_client = oci.identity.IdentityClient(config)

    all_compartments = {}

    def recurse(parent_id, path=""):
        try:
            response = identity_client.list_compartments(
                compartment_id=parent_id,
                compartment_id_in_subtree=False,
                lifecycle_state='ACTIVE'
            )

            children = response.data

            for comp in children:
                comp_path = f"{path}/{comp.name}"
                all_compartments[comp.id] = {
                    'id': comp.id,
                    'name': comp.name,
                    'path': comp_path,
                    'parent_id': parent_id,
                    'children': []
                }

                child_comps = recurse(comp.id, comp_path)
                all_compartments[comp.id]['children'] = child_comps

            return [c.id for c in children]

        except Exception as err:
            logging.error(f"Error listing compartments under {parent_id}: {err}")
            return []

    logging.info(f"Starting compartment discovery from root: {root_compartment_id}")
    recurse(root_compartment_id, "root")

    leaf_compartments = [
        comp for comp in all_compartments.values()
        if len(comp['children']) == 0
    ]

    logging.info(f"Found {len(leaf_compartments)} leaf compartments:")
    for leaf in leaf_compartments:
        logging.info(f"  - {leaf['path']} ({leaf['id']})")

    return leaf_compartments


def get_month_date_range(month: str) -> tuple:
    from datetime import datetime
    import calendar

    date_obj = datetime.strptime(month, "%Y-%m")
    from_date = date_obj.strftime("%Y-%m-01T00:00:00.000Z")

    last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
    to_date = date_obj.strftime(f"%Y-%m-{last_day:02d}T00:00:00.000Z")

    return from_date, to_date


def get_oci_compartment_costs(
    compartment_id: str,
    month: str,
    compartment_path: str,
    config: Dict
) -> Dict:
    logging.info(f"Fetching costs for {compartment_path} ({compartment_id})")

    try:
        usage_client = oci.usage_api.UsageapiClient(config)
        from_date, to_date = get_month_date_range(month)

        request_details = oci.usage_api.models.RequestSummarizedUsagesDetails(
            tenant_id=config['tenancy'],
            time_usage_started=from_date,
            time_usage_ended=to_date,
            granularity='MONTHLY',
            query_type='COST',
            compartment_depth=1,
            filter=oci.usage_api.models.Filter(
                operator='AND',
                dimensions=[
                    oci.usage_api.models.Dimension(
                        key='compartmentId',
                        value=compartment_id
                    )
                ]
            ),
            group_by=['service', 'skuName', 'unit']
        )

        response = usage_client.request_summarized_usages(request_details)
        items = response.data.items

        total_cost = sum(float(item.computed_amount or 0) for item in items)
        logging.info(
            f"Retrieved {len(items)} cost items for {compartment_path}, "
            f"total: {total_cost:.2f}"
        )

        return {
            "status": "success",
            "items": items,
            "compartment_path": compartment_path
        }

    except Exception as err:
        logging.error(f"Error retrieving costs for {compartment_path}: {err}")
        return {
            "status": "failure",
            "message": str(err)
        }


def transform_oci_to_line_items(cost_data: Dict) -> List[Dict]:
    line_items = []

    items = cost_data.get('items', [])

    for item in items:
        computed_amount = float(item.computed_amount or 0)
        computed_quantity = float(item.computed_quantity or 0)

        if computed_quantity > 0:
            unit_cost = computed_amount / computed_quantity
        else:
            unit_cost = 0

        service = item.service or 'Unknown'
        sku_name = item.sku_name or 'Unknown'
        product_name = f"{service} - {sku_name}"

        unit = item.unit or ""
        if 'ECPU' in sku_name and unit == 'Instance Hours':
            unit = 'ECPU Hours'

        line_item = {
            "productName": product_name,
            "usageQuantity": computed_quantity,
            "usageType": service,
            "usageCost": round(unit_cost, 4),
            "currency": item.currency or "USD",
            "usageUnit": unit,
            "totalCost": round(computed_amount, 2),
            "sellerId": "Oracle"
        }

        logging.debug(f"Line item: {line_item}")
        line_items.append(line_item)

    return line_items


def process_compartment_costs(
    mesh_client: MeshStackClient,
    platform_id: str,
    compartment_id: str,
    month: str,
    compartment_path: str,
    config: Dict
) -> None:
    logging.info(f"Processing compartment: {compartment_path} for {month}")

    cost_result = get_oci_compartment_costs(
        compartment_id,
        month,
        compartment_path,
        config
    )

    if cost_result['status'] != 'success':
        logging.error(
            f"Failed to get costs for {compartment_path}: {cost_result.get('message')}"
        )
        return

    line_items = transform_oci_to_line_items(cost_result)

    if not line_items:
        logging.info(f"No costs for compartment {compartment_path} in {month}")
        return

    payload = prepare_payload(line_items, platform_id, "OCI")

    meshstack_date = format_date_for_meshstack(month)
    response = mesh_client.submit_usage_report(compartment_id, meshstack_date, payload)

    if response['status'] == 'success':
        logging.info(f"Successfully submitted report for {compartment_path}")
    else:
        logging.error(
            f"Failed to submit report for {compartment_path}: {response.get('message')}"
        )


def main():
    setup_logging(
        level=os.environ.get('LOG_LEVEL', 'INFO'),
        loki_url=os.environ.get('LOKI_URL'),
        platform_name='oci'
    )

    logging.info("Starting OCI metering collection")
    logging.debug(f"Log level set to: {os.environ.get('LOG_LEVEL', 'INFO')}")

    meshfed_host = os.environ['MESHSTACK_MESHFED_URL']
    kraken_host = os.environ['MESHSTACK_KRAKEN_URL']
    mesh_user = os.environ['MESHSTACK_API_USER']
    mesh_secret = os.environ['MESHSTACK_API_SECRET']
    platform_id = os.environ['PLATFORM_ID']
    root_compartment_id = os.environ['OCI_ROOT_COMPARTMENT_ID']
    usage_period = os.environ.get('USAGE_PERIOD')
    include_deleted = os.environ.get('INCLUDE_DELETED_TENANTS', 'true').lower() == 'true'

    oci_config = get_oci_config()
    mesh_client = MeshStackClient(meshfed_host, kraken_host, mesh_user, mesh_secret)

    mesh_tenants = mesh_client.get_tenants(platform_id, include_deleted=include_deleted)

    if mesh_tenants['status'] != 'success':
        logging.error(f"Failed to fetch meshStack tenants: {mesh_tenants.get('message')}")
        return

    mesh_tenant_ids = mesh_tenants['tenant_ids']
    logging.info(f"Found {len(mesh_tenant_ids)} tenants in meshStack to process")

    months = get_current_and_last_month(usage_period)
    months_to_process = [months['current_month']]

    if should_process_last_month():
        months_to_process.append(months['last_month'])
        logging.info("Processing both current and last month (first 5 days)")

    for compartment_id in mesh_tenant_ids:
        for month in months_to_process:
            process_compartment_costs(
                mesh_client,
                platform_id,
                compartment_id,
                month,
                compartment_id,
                oci_config
            )

    logging.info("OCI metering collection completed")


if __name__ == '__main__':
    main()
