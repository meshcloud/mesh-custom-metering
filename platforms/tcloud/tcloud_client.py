"""
Client and pure transformation logic for the T-Cloud (Open Telekom Cloud)
Financial Dashboard API v2.

This module intentionally has no dependency on the shared core library so it
can be unit tested in isolation. Orchestration lives in main.py.

API reference: https://docs.otc.t-systems.com/enterprise-dashboard/api-ref/v2/
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

import requests

DEFAULT_BASE_URL = "https://api-enterprise-dashboard.otc-service.com"
DAILY_CONSUMPTION_PATH = "/v2/daily/consumption/"
# (connect timeout, read timeout between streamed chunks) in seconds
DEFAULT_TIMEOUT: Tuple[float, float] = (10, 300)
BODY_EXCERPT_LENGTH = 500
LINE_EXCERPT_LENGTH = 200

UNKNOWN_PRODUCT = "UNKNOWN"
CURRENCY = "EUR"
SELLER_ID = "T-Cloud"

# (product, product_description, quantity_type, consumption_type)
GroupKey = Tuple[str, str, str, str]


class TCloudApiError(Exception):
    """Raised for HTTP errors, malformed NDJSON or truncated streams."""

    def __init__(self, message: str, status_code: Optional[int] = None, body_excerpt: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body_excerpt = body_excerpt


def build_session(api_token: str) -> requests.Session:
    if not api_token or not api_token.strip():
        raise ValueError("TCLOUD_API_TOKEN must not be empty")

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {api_token.strip()}",
            "Accept": "application/x-ndjson",
            "User-Agent": "mesh-custom-metering/tcloud",
        }
    )
    return session


def fetch_daily_consumption(
    session: requests.Session,
    base_url: str,
    year: int,
    month: int,
    contract_id: Optional[int] = None,
    timeout: Tuple[float, float] = DEFAULT_TIMEOUT,
) -> Iterator[Dict[str, Any]]:
    """
    Stream the daily consumption records for one month.

    The API returns NDJSON (one JSON object per line) without pagination.
    Any malformed line or connection error mid-stream raises TCloudApiError:
    a truncated month must never be submitted to meshStack, because usage
    reports are full-period replacements.
    """
    url = f"{base_url.rstrip('/')}{DAILY_CONSUMPTION_PATH}"
    params: Dict[str, Any] = {"year": year, "month": month}
    if contract_id is not None:
        params["contract"] = contract_id

    logging.debug(f"Fetching T-Cloud daily consumption - URL: {url}, params: {params}")

    try:
        with session.get(url, params=params, stream=True, timeout=timeout) as response:
            if response.status_code >= 400:
                excerpt = (response.text or "")[:BODY_EXCERPT_LENGTH]
                raise TCloudApiError(
                    f"T-Cloud API returned HTTP {response.status_code}: {excerpt}",
                    status_code=response.status_code,
                    body_excerpt=excerpt,
                )

            for line_no, line in enumerate(response.iter_lines(chunk_size=65536, decode_unicode=True), start=1):
                if not line or not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as err:
                    raise TCloudApiError(
                        f"Malformed NDJSON at line {line_no}: {line[:LINE_EXCERPT_LENGTH]!r} ({err})"
                    ) from err
    except requests.exceptions.RequestException as err:
        raise TCloudApiError(f"T-Cloud API request failed: {err}") from err


@dataclass
class Aggregate:
    quantity: float = 0.0
    amount: float = 0.0
    records: int = 0


@dataclass
class AggregationResult:
    projects: Dict[str, Dict[GroupKey, Aggregate]] = field(default_factory=dict)
    total_records: int = 0
    skipped_no_project: int = 0
    status_counts: Dict[str, int] = field(default_factory=dict)


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def aggregate_by_project(records: Iterable[Dict[str, Any]]) -> AggregationResult:
    """
    Single streaming pass over consumption records. Memory is bounded by the
    number of distinct (project, product, unit, consumption type) groups, not
    by the number of records.
    """
    result = AggregationResult()

    for record in records:
        result.total_records += 1

        status = str(record.get("status") or "UNKNOWN")
        result.status_counts[status] = result.status_counts.get(status, 0) + 1

        project_id = str(record.get("project_id") or "").strip()
        if not project_id:
            result.skipped_no_project += 1
            continue

        key: GroupKey = (
            str(record.get("product") or UNKNOWN_PRODUCT),
            str(record.get("product_description") or ""),
            str(record.get("quantity_type") or ""),
            str(record.get("consumption_type") or ""),
        )

        groups = result.projects.setdefault(project_id, {})
        aggregate = groups.setdefault(key, Aggregate())
        aggregate.quantity += _as_float(record.get("quantity"))
        aggregate.amount += _as_float(record.get("amount"))
        aggregate.records += 1

    logging.debug(
        f"Aggregated {result.total_records} records into {len(result.projects)} projects "
        f"(skipped without project_id: {result.skipped_no_project}, status counts: {result.status_counts})"
    )
    return result


def build_usage_type(product: str, consumption_type: str) -> str:
    if consumption_type:
        return f"{product} ({consumption_type})"
    return product


def transform_to_line_items(groups: Dict[GroupKey, Aggregate]) -> List[Dict[str, Any]]:
    """
    Convert the aggregated groups of one project into meshStack line items,
    using the same schema as the other platforms.
    """
    line_items: List[Dict[str, Any]] = []

    for (product, description, unit, consumption_type), aggregate in groups.items():
        if aggregate.quantity == 0 and aggregate.amount == 0:
            logging.debug(f"Dropping zero group: {product} ({consumption_type})")
            continue

        if aggregate.quantity == 0:
            usage_cost = 0.0
        else:
            usage_cost = aggregate.amount / aggregate.quantity

        line_item = {
            "productName": description or product,
            "usageQuantity": round(aggregate.quantity, 6),
            "usageType": build_usage_type(product, consumption_type),
            "usageCost": round(usage_cost, 4),
            "currency": CURRENCY,
            "usageUnit": unit,
            "totalCost": round(aggregate.amount, 2),
            "sellerId": SELLER_ID,
        }
        logging.debug(f"Created line item: {line_item}")
        line_items.append(line_item)

    line_items.sort(key=lambda item: item["usageType"])
    return line_items


def parse_contract_ids(raw: Optional[str]) -> List[Optional[int]]:
    """
    TCLOUD_CONTRACT_IDS is a comma-separated list of contract numbers.
    When unset, a single unfiltered request is made (represented as [None]).
    """
    if raw is None or not raw.strip():
        return [None]

    contract_ids: List[Optional[int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            contract_ids.append(int(part))
        except ValueError as err:
            raise ValueError(f"TCLOUD_CONTRACT_IDS contains a non-integer value: {part!r}") from err

    return contract_ids or [None]
