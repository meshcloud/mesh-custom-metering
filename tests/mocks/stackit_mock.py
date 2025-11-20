from flask import Flask, request, jsonify
import logging
import os
import random
from datetime import datetime, timedelta

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "stackit-mock"}), 200

@app.route('/api/v1/projects/<project_id>/billing/usage', methods=['GET'])
def get_usage(project_id):
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Missing or invalid Authorization header"}), 401
    
    start_date = request.args.get('from')
    end_date = request.args.get('to')
    
    if not start_date or not end_date:
        return jsonify({"error": "from and to parameters required"}), 400
    
    mock_services = [
        {
            "serviceName": "STACKIT Kubernetes Engine",
            "sku": "ske-standard",
            "quantity": round(random.uniform(100, 400), 2),
            "unit": "node-hours",
            "unitPrice": 0.12,
            "cost": 0
        },
        {
            "serviceName": "STACKIT Object Storage",
            "sku": "object-storage-std",
            "quantity": round(random.uniform(500, 1500), 2),
            "unit": "GB-month",
            "unitPrice": 0.023,
            "cost": 0
        },
        {
            "serviceName": "STACKIT PostgreSQL",
            "sku": "postgresql-m",
            "quantity": round(random.uniform(200, 600), 2),
            "unit": "hours",
            "unitPrice": 0.18,
            "cost": 0
        },
        {
            "serviceName": "STACKIT Load Balancer",
            "sku": "lb-basic",
            "quantity": round(random.uniform(50, 200), 2),
            "unit": "hours",
            "unitPrice": 0.05,
            "cost": 0
        },
        {
            "serviceName": "STACKIT Backup",
            "sku": "backup-std",
            "quantity": round(random.uniform(100, 500), 2),
            "unit": "GB-month",
            "unitPrice": 0.015,
            "cost": 0
        }
    ]
    
    for service in mock_services:
        service['cost'] = round(service['quantity'] * service['unitPrice'], 2)
    
    response = {
        "projectId": project_id,
        "period": {
            "from": start_date,
            "to": end_date
        },
        "items": mock_services,
        "totalCost": round(sum(s['cost'] for s in mock_services), 2),
        "currency": "EUR"
    }
    
    logging.info(f"STACKIT Mock: Returned usage for project {project_id}, period {start_date} to {end_date}")
    
    return jsonify(response), 200

@app.route('/api/v1/projects/<project_id>/billing/invoices', methods=['GET'])
def get_invoices(project_id):
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Missing or invalid Authorization header"}), 401
    
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    
    response = {
        "projectId": project_id,
        "month": month,
        "invoices": [
            {
                "invoiceNumber": f"ST-{random.randint(1000000, 9999999)}",
                "invoiceDate": f"{month}-05",
                "dueDate": f"{month}-20",
                "amount": round(random.uniform(500, 3000), 2),
                "currency": "EUR",
                "status": "issued"
            }
        ]
    }
    
    logging.info(f"STACKIT Mock: Returned invoices for project {project_id}, month {month}")
    
    return jsonify(response), 200

@app.route('/api/debug/services', methods=['GET'])
def debug_services():
    return jsonify({
        "services": [
            "STACKIT Kubernetes Engine",
            "STACKIT Object Storage",
            "STACKIT PostgreSQL",
            "STACKIT Load Balancer",
            "STACKIT Backup"
        ]
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5003))
    app.run(host='0.0.0.0', port=port, debug=True)
