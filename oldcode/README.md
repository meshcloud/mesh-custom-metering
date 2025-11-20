# Custom Platform Metering

gets the metering data for meshStack out of different custom platforms

## STACKIT Cost Data Integration

This project allows you to extract cost information from STACKIT APIs, process it, and send it to meshStack. It ensures that the costs are converted from Cents to Euros before sending them to meshStack.

## Requirements

- **Node.js** (version 20 or higher)
- **Environment Variables**:
  - `STACKIT_SERVICE_ACCOUNT_TOKEN`: The authentication token for the STACKIT API.
  - `KRAKEN_API_KEY`: Your API key for meshStack.
  - `MESHSTACK_API_ENDPOINT`: The meshStack API endpoint.
  - `MESHSTACK_PLATFORM_IDENTIFIER`: The platform identifier for meshStack.
  - `STACKIT_CONTAINER_PARENT_ID`: The container ID for the STACKIT container.

## Installation

1. **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd <repository-name>
    ```

2. **Install dependencies**:
    ```bash
    npm install
    ```

3. **Configure environment variables**:
   Create a `.env` file in the project directory and add the necessary environment variables:
   ```plaintext
   STACKIT_SERVICE_ACCOUNT_TOKEN=<your-STACKIT-token>
   KRAKEN_API_KEY=<your-kraken-api-key>
   MESHSTACK_API_ENDPOINT=<meshstack-api-endpoint>
   MESHSTACK_PLATFORM_IDENTIFIER=<meshstack-platform-identifier>
   STACKIT_CONTAINER_PARENT_ID=<STACKIT-container-parent-id>
   ```

## Functionality

The script consists of several functions that run sequentially:

1. **`getActiveProjects()`**:
   - Fetches active projects from the STACKIT API.
   - Filters projects with the status "ACTIVE".

2. **`getProjectCosts(projectIds)`**:
   - For each active project, it fetches cost data (in cents) via the STACKIT Cost API.
   - Processes the response and converts the costs to Euros.

3. **`sendToMeshstack(projCostStr)`**:
   - Sends the processed cost data (in Euros) to meshStack.
   - The data is sent as a `meshResourceUsageReport` object in the meshStack format.

## Example of Returned Data

The data returned from STACKIT may look like this:

```json
{
  "apiVersion": "v1",
  "kind": "meshResourceUsageReport",
  "fullPlatformIdentifier": "STACKIT.sovereign",
  "source": "STACKIT",
  "lineItems": [
    {
      "productName": "likvid-mobile-search-backend - General Purpose Server-g1.1-EU01",
      "usageQuantity": 8,
      "usageType": "Compute Engine",
      "usageCost": 30.33,
      "currency": "EUR",
      "usageUnit": "Hours",
      "totalCost": 36.99
    },
    {
      "productName": "likvid-mobile-search-backend - Block Storage for disk volumes Premium-Performance 0-EU01",
      "usageQuantity": 8,
      "usageType": "Storage",
      "usageCost": 1.97,
      "currency": "EUR",
      "usageUnit": "Hours",
      "totalCost": 36.99
    }
  ]
}
```

### **Conversion from Cents to Euros**
The script converts all cents values into Euros, so the final output is correctly displayed in Euros.

## Running the Script

To run the script, use the following command:

```bash
node index.js
```

The script will perform the following steps:
1. Fetch active projects from STACKIT.
2. Load the cost data for each project.
3. Convert the Cents values to Euros and send them to meshStack.

## Error Handling

- If the script encounters an issue during data processing (e.g., errors fetching project information or the cost API), an appropriate error message will be logged.
- If the cost data is empty or invalid, the project will be skipped.

## Extending Functionality

- **Error Logging**: You can customize the logging to receive more detailed error reports.
- **Extensions**: It's possible to extend the functionality to integrate additional cloud data or use other APIs.
