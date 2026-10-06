import json

import pytest
import requests

from helpers import PROJECT_A, PROJECT_B, FakeResponse, FakeSession, daily_record
from tcloud_client import (
    DEFAULT_BASE_URL,
    Aggregate,
    TCloudApiError,
    aggregate_by_project,
    build_session,
    build_usage_type,
    fetch_daily_consumption,
    parse_contract_ids,
    transform_to_line_items,
)


# --- build_session -----------------------------------------------------------

def test_build_session_sets_headers():
    session = build_session("  secret-token ")
    assert session.headers["Authorization"] == "Bearer secret-token"
    assert session.headers["Accept"] == "application/x-ndjson"


@pytest.mark.parametrize("token", ["", "   ", None])
def test_build_session_requires_token(token):
    with pytest.raises(ValueError):
        build_session(token)


# --- fetch_daily_consumption -------------------------------------------------

def test_fetch_parses_ndjson_and_skips_blank_lines():
    lines = [json.dumps(daily_record()), "", "   ", json.dumps(daily_record(project_id=PROJECT_B)), json.dumps(daily_record())]
    session = FakeSession(FakeResponse(lines))

    records = list(fetch_daily_consumption(session, DEFAULT_BASE_URL, 2025, 9))

    assert len(records) == 3
    assert records[1]["project_id"] == PROJECT_B
    assert session.last_url == f"{DEFAULT_BASE_URL}/v2/daily/consumption/"
    assert session.last_params == {"year": 2025, "month": 9}
    assert session.last_kwargs["stream"] is True
    assert session.response.closed is True


def test_fetch_strips_trailing_slash_from_base_url():
    session = FakeSession(FakeResponse([]))
    list(fetch_daily_consumption(session, "https://example.test/", 2025, 1))
    assert session.last_url == "https://example.test/v2/daily/consumption/"


def test_fetch_adds_contract_param():
    session = FakeSession(FakeResponse([]))
    list(fetch_daily_consumption(session, DEFAULT_BASE_URL, 2025, 9, contract_id=4711))
    assert session.last_params == {"year": 2025, "month": 9, "contract": 4711}


def test_fetch_malformed_line_raises():
    lines = [json.dumps(daily_record()), '{"amount": 1.0, "broken"']
    session = FakeSession(FakeResponse(lines))

    with pytest.raises(TCloudApiError) as exc_info:
        list(fetch_daily_consumption(session, DEFAULT_BASE_URL, 2025, 9))

    assert "line 2" in str(exc_info.value)


def test_fetch_http_error_includes_status_and_body():
    session = FakeSession(FakeResponse(status_code=401, text='{"detail": "invalid token"}'))

    with pytest.raises(TCloudApiError) as exc_info:
        list(fetch_daily_consumption(session, DEFAULT_BASE_URL, 2025, 9))

    assert exc_info.value.status_code == 401
    assert "invalid token" in exc_info.value.body_excerpt
    assert "401" in str(exc_info.value)


def test_fetch_wraps_mid_stream_connection_error():
    lines = [json.dumps(daily_record()), json.dumps(daily_record())]
    session = FakeSession(FakeResponse(lines, raise_after=1))
    consumed = []

    with pytest.raises(TCloudApiError):
        consumed.extend(fetch_daily_consumption(session, DEFAULT_BASE_URL, 2025, 9))

    # the first record was streamed before the connection broke; the error still propagates
    assert len(consumed) == 1


def test_fetch_wraps_request_exception_on_connect():
    class BrokenSession:
        def get(self, *args, **kwargs):
            raise requests.exceptions.ConnectionError("no route to host")

    with pytest.raises(TCloudApiError) as exc_info:
        list(fetch_daily_consumption(BrokenSession(), DEFAULT_BASE_URL, 2025, 9))

    assert exc_info.value.status_code is None


# --- aggregate_by_project ----------------------------------------------------

def test_aggregate_sums_same_product_across_days_and_regions(sample_records):
    result = aggregate_by_project(sample_records)

    el_group = result.projects[PROJECT_A][("OTC_KMS_UD_C", "KMS Customer Masterkey", "h", "EL")]
    assert el_group.quantity == pytest.approx(66.0)   # 24 + 24 + 12 + 6 (EU-NL merged)
    assert el_group.amount == pytest.approx(0.275)
    assert el_group.records == 4


def test_aggregate_keeps_el_and_rc_apart(sample_records):
    result = aggregate_by_project(sample_records)

    groups = result.projects[PROJECT_A]
    assert ("OTC_KMS_UD_C", "KMS Customer Masterkey", "h", "RC") in groups
    assert groups[("OTC_KMS_UD_C", "KMS Customer Masterkey", "h", "RC")].amount == pytest.approx(10.0)
    assert len(groups) == 2


def test_aggregate_separates_projects_and_counts_skipped(sample_records):
    result = aggregate_by_project(sample_records)

    assert set(result.projects) == {PROJECT_A, PROJECT_B}
    assert result.projects[PROJECT_B][("OTC_ECS_S3", "ECS s3.large", "h", "EL")].quantity == 100.0
    assert result.total_records == 7
    assert result.skipped_no_project == 1
    assert result.status_counts == {"NEW": 6, "AGGREGATION_PROCESSED": 1}


def test_aggregate_handles_null_values_and_missing_product():
    records = [
        daily_record(quantity=None, amount=None),
        daily_record(product=None, product_description=None, quantity=2, amount=1),
    ]
    result = aggregate_by_project(records)

    groups = result.projects[PROJECT_A]
    assert groups[("OTC_KMS_UD_C", "KMS Customer Masterkey", "h", "EL")].quantity == 0.0
    assert ("UNKNOWN", "", "h", "EL") in groups


def test_aggregate_accepts_generator():
    result = aggregate_by_project(daily_record() for _ in range(3))
    assert result.total_records == 3
    assert result.projects[PROJECT_A][("OTC_KMS_UD_C", "KMS Customer Masterkey", "h", "EL")].records == 3


# --- transform_to_line_items -------------------------------------------------

def test_transform_fields_and_rounding():
    groups = {("OTC_KMS_UD_C", "KMS Customer Masterkey", "h", "EL"): Aggregate(quantity=60.0, amount=0.25, records=3)}

    [item] = transform_to_line_items(groups)

    assert item == {
        "productName": "KMS Customer Masterkey",
        "usageQuantity": 60.0,
        "usageType": "OTC_KMS_UD_C (EL)",
        "usageCost": 0.0042,
        "currency": "EUR",
        "usageUnit": "h",
        "totalCost": 0.25,
        "sellerId": "T Cloud",
    }


def test_transform_zero_quantity_keeps_total_cost():
    groups = {("OTC_X", "Flat fee", "", "RC"): Aggregate(quantity=0.0, amount=12.5)}

    [item] = transform_to_line_items(groups)

    assert item["usageCost"] == 0
    assert item["totalCost"] == 12.5
    assert item["usageUnit"] == ""


def test_transform_drops_all_zero_group_and_keeps_free_usage():
    groups = {
        ("OTC_ZERO", "Nothing", "h", "EL"): Aggregate(quantity=0.0, amount=0.0),
        ("OTC_FREE", "Free tier", "GB", "EL"): Aggregate(quantity=10.0, amount=0.0),
    }

    items = transform_to_line_items(groups)

    assert [item["usageType"] for item in items] == ["OTC_FREE (EL)"]
    assert items[0]["totalCost"] == 0.0


def test_transform_falls_back_to_product_code_without_description():
    groups = {("OTC_NO_DESC", "", "h", "EL"): Aggregate(quantity=1.0, amount=1.0)}
    [item] = transform_to_line_items(groups)
    assert item["productName"] == "OTC_NO_DESC"


def test_transform_output_sorted_by_usage_type():
    groups = {
        ("OTC_B", "b", "h", "EL"): Aggregate(quantity=1.0, amount=1.0),
        ("OTC_A", "a", "h", "RC"): Aggregate(quantity=1.0, amount=1.0),
        ("OTC_A", "a", "h", "EL"): Aggregate(quantity=1.0, amount=1.0),
    }
    items = transform_to_line_items(groups)
    assert [item["usageType"] for item in items] == ["OTC_A (EL)", "OTC_A (RC)", "OTC_B (EL)"]


def test_build_usage_type_without_consumption_type():
    assert build_usage_type("OTC_A", "") == "OTC_A"
    assert build_usage_type("OTC_A", "RC") == "OTC_A (RC)"


# --- parse_contract_ids ------------------------------------------------------

@pytest.mark.parametrize("raw", [None, "", "   ", ","])
def test_parse_contract_ids_unset_means_single_unfiltered_call(raw):
    assert parse_contract_ids(raw) == [None]


def test_parse_contract_ids_splits_and_strips():
    assert parse_contract_ids(" 1000012345, 1000067890 ,") == [1000012345, 1000067890]


def test_parse_contract_ids_rejects_non_integer():
    with pytest.raises(ValueError, match="abc"):
        parse_contract_ids("1,abc")
