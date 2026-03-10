import { CostExplorerClient, GetCostAndUsageCommand } from "@aws-sdk/client-cost-explorer";
import { OrganizationsClient, ListAccountsCommand } from "@aws-sdk/client-organizations";
import * as https from "https";
import * as dotenv from "dotenv";

dotenv.config();

// Configuration of meshStack and AWS
const meshcloudAuth = process.env.KRAKEN_API_KEY;
const meshStackApiEndpoint = process.env.MESHSTACK_API_ENDPOINT!;
const meshStackPlatformIdentifier = process.env.MESHSTACK_PLATFORM_IDENTIFIER_AWS!;

const region = process.env.AWS_REGION || "eu-central-1"; // or your preferred region
const costExplorerClient = new CostExplorerClient({ region });
const orgClient = new OrganizationsClient({ region });

// Logging Configuration
const ENABLE_DEBUG_LOGGING = process.env.DEBUG === 'true' || false;
const ENABLE_PAYLOAD_LOGGING = process.env.LOG_PAYLOADS === 'true' || false;

// AWS Cost Explorer Configuration
const AWS_COST_EXPLORER_CONFIG = {
  granularity: "MONTHLY" as const,
  metrics: ["UnblendedCost", "UsageQuantity"],
  groupBy: [
    { Type: "DIMENSION" as const, Key: "SERVICE" },
    { Type: "DIMENSION" as const, Key: "USAGE_TYPE" }
  ],
  recordTypeFilter: ["Usage", "Support"]
};

// Logging utility functions
const log = {
  info: (message: string) => console.log(message),
  error: (message: string) => console.error(message),
  warn: (message: string) => console.warn(message),
  debug: (message: string) => {
    if (ENABLE_DEBUG_LOGGING) console.log(`[DEBUG] ${message}`);
  },
  payload: (message: string) => {
    if (ENABLE_PAYLOAD_LOGGING) console.log(`[PAYLOAD] ${message}`);
  }
};

/**
 * Fetches all active AWS accounts from the organization
 * @returns Promise<Array<{Id: string, Name: string}>> List of active AWS accounts with their IDs and names
 */
async function listAccounts(): Promise<AwsAccount[]> {
  log.info("🔍 Fetching AWS accounts from organization...");

  const allAccounts: AwsAccount[] = [];
  let nextToken: string | undefined = undefined;

  do {
    const command = new ListAccountsCommand({ NextToken: nextToken });
    const response = await orgClient.send(command);
    
    const activeAccounts = response.Accounts?.filter(acc => acc.Status === "ACTIVE" || acc.Status === "SUSPENDED") ?? [];
    allAccounts.push(...activeAccounts.map(acc => ({ Id: acc.Id!, Name: acc.Name! })));
    
    nextToken = response.NextToken;
    
    if (nextToken) {
      log.debug(`Retrieved ${allAccounts.length} accounts so far, fetching next page...`);
    }
  } while (nextToken);

  log.info(`✅ Found ${allAccounts.length} active and suspended accounts.`);
  log.debug(`Accounts: ${allAccounts.map(acc => `${acc.Name} (${acc.Id})`).join(", ")}`);
  
  return allAccounts;
}

/**
 * Gets the first day of the current month in YYYY-MM-01 format
 * @returns string Current month's first day as ISO date string
 */
function getCurrentMonthFirstDayString(): string {
  const now = new Date();

  const year = now.getFullYear();
  // Months are 0-indexed, so +1 and pad with '0'
  // adding +1 on now.getMonth() to get current month
  const month = (now.getMonth() + 1).toString().padStart(2, '0');

  return `${year}-${month}-01`;
}

/**
 * Gets the first day of the last month in YYYY-MM-01 format
 * @returns string Last month's first day as ISO date string
 */
function getLastMonthFirstDayString(): string {
  const now = new Date();

  const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const year = lastMonth.getFullYear();
  // Months are 0-indexed, so +1 and pad with '0'
  const month = (lastMonth.getMonth() + 1).toString().padStart(2, '0');

  return `${year}-${month}-01`;
}

/**
 * Converts a date string to AWS Cost Explorer compatible time period
 * Creates a time period covering the entire calendar month of the given date
 * 
 * AWS Cost Explorer treats the start date as inclusive and end date as exclusive.
 * To get the entire month, we set start to the 1st and end to the 1st of next month.
 * 
 * Example: For input "2024-06-15", returns { fromDate: "2024-06-01", toDate: "2024-07-01" }
 * This would cover all of June 2024 for AWS Cost Explorer API
 * 
 * @param dateString Input date in YYYY-MM-DD format
 * @returns Object with fromDate and toDate strings for AWS Cost Explorer API
 * @throws Error if dateString is in invalid format
 */
function getAwsCostExplorerTimePeriod(dateString: string): { fromDate: string; toDate: string } {
    const date = new Date(dateString);

    if (isNaN(date.getTime())) {
      throw new Error("Ungültiges Datumsformat. Bitte verwenden Sie ein Format wie 'YYYY-MM-DD'.");
    }
    const startDate = new Date(date.getFullYear(), date.getMonth(), 1);
    const endDate = new Date(date.getFullYear(), date.getMonth() + 1, 1);

    const formatIsoDate = (d: Date): string => {
      const year = d.getFullYear();
      const month = (d.getMonth() + 1).toString().padStart(2, '0');
      const day = d.getDate().toString().padStart(2, '0');
      return `${year}-${month}-${day}`;
    };

    return {
      fromDate: formatIsoDate(startDate),
      toDate: formatIsoDate(endDate)
    };
  }

/**
 * Retrieves AWS cost and usage data for a specific account and month
 * 
 * Fetches detailed cost information from AWS Cost Explorer API including:
 * - Unblended costs and usage quantities
 * - Grouped by AWS service and usage type
 * - Filtered for Usage and Support record types only
 * 
 * @param accountId AWS account ID to query costs for
 * @param forMonth Month to query in YYYY-MM-DD format (any day of the month)
 * @returns Promise<Array> Array of cost items with product name, costs, quantities, and usage details
 */
async function getCostsForAccountForMonth(accountId: string, forMonth: string): Promise<any[]> {
  const { fromDate, toDate } = getAwsCostExplorerTimePeriod(forMonth)
  console.log("fromDate: " + fromDate + "todate: " + toDate)
  
  const command = new GetCostAndUsageCommand({
    TimePeriod: { Start: fromDate, End: toDate },
    Granularity: AWS_COST_EXPLORER_CONFIG.granularity,
    Metrics: AWS_COST_EXPLORER_CONFIG.metrics,
    GroupBy: AWS_COST_EXPLORER_CONFIG.groupBy,
    Filter: {
      And: [
        {
          Dimensions: {
            Key: "LINKED_ACCOUNT",
            Values: [accountId]
          }
        },
        {
          Dimensions: {
            Key: "RECORD_TYPE",
            Values: AWS_COST_EXPLORER_CONFIG.recordTypeFilter
          }
        }
      ]
    }
  });    const response = await costExplorerClient.send(command);
    const results = response.ResultsByTime ?? [];

    if (results.length === 0) return [];

    const groups = results[0].Groups ?? [];
    return groups.map(group => ({
      productName: group.Keys?.[0],
      usageCost: parseFloat(group.Metrics?.UnblendedCost?.Amount ?? "0").toFixed(2),
      usageQuantity: parseFloat(group.Metrics?.UsageQuantity?.Amount ?? "0"),
      usageUnit: "N/A", // AWS gibt Einheit nicht direkt aus
      usageType: group.Keys?.[1],
      currency: "USD", // AWS nutzt i.d.R. USD, anpassbar
      totalCost: parseFloat(group.Metrics?.UnblendedCost?.Amount ?? "0").toFixed(2),
    }));
  }

/**
 * Sends usage report data to meshStack via HTTPS PUT request
 * 
 * Creates a meshResourceUsageReport and submits it to the meshStack API.
 * Skips sending if no cost data is provided.
 * 
 * @param accountId AWS account ID for the report
 * @param items Array of cost/usage items to include in the report
 * @param fromDate Report date in YYYY-MM-DD format
 */
async function sendToMeshstack(accountId: string, items: any[], fromDate: string) {
    if (items.length === 0) {
      console.warn(`${accountId} ⚠️ No cost data to send, skipping.`);
      return;
    }

    const payload = JSON.stringify({
      apiVersion: "v1",
      kind: "meshResourceUsageReport",
      fullPlatformIdentifier: meshStackPlatformIdentifier,
      source: "AWS",
      lineItems: items
    });

    log.payload(`${accountId} ✅ MeshStack payload: ${payload} for ${fromDate}`);

    const options = {
      hostname: meshStackApiEndpoint,
      path: `/api/meshobjects/meshresourceusagereports/${accountId}/${fromDate}Z`,
      method: "PUT",
      headers: {
        "Content-Type": "application/vnd.meshcloud.api.meshobjects.v1+json;charset=UTF-8",
        "Authorization": `Basic ${meshcloudAuth}`,
        "Content-Length": Buffer.byteLength(payload),
        "Accept": "application/vnd.meshcloud.api.meshobjects.v1+json"
      }
    };

    const req = https.request(options, res => {
      let response = "";
      res.on("data", chunk => response += chunk);
      res.on("end", () => {
        console.log(`${accountId} ${fromDate} ✅ MeshStack response: ${response}`);
      });
    });

    req.on("error", e => {
      console.error(`${accountId} ${fromDate} ❌ Error sending to MeshStack:`, e);
    });

    req.write(payload);
    req.end();
  }

/**
 * Main execution function that orchestrates the AWS cost collection and meshStack reporting process
 * 
 * Process flow:
 * 1. Fetches all active AWS accounts from the organization
 * 2. For each account, collects cost data for current month and last month
 * 3. Sends the collected data to meshStack for usage reporting
 * 
 * Handles errors gracefully by logging them and continuing with the next account
 */
async function main() {
    const accounts = await listAccounts();
    const currentMonth = getCurrentMonthFirstDayString()
    const lastMonth = getLastMonthFirstDayString()

    // itterate over each active aws account and process costs
    for (const account of accounts) {
      // Collect AWS Account Cost items for current month and send to meshStack 
      try {
        console.log(`📦 Processing account for current month ${currentMonth}: ${account.Name} (${account.Id}) ${currentMonth}`);
        const costItems = await getCostsForAccountForMonth(account.Id, currentMonth);
        log.debug(`📊 Found ${costItems.length} cost items for account ${account.Id}.`);
        log.debug(JSON.stringify(costItems, null, 2));
        await sendToMeshstack(account.Id, costItems, currentMonth);
      } catch (err) {
        console.error(`❌ Error processing account ${account.Id}:`, err);
      }

      // Collect AWS Account Cost items for last month and send to meshStack
      try {
        console.log(`📦 Processing account for last month ${lastMonth}: ${account.Name} (${account.Id}) ${lastMonth}`);
        const costItemsPastMonth = await getCostsForAccountForMonth(account.Id, lastMonth);
        log.debug(`📊 Found ${costItemsPastMonth.length} cost items for account ${account.Id}.`);
        log.debug(JSON.stringify(costItemsPastMonth, null, 2));
        await sendToMeshstack(account.Id, costItemsPastMonth, lastMonth);
      } catch (err) {
        console.error(`❌ Error processing account ${account.Id}:`, err);
      }
    }

    console.log("🎉 All accounts processed.");
  }

main().catch(err => console.error("🔥 Unhandled error in script:", err));