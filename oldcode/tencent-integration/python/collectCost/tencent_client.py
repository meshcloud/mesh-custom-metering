from tencentcloud.common import credential
from tencentcloud.billing.v20180709 import billing_client, models
import logging
import traceback
import pandas as pd
from typing import Dict, List, Any

def create_tencent_client(secret_id: str, secret_key: str, region: str = 'ap-guangzhou'):
    """
    Create an authenticated Tencent client.
    
    Args:
        secret_id: Tencent cloud API secret ID
        secret_key: Tencent cloud API secret key
        region: Tencent cloud region, default is 'ap-guangzhou'
        
    Returns:
        Authenticated Tencent billing client
    """
    cred = credential.Credential(secret_id, secret_key)
    return billing_client.BillingClient(cred, region)

def get_tencent_costs_per_account(client, account_id: str, month: str, limit: int = 100):
    '''
    Retrieve Tencent cloud cost for a given account and month.
    
    Args:
        client: authenticated Tencent client
        account_id: Tencent account ID
        month: string formatted as YYYY-MM
        limit: number of records fetched in one call, max is 100
        
    Returns:
        results: dict formatted as {"status": "success", "result": list of service costs}
                in case of successful execution or {"status": "failure", "message": error message}
    '''
    
    # Init the output
    result = {"status":"failure"}

    try:               
        # Create request object for cost summary by product
        req = models.DescribeBillDetailRequest()
        req.Month = month
        req.Limit = limit
        req.Offset = 0
        req.PayerUin = account_id
        
        service_costs = []
        # Loop until the SDK response is empty
        while True:
            try:
                # Send request
                resp = client.DescribeBillDetail(req)
                
                # Check if we got any records
                if not resp.DetailSet:
                    break

                for item in resp.DetailSet:
                    service_costs.append({
                        'BusinessCodeName': item.BusinessCodeName, # productName
                        'UsedAmountUnit':item.ComponentSet[0].UsedAmountUnit, # usageUnit
                        'PriceUnit': item.ComponentSet[0].PriceUnit, # usageType
                        'SinglePrice': float(item.ComponentSet[0].SinglePrice), # usageCost
                        'UsedAmount': float(item.ComponentSet[0].UsedAmount), # usageQuantity
                        'RealCost': float(item.ComponentSet[0].RealCost) # totalCost
                    })
                
                # Check if we've processed all records
                if len(resp.DetailSet) < limit:
                    break
                    
                # Move to next page
                req.Offset += limit
                
            except Exception as e:
                logging.error(f"Error fetching page at offset {req.Offset}: {str(e)} {traceback.format_exc()}")
                raise

        result = {
            "status": "success",
            "result": service_costs
            }

    except Exception as err:
        logging.error(f"Error retrieving service costs: {err} {traceback.format_exc()}")
        result = {
            "status":"failure",
            "message": f"Error retrieving service costs: {err} {traceback.format_exc()}"
            }
    
    return result

def aggregate_cost(tencent_cost: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggregate cost data by product name, usage unit, price unit, and single price.
    
    Args:
        tencent_cost: List of cost items from get_tencent_costs_per_account
        
    Returns:
        List of aggregated cost items
    """
    # Init the output
    result = []

    if tencent_cost:
        # Convert the response to DataFrame, aggregate by the product name and the price,
        # calculate the sum for quantities and amount
        df = pd.DataFrame(tencent_cost)
        dfa = df.groupby(['BusinessCodeName', 'UsedAmountUnit', 'PriceUnit', 'SinglePrice']).agg(
                {
                    'UsedAmount':'sum',
                    'RealCost':'sum'
                })
        dfa.reset_index(inplace=True)
        result = dfa.to_dict(orient="records")

    return result