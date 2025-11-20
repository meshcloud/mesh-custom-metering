from flask import Flask, request, jsonify
import logging
import os
import random
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "ionos-mock"}), 200

@app.route('/api/v1/contracts/<contract_id>/usage', methods=['GET'])
def get_usage(contract_id):
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Missing or invalid Authorization header"}), 401
    
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    
    if not start_date or not end_date:
        return jsonify({"error": "startDate and endDate parameters required"}), 400
    
    mock_resources = [
        {
            "resourceType": "compute.vm",
            "resourceId": f"vm-{random.randint(1000, 9999)}",
            "quantity": round(random.uniform(100, 500), 2),
            "unit": "hours",
            "pricePerUnit": 0.10,
            "totalCost": 0
        },
        {
            "resourceType": "storage.block",
            "resourceId": f"vol-{random.randint(1000, 9999)}",
            "quantity": round(random.uniform(50, 200), 2),
            "unit": "GB-month",
            "pricePerUnit": 0.08,
            "totalCost": 0
        },
        {
            "resourceType": "network.bandwidth",
            "resourceId": f"net-{random.randint(1000, 9999)}",
            "quantity": round(random.uniform(500, 2000), 2),
            "unit": "GB",
            "pricePerUnit": 0.05,
            "totalCost": 0
        },
        {
            "resourceType": "database.instance",
            "resourceId": f"db-{random.randint(1000, 9999)}",
            "quantity": round(random.uniform(100, 300), 2),
            "unit": "hours",
            "pricePerUnit": 0.25,
            "totalCost": 0
        },
        {
            "resourceType": "loadbalancer",
            "resourceId": f"lb-{random.randint(1000, 9999)}",
            "quantity": round(random.uniform(50, 150), 2),
            "unit": "hours",
            "pricePerUnit": 0.15,
            "totalCost": 0
        }
    ]
    
    for resource in mock_resources:
        resource['totalCost'] = round(resource['quantity'] * resource['pricePerUnit'], 2)
    
    response = {
        "contractId": contract_id,
        "period": {
            "start": start_date,
            "end": end_date
        },
        "resources": mock_resources,
        "totalCost": sum(r['totalCost'] for r in mock_resources),
        "currency": "EUR"
    }
    
    logging.info(f"IONOS Mock: Returned usage for contract {contract_id}, period {start_date} to {end_date}")
    
    return jsonify(response), 200

@app.route('/api/v1/contracts/<contract_id>/invoices', methods=['GET'])
def get_invoices(contract_id):
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Missing or invalid Authorization header"}), 401
    
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    
    response = {
        "contractId": contract_id,
        "month": month,
        "invoices": [
            {
                "invoiceId": f"INV-{random.randint(100000, 999999)}",
                "date": f"{month}-01",
                "amount": round(random.uniform(1000, 5000), 2),
                "currency": "EUR",
                "status": "paid"
            }
        ]
    }
    
    logging.info(f"IONOS Mock: Returned invoices for contract {contract_id}, month {month}")
    
    return jsonify(response), 200

@app.route('/api/debug/resources', methods=['GET'])
def debug_resources():
    return jsonify({
        "resource_types": ["compute.vm", "storage.block", "network.bandwidth", "database.instance", "loadbalancer"]
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=True)
