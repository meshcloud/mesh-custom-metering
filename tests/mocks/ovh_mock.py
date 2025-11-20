from flask import Flask, request, jsonify
import logging
import os
import random
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "ovh-mock"}), 200

@app.route('/cloud/project/<project_id>/usage/current', methods=['GET'])
def get_current_usage(project_id):
    auth_header = request.headers.get('X-Ovh-Application')
    
    if not auth_header:
        return jsonify({"message": "Missing X-Ovh-Application header"}), 401
    
    mock_resources = [
        {
            "type": "instance",
            "resourceId": f"instance-{random.randint(1000, 9999)}",
            "region": "GRA",
            "quantity": {
                "value": round(random.uniform(100, 500), 2),
                "unit": "hours"
            },
            "totalPrice": round(random.uniform(10, 100), 2)
        },
        {
            "type": "volume",
            "resourceId": f"volume-{random.randint(1000, 9999)}",
            "region": "GRA",
            "quantity": {
                "value": round(random.uniform(50, 200), 2),
                "unit": "GB"
            },
            "totalPrice": round(random.uniform(5, 50), 2)
        },
        {
            "type": "snapshot",
            "resourceId": f"snapshot-{random.randint(1000, 9999)}",
            "region": "GRA",
            "quantity": {
                "value": round(random.uniform(20, 100), 2),
                "unit": "GB"
            },
            "totalPrice": round(random.uniform(2, 20), 2)
        },
        {
            "type": "bandwidth",
            "resourceId": f"bandwidth-{random.randint(1000, 9999)}",
            "region": "GRA",
            "quantity": {
                "value": round(random.uniform(500, 2000), 2),
                "unit": "GB"
            },
            "totalPrice": round(random.uniform(25, 150), 2)
        },
        {
            "type": "objectStorage",
            "resourceId": f"object-{random.randint(1000, 9999)}",
            "region": "GRA",
            "quantity": {
                "value": round(random.uniform(100, 1000), 2),
                "unit": "GB"
            },
            "totalPrice": round(random.uniform(3, 30), 2)
        }
    ]
    
    response = {
        "projectId": project_id,
        "period": {
            "from": datetime.now().replace(day=1).strftime('%Y-%m-%d'),
            "to": datetime.now().strftime('%Y-%m-%d')
        },
        "resources": mock_resources,
        "total": round(sum(r['totalPrice'] for r in mock_resources), 2),
        "currency": "EUR"
    }
    
    logging.info(f"OVH Mock: Returned current usage for project {project_id}")
    
    return jsonify(response), 200

@app.route('/cloud/project/<project_id>/usage/history', methods=['GET'])
def get_usage_history(project_id):
    auth_header = request.headers.get('X-Ovh-Application')
    
    if not auth_header:
        return jsonify({"message": "Missing X-Ovh-Application header"}), 401
    
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    
    if not from_date or not to_date:
        return jsonify({"message": "from and to parameters required"}), 400
    
    response = {
        "projectId": project_id,
        "period": {
            "from": from_date,
            "to": to_date
        },
        "usage": [
            {
                "date": from_date,
                "hourlyUsage": [
                    {
                        "type": "instance",
                        "quantity": round(random.uniform(10, 50), 2),
                        "cost": round(random.uniform(1, 10), 2)
                    }
                ]
            }
        ],
        "total": round(random.uniform(100, 500), 2),
        "currency": "EUR"
    }
    
    logging.info(f"OVH Mock: Returned usage history for project {project_id}, period {from_date} to {to_date}")
    
    return jsonify(response), 200

@app.route('/cloud/project/<project_id>/bill', methods=['GET'])
def get_bills(project_id):
    auth_header = request.headers.get('X-Ovh-Application')
    
    if not auth_header:
        return jsonify({"message": "Missing X-Ovh-Application header"}), 401
    
    response = [
        {
            "billId": f"OVH-{random.randint(100000, 999999)}",
            "date": datetime.now().strftime('%Y-%m-%d'),
            "priceWithoutTax": round(random.uniform(100, 1000), 2),
            "tax": round(random.uniform(10, 100), 2),
            "priceWithTax": 0,
            "currency": "EUR"
        }
    ]
    
    response[0]['priceWithTax'] = round(
        response[0]['priceWithoutTax'] + response[0]['tax'], 2
    )
    
    logging.info(f"OVH Mock: Returned bills for project {project_id}")
    
    return jsonify(response), 200

@app.route('/api/debug/regions', methods=['GET'])
def debug_regions():
    return jsonify({
        "regions": ["GRA", "SBG", "BHS", "DE", "UK", "WAW"]
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5004))
    app.run(host='0.0.0.0', port=port, debug=True)
