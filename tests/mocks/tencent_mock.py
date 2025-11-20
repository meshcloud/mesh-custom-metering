from flask import Flask, request, jsonify
import logging
import os
import json

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "tencent-mock"}), 200

@app.route('/api/billing/v20180709/DescribeBillDetail', methods=['POST'])
def describe_bill_detail():
    data = request.get_json()
    
    required_fields = ['Month', 'Limit', 'Offset', 'PayerUin']
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        return jsonify({
            "Response": {
                "Error": {
                    "Code": "InvalidParameter",
                    "Message": f"Missing required fields: {missing_fields}"
                }
            }
        }), 400
    
    month = data['Month']
    limit = data['Limit']
    offset = data['Offset']
    payer_uin = data['PayerUin']
    
    mock_services = [
        {
            "name": "Cloud Virtual Machine",
            "code": "cvm",
            "used_amount": 720.0,
            "used_amount_unit": "Hour",
            "price_unit": "Hour",
            "single_price": 0.15,
            "real_cost": 108.0
        },
        {
            "name": "Cloud Block Storage",
            "code": "cbs",
            "used_amount": 100.0,
            "used_amount_unit": "GB",
            "price_unit": "GB",
            "single_price": 0.05,
            "real_cost": 5.0
        },
        {
            "name": "Content Delivery Network",
            "code": "cdn",
            "used_amount": 500.0,
            "used_amount_unit": "GB",
            "price_unit": "GB",
            "single_price": 0.08,
            "real_cost": 40.0
        },
        {
            "name": "TencentDB for MySQL",
            "code": "cdb",
            "used_amount": 720.0,
            "used_amount_unit": "Hour",
            "price_unit": "Hour",
            "single_price": 0.25,
            "real_cost": 180.0
        },
        {
            "name": "Cloud Load Balancer",
            "code": "clb",
            "used_amount": 720.0,
            "used_amount_unit": "Hour",
            "price_unit": "Hour",
            "single_price": 0.02,
            "real_cost": 14.4
        }
    ]
    
    detail_set = []
    start_idx = offset
    end_idx = min(offset + limit, len(mock_services))
    
    for service in mock_services[start_idx:end_idx]:
        detail_set.append({
            "BusinessCodeName": service["name"],
            "ComponentSet": [
                {
                    "UsedAmountUnit": service["used_amount_unit"],
                    "PriceUnit": service["price_unit"],
                    "SinglePrice": str(service["single_price"]),
                    "UsedAmount": str(service["used_amount"]),
                    "RealCost": str(service["real_cost"])
                }
            ]
        })
    
    response = {
        "Response": {
            "DetailSet": detail_set,
            "Total": len(mock_services),
            "RequestId": f"mock-request-{payer_uin}-{month}-{offset}"
        }
    }
    
    logging.info(f"Tencent Mock: Returned {len(detail_set)} billing details for account {payer_uin}, month {month}, offset {offset}")
    
    return jsonify(response), 200

@app.route('/api/debug/services', methods=['GET'])
def debug_services():
    return jsonify({
        "total_services": 5,
        "services": ["cvm", "cbs", "cdn", "cdb", "clb"]
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
