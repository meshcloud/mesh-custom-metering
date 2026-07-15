import os
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import jwt
import requests

STACKIT_DEFAULT_TOKEN_ENDPOINT = "https://service-account.api.stackit.cloud/token"

class ServiceAccountKeyAuth(requests.auth.AuthBase):
    """
    JWT-bearer auth for a STACKIT service account key: sign a short-lived JWT
    assertion with the key's private key, exchange it at the token endpoint
    for an access token, and re-mint a fresh assertion whenever it's near
    expiry (this token endpoint doesn't issue refresh tokens, so there's no
    refresh grant to fall back to).
    """

    EXPIRY_LEEWAY_SECONDS = 60

    def __init__(self, credentials: Dict, token_endpoint: str):
        self.credentials = credentials
        self.token_endpoint = token_endpoint
        self.access_token: Optional[str] = None
        self.expires_at: float = 0

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        if time.time() >= self.expires_at:
            self._fetch_token()
        r.headers["Authorization"] = f"Bearer {self.access_token}"
        return r

    def _fetch_token(self) -> None:
        now = datetime.now(timezone.utc)
        assertion = jwt.encode(
            {
                "iss": self.credentials["iss"],
                "sub": self.credentials["sub"],
                "aud": self.credentials["aud"],
                "jti": str(uuid.uuid4()),
                "iat": now,
                "exp": now + timedelta(minutes=10),
            },
            self.credentials["privateKey"],
            headers={"kid": str(self.credentials["kid"])},
            algorithm="RS512",
        )

        response = requests.post(
            self.token_endpoint,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()

        self.access_token = token_data["access_token"]
        self.expires_at = time.time() + token_data.get("expires_in", 300) - self.EXPIRY_LEEWAY_SECONDS


def build_stackit_auth() -> requests.auth.AuthBase:
    """
    STACKIT_SERVICE_ACCOUNT_TOKEN holds the full JSON service account key
    downloaded from the STACKIT portal.
    """
    raw_value = os.environ.get('STACKIT_SERVICE_ACCOUNT_TOKEN')
    if not raw_value:
        raise ValueError("STACKIT_SERVICE_ACCOUNT_TOKEN environment variable is not set")

    try:
        key_data = json.loads(raw_value)
    except json.JSONDecodeError as e:
        raise ValueError(f"STACKIT_SERVICE_ACCOUNT_TOKEN is not valid JSON: {e}") from e

    try:
        credentials = key_data['credentials']
    except KeyError as e:
        raise ValueError("STACKIT_SERVICE_ACCOUNT_TOKEN JSON is missing the 'credentials' key") from e
    token_endpoint = (
        os.environ.get('STACKIT_TOKEN_BASEURL')
        or credentials.get('tokenEndpoint')
        or STACKIT_DEFAULT_TOKEN_ENDPOINT
    )
    return ServiceAccountKeyAuth(credentials, token_endpoint)
