# HLA Application setup
```mermaid
graph LR;
      A(meshStack);
      B(mesh-custom-metering);
      C(source platform);
      D(Scheduler);
      D -- 0. schdules the job --> B
      B -- 1. calling all meshTenants of Platform A --> A
      B -- 2. get all cost and usage data for each account --> C
      B -- 3. aggregated and transfors the cost data --> B
      B -- 4. post cost and usage reports for each account --> A
```

# Application Design
```mermaid
graph TD;
      A(Custom-Code);
      B(mesh-standartized-code);
      C(meshStack);
      D(Source Platform);
			
			A --> B
			B -- communicates --> C
			A -- communicates --> D
```

# Custom-Code:
configruation items:
- platform id e.g. Entra Tenant ID / IONOS Contract ID
- credentials for the API -> usually as env variables
- workspaceID for contact
- meshStack API credentials and API base URL

- function collectionCostAndUsage(string platformTenantId, period): tempalte retry mechanism
- function transformCostAndUsage(string rawData)
- function sumCost(string platformTenantId)

# meshStandard part
- function main(): collect data based on CU, transform data CU and send data
- function currentPeriod()
- function lastPeriod()
- function collectMeshTenants(string meshPlatformID)
- function postTenantUsageReport(string meshPlatfromID)
- function postErrorNotification(string workspaceId)
- function validateCostAndUsage(period)

- Loki monitoring endpoint

# Libs we need
request
pandas
tenacity https://github.com/jd/tenacity
