const https = require('https');

// IONOS API credentials, only the main user can see the cost data
const username = process.env.IONOS_USERNAME;
const password = process.env.IONOS_PASSWORD;
const contract = process.env.IONOS_CONTRACT;
const meshcloudAuth = process.env.KRAKEN_API_KEY;
const meshStackApiEndpoint = process.env.MESHSTACK_API_ENDPOINT;
const meshStackPlatformIdentifier = process.env.MESHSTACK_PLATFORM_IDENTIFIER;

// Basic authentication for IONOS API
const auth = 'Basic ' + Buffer.from(username + ':' + password).toString('base64');

// logging
const logging = true;

function getCurrentMonthRange() {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const firstDay = `${year}-${String(month).padStart(2, '0')}-01`;
    const lastDay = new Date(year, month, 0).getDate();
    const toDate = `${year}-${String(month).padStart(2, '0')}-${lastDay}`;
    const monthString = `${year}-${String(month).padStart(2, '0')}`;
    return { fromDate: firstDay, toDate: toDate, monthString: monthString };
}

function getLastMonthRange() {
    const now = new Date();
    let year = now.getFullYear();
    let month = now.getMonth();

    if (month === 0) {
        month = 12;
        year -= 1;
    }

    const firstDay = `${year}-${String(month).padStart(2, '0')}-01`;
    const lastDay = new Date(year, month, 0).getDate();
    const toDate = `${year}-${String(month).padStart(2, '0')}-${lastDay}`;
    const monthString = `${year}-${String(month).padStart(2, '0')}`;
    return { fromDate: firstDay, toDate: toDate, monthString: monthString };
}

function getProductCosts() {
    console.log("🔍 Fetching product costs from IONOS...");
    const options = {
        hostname: 'api.ionos.com',
        path: `/billing/${contract}/products`,
        method: 'GET',
        headers: { 'Authorization': auth, 'Accept': 'application/json' }
    };
    return fetchData(options, "Product Costs");
}

function getUsage(monthString) {
    console.log("🔍 Fetching usage data from IONOS...");
    const options = {
        hostname: 'api.ionos.com',
        path: `/billing/${contract}/usage/?period=${monthString}`,
        method: 'GET',
        headers: { 'Authorization': auth, 'Accept': 'application/json' }
    };
    return fetchData(options, "Usage Data");
}

function fetchData(options, label) {
    return new Promise((resolve, reject) => {
        const req = https.request(options, (res) => {
            let data = '';
            res.on('data', (chunk) => { data += chunk; });
            res.on('end', () => {
                try {
                    const response = JSON.parse(data);
                    resolve(response);
                } catch (error) {
                    console.error(`❌ Error parsing ${label}:`, error);
                    reject(`Error parsing ${label}`);
                }
            });
        });
        req.on('error', (e) => {
            console.error(`❌ Error fetching ${label}:`, e);
            reject(e);
        });
        req.end();
    });
}

async function calculateCosts(mode = 'current') {
    const now = new Date();
    if (mode === 'last' && now.getDate() > 5) {
        console.log("⏳ Too late in the month – skipping cost fetch for last month.");
        return;
    }

    try {
        const { monthString, fromDate } = (mode === 'last') ? getLastMonthRange() : getCurrentMonthRange();
        const products = await getProductCosts();
        const usage = await getUsage(monthString);
        const result = [];

        usage.datacenters.forEach((datacenter) => {
            const datacenterResult = { id: datacenter.id, name: datacenter.name, meters: [] };
            datacenter.meters.forEach((meter) => {
                const matchedProduct = products.products.find(product =>
                    product.meterDesc && meter.meterDesc.includes(product.meterDesc)
                );
                datacenterResult.meters.push({
                    meterId: meter.meterId,
                    meterDesc: meter.meterDesc,
                    quantity: meter.quantity,
                    totalCost: matchedProduct ? (meter.quantity.quantity * parseFloat(matchedProduct.unitCost.quantity)).toFixed(2) : 'N/A',
                    unitCost: matchedProduct ? matchedProduct.unitCost : 'N/A'
                });
            });
            result.push(datacenterResult);
            if (logging) {
                console.log(datacenterResult);
            }
        });
        sendToMeshstack(result, fromDate);
    } catch (error) {
        console.error(`❌ Error calculating ${mode} costs:`, error);
    }
}

function sendToMeshstack(result, fromDate) {
    result.forEach(datacenter => {
        console.log(datacenter.id, "🚀 Sending IONOS billing data to MeshStack...");
        const projCostItems = datacenter.meters.map(meter => ({
            "productName": meter.meterDesc,
            "usageQuantity": meter.quantity.quantity,
            "usageType": "IONOS Service " + meter.meterId,
            "usageCost": meter.totalCost,
            "currency": "EUR",
            "usageUnit": meter.quantity.unit,
            "totalCost": meter.totalCost
        }));

        if (projCostItems.length === 0) {
            console.warn(`⚠️ No valid cost items found for datacenter ${datacenter.id}, skipping.`);
            return;
        }

        const postData = JSON.stringify({
            "apiVersion": "v1",
            "kind": "meshResourceUsageReport",
            "fullPlatformIdentifier": meshStackPlatformIdentifier,
            "source": "IONOS",
            "lineItems": projCostItems
        });

        const path = `/api/meshobjects/meshresourceusagereports/${encodeURIComponent(datacenter.id)}/${fromDate}Z`;
        console.log("🔍 Final API Path:", path);

        const options = {
            hostname: meshStackApiEndpoint,
            path: path,
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
                console.log(`✅ Response from MeshStack for datacenter ${datacenter.id}:`, response);
            });
        });

        req.on('error', (e) => {
            console.error(`❌ Error sending data for datacenter ${datacenter.id}:`, e);
        });

        req.write(postData);
        req.end();
    });
}

// Run both modes
calculateCosts('current');
calculateCosts('last');
