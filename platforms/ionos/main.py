import os
import sys
import logging
from typing import Dict, List
import requests

sys.path.append('/app/core')
from meshstack_client import MeshStackClient, prepare_payload
from utils import get_current_and_last_month, format_date_for_meshstack, should_process_last_month
from logging_config import setup_logging


def get_ionos_product_costs() -> Dict:
    ionos_host = os.environ.get('IONOS_API_URL', 'http://ionos-mock:5002')
    
    try:
        response = requests.get(f"{ionos_host}/products")
        response.raise_for_status()
        return response.json()
    except Exception as err:
        logging.error(f"Error retrieving IONOS product costs: {err}")
        raise


def get_ionos_usage(month: str) -> Dict:
    ionos_host = os.environ.get('IONOS_API_URL', 'http://ionos-mock:5002')
    
    try:
        response = requests.get(f"{ionos_host}/usage", params={"period": month})
        response.raise_for_status()
        return response.json()
    except Exception as err:
        logging.error(f"Error retrieving IONOS usage: {err}")
        raise


def calculate_datacenter_costs(usage_data: Dict, products: Dict) -> List[Dict]:
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
            quantity = quantity_data.get('quantity', 0)
            
            if matched_product:
                unit_cost_data = matched_product.get('unitCost', {})
                unit_cost = float(unit_cost_data.get('quantity', 0))
                total_cost = round(quantity * unit_cost, 2)
            else:
                unit_cost = 0
                total_cost = 0
            
            meters.append({
                'meterId': meter.get('meterId'),
                'meterDesc': meter_desc,
                'quantity': quantity,
                'unit': quantity_data.get('unit', ''),
                'totalCost': total_cost,
                'unitCost': unit_cost
            })
        
        results.append({
            'id': datacenter.get('id'),
            'name': datacenter.get('name'),
            'meters': meters
        })
    
    return results


def transform_ionos_to_line_items(meters: List[Dict]) -> List[Dict]:
    line_items = []
    
    for meter in meters:
        if meter['totalCost'] > 0:
            line_items.append({
                "productName": meter['meterDesc'],
                "usageQuantity": meter['quantity'],
                "usageType": f"IONOS Service {meter['meterId']}",
                "usageCost": meter['totalCost'],
                "currency": "EUR",
                "usageUnit": meter['unit'],
                "totalCost": meter['totalCost']
            })
    
    return line_items


def process_month(
    mesh_client: MeshStackClient,
    platform_id: str,
    month: str
) -> None:
    logging.info(f"Processing IONOS costs for {month}")
    
    products = get_ionos_product_costs()
    usage = get_ionos_usage(month)
    
    datacenter_costs = calculate_datacenter_costs(usage, products)
    
    meshstack_date = format_date_for_meshstack(month)
    
    for datacenter in datacenter_costs:
        datacenter_id = datacenter['id']
        logging.info(f"Processing datacenter {datacenter_id}")
        
        line_items = transform_ionos_to_line_items(datacenter['meters'])
        
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
    
    meshfed_host = os.environ.get('MESHSTACK_MESHFED_URL', os.environ.get('MESHSTACK_API_URL', ''))
    kraken_host = os.environ.get('MESHSTACK_KRAKEN_URL', os.environ.get('MESHSTACK_API_URL', ''))
    mesh_user = os.environ['MESHSTACK_API_USER']
    mesh_secret = os.environ['MESHSTACK_API_SECRET']
    platform_id = os.environ['PLATFORM_ID']
    usage_period = os.environ.get('USAGE_PERIOD')
    
    mesh_client = MeshStackClient(meshfed_host, kraken_host, mesh_user, mesh_secret)
    
    months = get_current_and_last_month(usage_period)
    months_to_process = [months['current_month']]
    
    if should_process_last_month():
        months_to_process.append(months['last_month'])
        logging.info("Processing both current and last month (first 5 days)")
    
    for month in months_to_process:
        process_month(mesh_client, platform_id, month)
    
    logging.info("IONOS metering collection completed")


if __name__ == '__main__':
    main()
