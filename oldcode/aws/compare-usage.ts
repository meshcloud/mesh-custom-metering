import { CostExplorerClient, GetCostAndUsageCommand } from "@aws-sdk/client-cost-explorer";
import { OrganizationsClient, ListAccountsCommand } from "@aws-sdk/client-organizations";
import * as https from "https";
import * as dotenv from "dotenv";

dotenv.config();

// Configuration of meshStack and AWS
const meshcloudAuth = process.env.KRAKEN_API_KEY;
const meshStackApiEndpoint = process.env.MESHSTACK_API_ENDPOINT!;

const region = process.env.AWS_REGION || "eu-central-1";
const costExplorerClient = new CostExplorerClient({ region });
const orgClient = new OrganizationsClient({ region });

// Logging Configuration
const ENABLE_DEBUG_LOGGING = process.env.DEBUG === 'true' || false;

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
  success: (message: string) => console.log(`✅ ${message}`),
  mismatch: (message: string) => console.log(`❌ ${message}`)
};

// Types for better type safety
interface AwsAccount {
  Id: string;
  Name: string;
}

interface AwsCostItem {
  productName: string;
  usageCost: string;
  usageQuantity: number;
  usageUnit: string;
  usageType: string;
  currency: string;
  totalCost: string;
}

interface meshStackUsageItem {
  kind: string;
  apiVersion: string;
  metadata: {
    uuid: string;
    ownedByWorkspace: string;
    ownedByProject: string;
    createdAt: string;
  };
  spec: {
    period: string;
    reportCategory: string;
    platformType: string;
    platform: string;
    platformTenantId: string;
    version: number;
  };
  status: {
    generatedAt: string;
    finalizedAt: string;
    paymentMethod: {
      identifier: string;
      name: string;
      amount: number;
    };
    timeframe: {
      from: string;
      to: string;
    };
    tags: Record<string, string[]>;
    lineItems: {
      netAmount: {
        amount: number;
        currency: string;
        baseAmount: number;
        baseCurrency: string;
        exchangeRate: number;
      };
    }[];
  };
}

interface ComparisonResult {
  accountId: string;
  accountName: string;
  month: string;
  isMatch: boolean;
  awsTotal: number;
  meshStackTotal: number; // Raw consumption (calculated from baseAmount / 0.96795)
  meshStackFinalTotal?: number; // Calculated amount (what meshStack calls baseAmount)
  difference: number;
  mismatches?: ServiceMismatch[];
}

interface ServiceMismatch {
  service: string;
  awsCost: number;
  meshStackCost: number;
  difference: number;
}

/**
 * Fetches all active AWS accounts from the organization
 * Handles pagination to retrieve all accounts (default page size is 20)
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
 * Gets the first day of the last month in YYYY-MM-01 format
 * @returns string Last month's first day as ISO date string
 */
function getLastMonthFirstDayString(): string {
  const now = new Date();
  const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const year = lastMonth.getFullYear();
  const month = (lastMonth.getMonth() + 1).toString().padStart(2, '0');
  return `${year}-${month}-01`;
}

/**
 * Converts a date string to AWS Cost Explorer compatible time period
 * Creates a time period covering the entire calendar month of the given date
 * 
 * @param dateString Input date in YYYY-MM-DD format
 * @returns Object with fromDate and toDate strings for AWS Cost Explorer API
 * @throws Error if dateString is in invalid format
 */
function getAwsCostExplorerTimePeriod(dateString: string): { fromDate: string; toDate: string } {
  const date = new Date(dateString);

  if (isNaN(date.getTime())) {
    throw new Error("Invalid date format. Please use format like 'YYYY-MM-DD'.");
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
 * @param accountId AWS account ID to query costs for
 * @param forMonth Month to query in YYYY-MM-DD format (any day of the month)
 * @returns Promise<Array> Array of cost items with product name, costs, quantities, and usage details
 */
async function getCostsForAccountForMonth(accountId: string, forMonth: string): Promise<AwsCostItem[]> {
  const { fromDate, toDate } = getAwsCostExplorerTimePeriod(forMonth);
  log.debug(`Fetching AWS costs for account ${accountId} from ${fromDate} to ${toDate}`);
  
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
  });

  const response = await costExplorerClient.send(command);
  const results = response.ResultsByTime ?? [];

  if (results.length === 0) return [];

  const groups = results[0].Groups ?? [];
  return groups.map(group => ({
    productName: group.Keys?.[0] || "Unknown",
    usageCost: parseFloat(group.Metrics?.UnblendedCost?.Amount ?? "0").toFixed(2),
    usageQuantity: parseFloat(group.Metrics?.UsageQuantity?.Amount ?? "0"),
    usageUnit: "N/A",
    usageType: group.Keys?.[1] || "Unknown",
    currency: "USD",
    totalCost: parseFloat(group.Metrics?.UnblendedCost?.Amount ?? "0").toFixed(2),
  }));
}

/**
 * Fetches tenant usage report from meshStack for a specific account and month
 * Uses the list API to search by tenant identifier (AWS Account ID)
 * 
 * @param accountId AWS account ID (tenant ID in meshStack)
 * @param forMonth Month to query in YYYY-MM-DD format
 * @returns Promise<meshStackUsageItem | null> Usage report data or null if not found
 */
async function getMeshStackUsageReport(accountId: string, forMonth: string): Promise<meshStackUsageItem | null> {
  return new Promise((resolve, reject) => {
    const { fromDate } = getAwsCostExplorerTimePeriod(forMonth);
    
    // Convert fromDate (YYYY-MM-DD) to period format (YYYY-MM)
    const period = fromDate.substring(0, 7); // Extract YYYY-MM from YYYY-MM-DD
    
    // Use the list API endpoint with query parameters for tenant identifier and period
    const queryParams = new URLSearchParams({
      platformTenantId: accountId,
      period: period
    });
    
    const path = `/api/meshobjects/meshtenantusagereports?${queryParams.toString()}`;
    
    log.debug(`Fetching meshStack usage report: ${meshStackApiEndpoint}${path}`);

    const options = {
      hostname: meshStackApiEndpoint,
      path: path,
      method: "GET",
      headers: {
        "Authorization": `Basic ${meshcloudAuth}`,
        "Accept": "application/vnd.meshcloud.api.meshtenantusagereport.v3.hal+json"
      }
    };

    const req = https.request(options, res => {
      let data = "";
      res.on("data", chunk => data += chunk);
      res.on("end", () => {
        if (res.statusCode === 200) {
          try {
            const response = JSON.parse(data);
            
            // The list API returns an array of reports, we need to find the matching one
            // or take the first one if there's only one result
            if (response._embedded && response._embedded.meshTenantUsageReports && response._embedded.meshTenantUsageReports.length > 0) {
              const usageReport = response._embedded.meshTenantUsageReports[0];
              log.debug(`Found meshStack usage report for ${accountId} in ${forMonth}`);
              resolve(usageReport);
            } else {
              log.debug(`No meshStack usage report found for ${accountId} in ${forMonth}`);
              resolve(null);
            }
          } catch (err) {
            log.error(`Failed to parse meshStack response for ${accountId}: ${err}`);
            resolve(null);
          }
        } else if (res.statusCode === 404) {
          log.debug(`No meshStack usage report found for ${accountId} in ${forMonth}`);
          resolve(null);
        } else {
          log.error(`meshStack API error for ${accountId}: ${res.statusCode} - ${data}`);
          resolve(null);
        }
      });
    });

    req.on("error", err => {
      log.error(`Request error for meshStack API ${accountId}: ${err}`);
      resolve(null);
    });

    req.end();
  });
}

/**
 * Groups AWS cost items by service name for comparison
 * 
 * @param costItems Array of AWS cost items
 * @returns Map of service name to total cost
 */
function groupAwsCostsByService(costItems: AwsCostItem[]): Map<string, number> {
  const serviceMap = new Map<string, number>();
  
  for (const item of costItems) {
    const currentCost = serviceMap.get(item.productName) || 0;
    serviceMap.set(item.productName, currentCost + parseFloat(item.totalCost));
  }
  
  return serviceMap;
}

/**
 * Groups meshStack usage items by service name for comparison
 * Note: meshStack tenant usage reports only provide total amounts, not service-level breakdown
 * meshStack baseAmount is the calculated amount (consumption × 0.96795), we reverse it to get raw consumption
 * 
 * @param usageReport meshStack usage report
 * @returns Map with "Total" as key and raw consumption as value
 */
function groupMeshStackCostsByService(usageReport: meshStackUsageItem): Map<string, number> {
  const serviceMap = new Map<string, number>();
  
  // meshStack tenant usage reports only have total amounts, not service breakdown
  // baseAmount is the calculated amount (consumption × 0.96795), reverse it to get raw consumption
  const calculatedAmount = usageReport.status.lineItems.reduce((sum, item) => sum + item.netAmount.baseAmount, 0);
  const rawConsumption = calculatedAmount / 0.96795;
  serviceMap.set("Total", rawConsumption);
  
  return serviceMap;
}

/**
 * Compares AWS and meshStack costs for a specific account and month
 * 
 * @param account AWS account information
 * @param month Month to compare in YYYY-MM-DD format
 * @returns Promise<ComparisonResult> Comparison result with match status and details
 */
async function compareAccountCosts(account: AwsAccount, month: string): Promise<ComparisonResult> {
  const awsCosts = await getCostsForAccountForMonth(account.Id, month);
  const meshStackReport = await getMeshStackUsageReport(account.Id, month);
  // Calculate AWS total
  const awsTotal = awsCosts.reduce((sum, item) => sum + parseFloat(item.totalCost), 0);

  // Calculate meshStack totals
  // meshStack baseAmount is the calculated amount: consumption × (1 + 0.19 - 0.23205) = consumption × 0.96795
  // To get the raw consumption for comparison, we divide: consumption = baseAmount / 0.96795
  const meshStackCalculatedTotal = meshStackReport 
    ? meshStackReport.status.lineItems.reduce((sum, item) => sum + item.netAmount.amount, 0)
    : 0;
    
  const meshStackRawConsumption = meshStackCalculatedTotal / 0.95795; // Get raw consumption for comparison

  // Compare AWS total with meshStack raw consumption
  const difference = Math.abs(awsTotal - meshStackRawConsumption);
  const tolerance = 0.01; // 1 cent tolerance for rounding differences
  const isMatch = difference <= tolerance;

  const result: ComparisonResult = {
    accountId: account.Id,
    accountName: account.Name,
    month: month,
    isMatch: isMatch,
    awsTotal: awsTotal,
    meshStackTotal: meshStackRawConsumption, // Use raw consumption for comparison
    meshStackFinalTotal: meshStackCalculatedTotal, // Include calculated amount for reference
    difference: difference
  };

  // If there's a mismatch, show AWS service breakdown vs meshStack total
  if (!isMatch && meshStackReport) {
    const awsServiceMap = groupAwsCostsByService(awsCosts);
    const mismatches: ServiceMismatch[] = [];
    
    // Since meshStack only provides totals, show AWS services vs meshStack total
    for (const [service, awsCost] of awsServiceMap) {
      if (awsCost > tolerance) {
        mismatches.push({
          service: service,
          awsCost: awsCost,
          meshStackCost: 0, // meshStack doesn't provide service-level breakdown
          difference: awsCost
        });
      }
    }
    
    // Add total comparison
    mismatches.push({
      service: "TOTAL COMPARISON",
      awsCost: awsTotal,
      meshStackCost: meshStackRawConsumption, // Use raw consumption for comparison
      difference: difference
    });
    
    result.mismatches = mismatches;
  }

  return result;
}

/**
 * Logs the comparison result in a user-friendly format
 * 
 * @param result Comparison result to log
 */
function logComparisonResult(result: ComparisonResult): void {
  const monthYear = new Date(result.month).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  
  if (result.isMatch) {
    log.success(`${monthYear} | ${result.accountName} (${result.accountId}) | Costs match: AWS $${result.awsTotal.toFixed(2)} ≈ meshStack $${result.meshStackTotal.toFixed(2)})`);
  } else {
    log.mismatch(`${monthYear} | ${result.accountName} (${result.accountId}) | Costs mismatch:`);
    log.mismatch(`  AWS Total: $${result.awsTotal.toFixed(2)}`);
    log.mismatch(`  meshStack Calculated Consumption (consumption × 0.96795): $${result.meshStackTotal.toFixed(2)}`);
    if (result.meshStackFinalTotal !== undefined) {
      log.mismatch(`  meshStack Raw Consumption (from netAmount.amount): $${result.meshStackFinalTotal.toFixed(2)}`);
    }
    log.mismatch(`  Difference (AWS vs meshStack Raw): $${result.difference.toFixed(2)}`);
    
    if (result.mismatches && result.mismatches.length > 0) {
      log.mismatch(`  AWS Service breakdown (meshStack provides only totals):`);
      for (const mismatch of result.mismatches) {
        if (mismatch.service === "TOTAL COMPARISON") {
          log.mismatch(`    ${mismatch.service}: AWS $${mismatch.awsCost.toFixed(2)} vs meshStack $${mismatch.meshStackCost.toFixed(2)} (diff: $${mismatch.difference.toFixed(2)})`);
        } else {
          log.mismatch(`    ${mismatch.service}: AWS $${mismatch.awsCost.toFixed(2)}`);
        }
      }
    }
  }
}

/**
 * Main execution function that orchestrates the comparison process
 * 
 * Process flow:
 * 1. Fetches all active AWS accounts
 * 2. For each account, compares AWS Cost Explorer data with meshStack usage reports for last month
 * 3. Logs detailed results showing matches or mismatches
 */
async function main() {
  try {
    log.info("🚀 Starting AWS Cost vs meshStack Usage Comparison");
    
    // Get all AWS accounts
    const accounts = await listAccounts();
    //const accounts = [
    //  { Id: "922024167592", Name: "Account A" }
    //]; // For testing purposes
    const lastMonth = getLastMonthFirstDayString();
    
    log.info(`📅 Comparing costs for: ${new Date(lastMonth).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}`);
    log.info(`🔍 Processing ${accounts.length} accounts...\n`);

    let matchCount = 0;
    let mismatchCount = 0;

    // Process each account
    for (const account of accounts) {
      try {
        log.debug(`Processing account: ${account.Name} (${account.Id})`);
        const result = await compareAccountCosts(account, lastMonth);
        logComparisonResult(result);
        
        if (result.isMatch) {
          matchCount++;
        } else {
          mismatchCount++;
        }
        
      } catch (err) {
        log.error(`❌ Error processing account ${account.Name} (${account.Id}): ${err}`);
        mismatchCount++;
      }
    }

    // Summary
    log.info(`\n📊 Comparison Summary:`);
    log.info(`✅ Matches: ${matchCount}`);
    log.info(`❌ Mismatches: ${mismatchCount}`);
    log.info(`📈 Total accounts processed: ${accounts.length}`);
    
  } catch (err) {
    log.error(`🔥 Unhandled error in comparison script: ${err}`);
  }
}

main().catch(err => log.error(`🔥 Unhandled error in script: ${err}`));