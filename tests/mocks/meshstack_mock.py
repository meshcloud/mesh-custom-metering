from flask import Flask, request, jsonify
from datetime import datetime
import logging
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

stored_reports = {}

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "meshstack-mock"}), 200

@app.route('/api/meshobjects/meshtenants', methods=['GET'])
def get_mesh_tenants():
    platform_id = request.args.get('platformIdentifier')
    
    if not platform_id:
        return jsonify({"error": "platformIdentifier parameter required"}), 400
    
    tenants = [
        {
            "platformTenantId": f"{platform_id}-tenant-001",
            "platformTenantName": "Test Tenant 001",
            "tags": {"environment": "production"}
        },
        {
            "platformTenantId": f"{platform_id}-tenant-002",
            "platformTenantName": "Test Tenant 002",
            "tags": {"environment": "development"}
        }
    ]
    
    logging.info(f"Returning {len(tenants)} tenants for platform {platform_id}")
    return jsonify({"tenants": tenants}), 200

@app.route('/api/meshobjects/meshresourceusagereports/<platform_tenant_id>/<date>', methods=['PUT'])
def import_usage_report(platform_tenant_id, date):
    auth = request.authorization
    
    if not auth or auth.username != 'test_user' or auth.password != 'test_password':
        return jsonify({"error": "Unauthorized"}), 401
    
    payload = request.get_json()
    
    if not payload:
        return jsonify({"error": "No payload provided"}), 400
    
    required_fields = ['apiVersion', 'kind', 'fullPlatformIdentifier', 'source', 'lineItems']
    missing_fields = [field for field in required_fields if field not in payload]
    
    if missing_fields:
        return jsonify({"error": f"Missing required fields: {missing_fields}"}), 400
    
    if payload['apiVersion'] != 'v1':
        return jsonify({"error": "Unsupported API version"}), 400
    
    if payload['kind'] != 'meshResourceUsageReport':
        return jsonify({"error": "Invalid kind"}), 400
    
    key = f"{platform_tenant_id}_{date}"
    stored_reports[key] = {
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat(),
        "platform_tenant_id": platform_tenant_id,
        "date": date
    }
    
    total_cost = sum(item.get('totalCost', 0) for item in payload['lineItems'])
    
    logging.info(f"Stored usage report for {platform_tenant_id} on {date} with {len(payload['lineItems'])} line items, total cost: {total_cost}")
    
    return jsonify({
        "status": "success",
        "message": f"Usage report imported successfully",
        "lineItemsCount": len(payload['lineItems']),
        "totalCost": total_cost
    }), 200

@app.route('/api/meshobjects/meshresourceusagereports/<platform_tenant_id>/<date>', methods=['GET'])
def get_usage_report(platform_tenant_id, date):
    key = f"{platform_tenant_id}_{date}"
    
    if key not in stored_reports:
        return jsonify({"error": "Report not found"}), 404
    
    return jsonify(stored_reports[key]), 200

@app.route('/api/debug/reports', methods=['GET'])
def debug_reports():
    return jsonify({
        "total_reports": len(stored_reports),
        "reports": list(stored_reports.keys())
    }), 200

@app.route('/api/debug/clear', methods=['POST'])
def clear_reports():
    stored_reports.clear()
    return jsonify({"status": "success", "message": "All reports cleared"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
