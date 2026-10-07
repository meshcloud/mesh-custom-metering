import os
import sys
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests

from tcloud_client import (
    DEFAULT_BASE_URL,
    TCloudApiError,
    aggregate_by_project,
    build_session,
    fetch_daily_consumption,
    parse_contract_ids,
    transform_to_line_items,
)

# We have to load the core libraries from different locations depending on whether its running in Docker or not.
DOCKER_CORE_PATH = Path('/app/core')
LOCAL_CORE_PATH = Path(__file__).parent.parent.parent / 'src' / 'core'
sys.path.append(str(DOCKER_CORE_PATH if DOCKER_CORE_PATH.is_dir() else LOCAL_CORE_PATH))
from meshstack_client import MeshStackClient, prepare_payload  # noqa: E402
from utils import get_current_and_last_month, format_date_for_meshstack, should_process_last_month  # noqa: E402
from logging_config import setup_logging  # noqa: E402

# meshStack (kraken) only allows letters, digits and spaces in the report source, so no hyphen here.
SOURCE_NAME = "T Cloud"
TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass
class TCloudConfig:
    api_token: str
    base_url: str = DEFAULT_BASE_URL
    # [None] means a single request without contract filter
    contract_ids: List[Optional[int]] = field(default_factory=lambda: [None])
    dry_run: bool = False


def load_tcloud_config() -> TCloudConfig:
    """
    Reads the TCLOUD_* environment variables and fails fast on invalid input,
    before any meshStack call is made.
    """
    api_token = os.environ.get('TCLOUD_API_TOKEN')
    if not api_token or not api_token.strip():
        raise ValueError("TCLOUD_API_TOKEN environment variable is not set")

    base_url = (os.environ.get('TCLOUD_API_BASE_URL') or DEFAULT_BASE_URL).rstrip('/')
    contract_ids = parse_contract_ids(os.environ.get('TCLOUD_CONTRACT_IDS'))
    dry_run = os.environ.get('TCLOUD_DRY_RUN', 'false').strip().lower() in TRUE_VALUES

    return TCloudConfig(
        api_token=api_token.strip(),
        base_url=base_url,
        contract_ids=contract_ids,
        dry_run=dry_run,
    )


def _log_fetch_error(err: TCloudApiError, month: str, contract_id: Optional[int]) -> None:
    scope = f"month {month}" + (f", contract {contract_id}" if contract_id is not None else "")
    if err.status_code in (401, 403):
        logging.error(
            f"T-Cloud API rejected the API key for {scope} (HTTP {err.status_code}). "
            f"Financial Dashboard API keys are valid for at most 90 days; check that TCLOUD_API_TOKEN "
            f"is current and was created with the 'Admin' security level. Response: {err.body_excerpt}"
        )
    elif err.status_code in (400, 422):
        logging.error(f"T-Cloud API rejected the request for {scope} (HTTP {err.status_code}): {err.body_excerpt}")
    else:
        logging.error(f"Failed to fetch T-Cloud consumption for {scope}: {err}")


def process_month(
    mesh_client: MeshStackClient,
    session: requests.Session,
    config: TCloudConfig,
    platform_id: str,
    month: str,
    contract_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Fetch one month (optionally for one contract), aggregate per project and
    submit one usage report per project. A fetch failure skips the whole
    month so that a partial result never overwrites a complete report.
    """
    stats = {"fetched_records": 0, "projects": 0, "submitted": 0, "failed": 0, "fetch_failed": 0}
    scope = f"month {month}" + (f", contract {contract_id}" if contract_id is not None else "")
    logging.info(f"Processing T-Cloud costs for {scope}")

    year, month_number = (int(part) for part in month.split("-"))

    try:
        records = fetch_daily_consumption(session, config.base_url, year, month_number, contract_id)
        result = aggregate_by_project(records)
    except TCloudApiError as err:
        _log_fetch_error(err, month, contract_id)
        stats["fetch_failed"] = 1
        return stats

    stats["fetched_records"] = result.total_records
    stats["projects"] = len(result.projects)
    logging.info(
        f"Fetched {result.total_records} records for {scope} across {len(result.projects)} projects "
        f"(status counts: {result.status_counts})"
    )
    if result.skipped_no_project:
        logging.warning(f"Skipped {result.skipped_no_project} records without project_id for {scope}")

    meshstack_date = format_date_for_meshstack(month)
    logging.debug(f"MeshStack formatted date: {meshstack_date}")

    for project_id in sorted(result.projects):
        logging.info(f"Processing project {project_id}")

        line_items = transform_to_line_items(result.projects[project_id])

        if not line_items:
            logging.info(f"No costs for project {project_id} in {month}")
            continue

        logging.debug(f"Prepared {len(line_items)} line items for project {project_id}")

        payload = prepare_payload(line_items, platform_id, SOURCE_NAME)
        logging.debug(f"Payload for project {project_id}: {payload}")

        if config.dry_run:
            total = round(sum(item["totalCost"] for item in line_items), 2)
            logging.info(
                f"[DRY RUN] Would submit report for project {project_id}: "
                f"{len(line_items)} line items, total {total} {line_items[0]['currency']}"
            )
            stats["submitted"] += 1
            continue

        response = mesh_client.submit_usage_report(project_id, meshstack_date, payload)

        if response['status'] == 'success':
            logging.info(f"Successfully submitted report for project {project_id}")
            stats["submitted"] += 1
        else:
            logging.error(f"Failed to submit report for {project_id}: {response.get('message')}")
            stats["failed"] += 1

    logging.info(
        f"Finished {scope}: projects={stats['projects']} submitted={stats['submitted']} failed={stats['failed']}"
    )
    return stats


def main() -> int:
    setup_logging(
        level=os.environ.get('LOG_LEVEL', 'INFO'),
        loki_url=os.environ.get('LOKI_URL'),
        platform_name='tcloud'
    )

    logging.info("Starting T-Cloud metering collection")

    # Validate T-Cloud configuration first so misconfiguration fails fast.
    config = load_tcloud_config()
    if config.dry_run:
        logging.info("DRY RUN enabled: no usage reports will be submitted to meshStack")

    meshfed_host = os.environ['MESHSTACK_MESHFED_URL']
    kraken_host = os.environ['MESHSTACK_KRAKEN_URL']
    mesh_user = os.environ['MESHSTACK_API_USER']
    mesh_secret = os.environ['MESHSTACK_API_SECRET']
    platform_id = os.environ['PLATFORM_ID']
    usage_period = os.environ.get('USAGE_PERIOD')

    mesh_client = MeshStackClient(meshfed_host, kraken_host, mesh_user, mesh_secret)

    months = get_current_and_last_month(usage_period)
    months_to_process = [months['current_month']]

    if should_process_last_month():
        months_to_process.append(months['last_month'])
        logging.info("Processing both current and last month (first 5 days)")

    totals = {"fetched_records": 0, "projects": 0, "submitted": 0, "failed": 0, "fetch_failed": 0}

    session = build_session(config.api_token)
    try:
        for contract_id in config.contract_ids:
            if contract_id is not None:
                logging.info(f"Processing contract: {contract_id}")

            for month in months_to_process:
                stats = process_month(mesh_client, session, config, platform_id, month, contract_id)
                for key, value in stats.items():
                    totals[key] += value
    finally:
        session.close()

    logging.info(
        f"T-Cloud metering collection completed: records={totals['fetched_records']} "
        f"projects={totals['projects']} submitted={totals['submitted']} failed={totals['failed']} "
        f"fetch_failures={totals['fetch_failed']}"
    )

    if totals["fetch_failed"]:
        logging.error("At least one T-Cloud fetch failed; exiting with status 1")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
