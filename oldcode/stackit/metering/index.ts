const https = require('https');

const stackitAuth = process.env.STACKIT_SERVICE_ACCOUNT_TOKEN;
const meshcloudAuth = process.env.KRAKEN_API_KEY;
const meshStackApiEndpoint = process.env.MESHSTACK_API_ENDPOINT;
const meshStackPlatformIdentifier = process.env.MESHSTACK_PLATFORM_IDENTIFIER;
const stackitContainerParentId = process.env.STACKIT_CONTAINER_PARENT_ID ? process.env.STACKIT_CONTAINER_PARENT_ID.split(',') : [];

let completedContainers = 0;
const totalContainers = stackitContainerParentId.length;

function fetchProjects(containerParentId) {
    console.log(`🔍 Fetching active StackIT projects for containerParentId: ${containerParentId}...`);

    const options = {
        hostname: 'resource-manager.api.stackit.cloud',
        path: `/v2/projects?containerParentId=${containerParentId}`,
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${stackitAuth}`,
            'Accept': 'application/json'
        }
    };

    const req = https.request(options, (res) => {
        let data = '';

        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
            try {
                const projects = JSON.parse(data);
                const activeProjects = projects.items.filter(p => p.lifecycleState === "ACTIVE");
                console.log(`✅ Found ${activeProjects.length} active projects.`);
                getProjectCurrentCosts(activeProjects,containerParentId);
                getProjectLastMonthCosts(activeProjects,containerParentId);
                
                completedContainers++;
                if (completedContainers === totalContainers) {
                    console.log(`✅ Successfully finished collecting cost and metering for all containerParentIDs`);
                }
            } catch (error) {
                console.error("❌ Error parsing project JSON:", error, "\nRaw data:", data);
            }
        });
    });

    req.on('error', (e) => {
        console.error('❌ Error fetching StackIT projects:', e);
    });
    req.end();
}

function getActiveProjects() {
    stackitContainerParentId.forEach(containerParentId => {
        fetchProjects(containerParentId);
    });
}

function getCurrentMonthRange() {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const firstDay = `${year}-${String(month).padStart(2, '0')}-01`;
    const lastDay = new Date(year, month, 0).getDate(); // Last day of the month
    const toDate = `${year}-${String(month).padStart(2, '0')}-${lastDay}`;

    return {
        fromDate: firstDay,
        toDate: toDate
    };
}

function getLastMonthRange() {
    const now = new Date();
    const year = now.getFullYear();
    let month = now.getMonth();

    if (month === 0) {
        month = 12;
        year -= 1;
    }

    const firstDay = `${year}-${String(month).padStart(2, '0')}-01`;
    const lastDay = new Date(year, month, 0).getDate();
    const toDate = `${year}-${String(month).padStart(2, '0')}-${lastDay}`;

    return {
        fromDate: firstDay,
        toDate: toDate
    };
}

function getProjectCurrentCosts(projects, currentParentId) {
    console.log("🔍 Fetching cost data for active projects...");

    const { fromDate, toDate } = getCurrentMonthRange();
    const granularity = "monthly";

    const options = {
        hostname: 'cost.api.stackit.cloud',
        path: `/v3/costs/${currentParentId}?from=${fromDate}&to=${toDate}&granularity=${granularity}&depth=service`,
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${stackitAuth}`,
            'Accept': 'application/json'
        }
    };

    const req = https.request(options, (res) => {
        let data = '';

        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
            try {
                const parsedData = JSON.parse(data);
                if (parsedData && Array.isArray(parsedData)) {
                    console.log(`Found ${parsedData.length} cost records`);
                    for (let index = 0; index < parsedData.length; index++) {
                        const element = parsedData[index];
                        if (element && element.projectId) {
                            sendToMeshstack(JSON.stringify(element), element.projectId, fromDate);
                        } else {
                            console.warn('⚠️ Skipping element with missing projectId:', element);
                        }
                    }
                } else {
                    console.warn('⚠️ Invalid or empty cost data received');
                }
            } catch (error) {
                console.error('❌ Error parsing cost data:', error, '\nRaw data:', data);
            }
            if (!data || data.trim() === "") {
                console.warn(`⚠️ No billing data found. Skipping.`);
                return;
            }
        });
    });

    req.on('error', (e) => {
        console.error(`❌ Error fetching cost data:`, e);
    });
    req.end();
}

function getProjectLastMonthCosts(projects, currentParentId) {
    const now = new Date();
    const currentDay = now.getDate();

    if (currentDay >= 5) {
        console.log("⏳ Too late in the month – skipping cost fetch for last month.");
        return;
    }

    console.log("🔍 Fetching cost data for active projects...");

    const { fromDate, toDate } = getLastMonthRange();
    const granularity = "monthly";

    projects.forEach(project => {
        const projectId = project.projectId;
        const options = {
            hostname: 'cost.api.stackit.cloud',
            path: `/v3/costs/${currentParentId}?from=${fromDate}&to=${toDate}&granularity=${granularity}&depth=service`,
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${stackitAuth}`,
                'Accept': 'application/json'
            }
        };

        const req = https.request(options, (res) => {
            let data = '';

            res.on('data', (chunk) => { data += chunk; });
            res.on('end', () => {
                try {
                    const parsedData = JSON.parse(data);
                    if (parsedData && Array.isArray(parsedData)) {
                        console.log(`Found ${parsedData.length} last month cost records`);
                        for (let index = 0; index < parsedData.length; index++) {
                            const element = parsedData[index];
                            if (element && element.projectId) {
                                sendToMeshstack(JSON.stringify(element), element.projectId, fromDate);
                            } else {
                                console.warn('⚠️ Skipping last month element with missing projectId:', element);
                            }
                        }
                    } else {
                        console.warn('⚠️ Invalid or empty last month cost data received');
                    }
                } catch (error) {
                    console.error('❌ Error parsing last month cost data:', error, '\nRaw data:', data);
                }
                if (!data || data.trim() === "") {
                    console.warn(`⚠️ No billing data found. Skipping.`);
                    return;
                }
            });
        });

        req.on('error', (e) => {
            console.error(`❌ Error fetching cost data for project ${projectId}:`, e);
        });
        req.end();
    });
}

function sendToMeshstack(projCostStr, projectId, fromDate) {
    console.log(projectId, " 🚀 Sending cost data to MeshStack...");
    console.log("📝 Raw cost data:", projCostStr);

    let projCostObj;
    try {
        projCostObj = JSON.parse(projCostStr);
    } catch (error) {
        console.error("❌ JSON Parse Error in sendToMeshstack:", error, "\nRaw input:", projCostStr);
        return;
    }

    if (!projCostObj || !projCostObj.services) {
        console.error("❌ Invalid or empty data structure received:", projCostObj);
        return;
    }

    // Extracting cost data from the response and formatting it to match MeshStack's expected structure
    const projCostItems = projCostObj.services.map(service => service.reportData.map(item => {
        // Calculate usageCost, handling the case where item.quantity is 0
        const usageCostValue = item.quantity === 0 ? 0 : ((item.charge / 100) / item.quantity);

        return {
            "productName": `${service.serviceName}`,
            "usageQuantity": item.quantity,
            "usageType": service.serviceCategoryName,
            "usageCost": usageCostValue.toFixed(2), // Apply toFixed(2) after the conditional check
            "currency": "EUR",
            "usageUnit": service.unitLabel,
            "totalCost": (item.charge / 100).toFixed(2)
        };
    })).flat();
    if (projCostItems.length === 0) {
        console.warn(projectId," ⚠️ No valid cost items found, skipping MeshStack request ");
        return;
    }

    const postData = JSON.stringify({
        "apiVersion": "v1",
        "kind": "meshResourceUsageReport",
        "fullPlatformIdentifier": meshStackPlatformIdentifier,
        "source": "StackIT",
        "lineItems": projCostItems
    });

     console.log("📡 Sending payload to MeshStack:", postData);

    const options = {
        hostname: meshStackApiEndpoint,
        path: `/api/meshobjects/meshresourceusagereports/${projectId}/${fromDate}Z`, // projectId as platformTenantId
        method: 'PUT',
        headers: {
            'Content-Type': 'application/vnd.meshcloud.api.meshobjects.v1+json;charset=UTF-8',
            'Authorization': `Basic ${meshcloudAuth}`,
            'Content-Length': Buffer.byteLength(postData),
            'Accept': 'application/vnd.meshcloud.api.meshobjects.v1+json'

        }
    };

    const req = https.request(options, (res) => {
        let response = '';
        res.on('data', (chunk) => { response += chunk; });
        res.on('end', () => {
            console.log(projectId," ✅ Response from MeshStack:", response);
        });
    });

    req.on('error', (e) => {
        console.error('❌ Error sending data to MeshStack:', e);
    });
    req.write(postData);
    req.end();
}

getActiveProjects();
