#!/bin/bash

set -euo pipefail

CONFIG=$1
TOKEN_URL="https://service-account.api.stackit.cloud/token"

# --- Konfiguration aus JSON-Datei lesen ---
ISS=$(jq -r '.credentials.iss' "$CONFIG")
SUB=$(jq -r '.credentials.sub' "$CONFIG")
AUD=$(jq -r '.credentials.aud' "$CONFIG")
KID=$(jq -r '.credentials.kid' "$CONFIG")
PRIVATE_KEY_RAW=$(jq -r '.credentials.privateKey' "$CONFIG")

# --- Write private key in file ---
PRIVATE_KEY_FILE=$(mktemp)
echo "$PRIVATE_KEY_RAW" | sed 's/\\n/\n/g' > "$PRIVATE_KEY_FILE"

# --- Timestamp for JWT ---
NOW=$(date +%s)
EXP=$((NOW + 600))  # Set token validity to ten minutes
JTI=$(uuidgen) # Optional in spec but mandatory for STACKIT

# --- JWT header & payload ---
HEADER=$(jq -nc --arg kid "$KID" '{alg:"RS512", typ:"JWT", kid:$kid}')
PAYLOAD=$(jq -nc \
  --arg iss "$ISS" \
  --arg sub "$SUB" \
  --arg aud "$AUD" \
  --arg jti "$JTI" \
  --argjson iat "$NOW" \
  --argjson exp "$EXP" \
  '{iss:$iss, sub:$sub, aud:$aud, iat:$iat, exp:$exp, jti:$jti}')

# --- Base64URL encode function ---
b64enc() {
  openssl base64 -e -A | tr '+/' '-_' | tr -d '='
}

# --- Build and sign JWT ---
HEADER_B64=$(echo -n "$HEADER" | b64enc)
PAYLOAD_B64=$(echo -n "$PAYLOAD" | b64enc)
DATA="${HEADER_B64}.${PAYLOAD_B64}"

SIGNATURE=$(echo -n "$DATA" | openssl dgst -sha512 -sign "$PRIVATE_KEY_FILE" | b64enc)
JWT="${DATA}.${SIGNATURE}"

echo "$JWT"

# --- Request access token ---
echo "�55357;�56592; Request to $TOKEN_URL ..."
RESPONSE=$(curl --fail -sS -X POST "$TOKEN_URL" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer" \
  -d "assertion=$JWT") || {
    echo "❌ Error acquiring token"
    exit 1
}

# --- Extract access token ---
ACCESS_TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')

if [[ "$ACCESS_TOKEN" == "null" || -z "$ACCESS_TOKEN" ]]; then
  echo "❌ Did not receive access token!"
  echo "$RESPONSE"
  exit 1
fi

# --- Output ---
echo "✅ Received access token:"
echo "$ACCESS_TOKEN"

# --- Cleanup ---
rm -f "$PRIVATE_KEY_FILE"
