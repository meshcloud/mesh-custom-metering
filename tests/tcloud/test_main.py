import logging

import pytest

from helpers import PROJECT_A, PROJECT_B, FakeSession, FakeResponse
from tcloud_client import TCloudApiError

MESH_ENV = {
    "MESHSTACK_MESHFED_URL": "https://meshfed.example.test",
    "MESHSTACK_KRAKEN_URL": "https://kraken.example.test",
    "MESHSTACK_API_USER": "user",
    "MESHSTACK_API_SECRET": "secret",
    "PLATFORM_ID": "tcloud.test",
}


def set_env(monkeypatch, **extra):
    for key in ("TCLOUD_API_TOKEN", "TCLOUD_API_BASE_URL", "TCLOUD_CONTRACT_IDS", "TCLOUD_DRY_RUN", "USAGE_PERIOD", "LOKI_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**MESH_ENV, **extra}.items():
        monkeypatch.setenv(key, value)


# --- load_tcloud_config ------------------------------------------------------

def test_load_config_fails_fast_without_token(tcloud_main, monkeypatch):
    set_env(monkeypatch)
    with pytest.raises(ValueError, match="TCLOUD_API_TOKEN"):
        tcloud_main.load_tcloud_config()


def test_load_config_defaults(tcloud_main, monkeypatch):
    set_env(monkeypatch, TCLOUD_API_TOKEN="abc")
    config = tcloud_main.load_tcloud_config()

    assert config.api_token == "abc"
    assert config.base_url == "https://api-enterprise-dashboard.otc-service.com"
    assert config.contract_ids == [None]
    assert config.dry_run is False


def test_load_config_parses_overrides(tcloud_main, monkeypatch):
    set_env(
        monkeypatch,
        TCLOUD_API_TOKEN="abc",
        TCLOUD_API_BASE_URL="https://proxy.example.test/",
        TCLOUD_CONTRACT_IDS="1, 2",
        TCLOUD_DRY_RUN="True",
    )
    config = tcloud_main.load_tcloud_config()

    assert config.base_url == "https://proxy.example.test"
    assert config.contract_ids == [1, 2]
    assert config.dry_run is True


def test_load_config_rejects_bad_contract_ids(tcloud_main, monkeypatch):
    set_env(monkeypatch, TCLOUD_API_TOKEN="abc", TCLOUD_CONTRACT_IDS="abc")
    with pytest.raises(ValueError, match="TCLOUD_CONTRACT_IDS"):
        tcloud_main.load_tcloud_config()


# --- process_month -----------------------------------------------------------

def _patch_fetch(monkeypatch, tcloud_main, records):
    calls = []

    def fake_fetch(session, base_url, year, month, contract_id=None):
        calls.append({"base_url": base_url, "year": year, "month": month, "contract_id": contract_id})
        return iter(records)

    monkeypatch.setattr(tcloud_main, "fetch_daily_consumption", fake_fetch)
    return calls


def test_process_month_submits_one_report_per_project(tcloud_main, monkeypatch, sample_records, fake_mesh_client_factory):
    calls = _patch_fetch(monkeypatch, tcloud_main, sample_records)
    mesh = fake_mesh_client_factory()
    config = tcloud_main.TCloudConfig(api_token="t", base_url="https://api.test")

    stats = tcloud_main.process_month(mesh, object(), config, "tcloud.test", "2025-09", contract_id=42)

    assert calls == [{"base_url": "https://api.test", "year": 2025, "month": 9, "contract_id": 42}]
    assert [s["tenant_id"] for s in mesh.submissions] == sorted([PROJECT_A, PROJECT_B])
    assert all(s["date"] == "2025-09-01Z" for s in mesh.submissions)

    payload_a = next(s["payload"] for s in mesh.submissions if s["tenant_id"] == PROJECT_A)
    assert payload_a["kind"] == "meshResourceUsageReport"
    assert payload_a["source"] == "T Cloud"
    assert payload_a["fullPlatformIdentifier"] == "tcloud.test"
    assert [item["usageType"] for item in payload_a["lineItems"]] == ["OTC_KMS_UD_C (EL)", "OTC_KMS_UD_C (RC)"]

    assert stats == {"fetched_records": 7, "projects": 2, "submitted": 2, "failed": 0, "fetch_failed": 0}


def test_process_month_one_failure_does_not_abort_others(tcloud_main, monkeypatch, sample_records, fake_mesh_client_factory):
    _patch_fetch(monkeypatch, tcloud_main, sample_records)
    mesh = fake_mesh_client_factory(failing_projects=[PROJECT_A])
    config = tcloud_main.TCloudConfig(api_token="t")

    stats = tcloud_main.process_month(mesh, object(), config, "tcloud.test", "2025-09")

    assert len(mesh.submissions) == 2
    assert stats["submitted"] == 1
    assert stats["failed"] == 1


def test_process_month_fetch_error_skips_submission(tcloud_main, monkeypatch, fake_mesh_client_factory, caplog):
    def failing_fetch(*args, **kwargs):
        raise TCloudApiError("HTTP 422", status_code=422, body_excerpt='{"detail": "bad month"}')

    monkeypatch.setattr(tcloud_main, "fetch_daily_consumption", failing_fetch)
    mesh = fake_mesh_client_factory()
    config = tcloud_main.TCloudConfig(api_token="t")

    with caplog.at_level(logging.ERROR):
        stats = tcloud_main.process_month(mesh, object(), config, "tcloud.test", "2025-09")

    assert mesh.submissions == []
    assert stats["fetch_failed"] == 1
    assert stats["submitted"] == 0
    assert "422" in caplog.text and "bad month" in caplog.text


def test_process_month_auth_error_logs_hint(tcloud_main, monkeypatch, fake_mesh_client_factory, caplog):
    def failing_fetch(*args, **kwargs):
        raise TCloudApiError("HTTP 401", status_code=401, body_excerpt="unauthorized")

    monkeypatch.setattr(tcloud_main, "fetch_daily_consumption", failing_fetch)
    config = tcloud_main.TCloudConfig(api_token="t")

    with caplog.at_level(logging.ERROR):
        tcloud_main.process_month(fake_mesh_client_factory(), object(), config, "tcloud.test", "2025-09")

    assert "90 days" in caplog.text


def test_process_month_truncated_stream_submits_nothing(tcloud_main, monkeypatch, sample_records, fake_mesh_client_factory):
    def truncated_fetch(*args, **kwargs):
        yield sample_records[0]
        raise TCloudApiError("stream broken")

    monkeypatch.setattr(tcloud_main, "fetch_daily_consumption", truncated_fetch)
    mesh = fake_mesh_client_factory()
    config = tcloud_main.TCloudConfig(api_token="t")

    stats = tcloud_main.process_month(mesh, object(), config, "tcloud.test", "2025-09")

    assert mesh.submissions == []
    assert stats["fetch_failed"] == 1


def test_process_month_dry_run_makes_no_calls(tcloud_main, monkeypatch, sample_records, fake_mesh_client_factory, caplog):
    _patch_fetch(monkeypatch, tcloud_main, sample_records)
    mesh = fake_mesh_client_factory()
    config = tcloud_main.TCloudConfig(api_token="t", dry_run=True)

    with caplog.at_level(logging.INFO):
        stats = tcloud_main.process_month(mesh, object(), config, "tcloud.test", "2025-09")

    assert mesh.submissions == []
    assert stats["submitted"] == 2
    assert "[DRY RUN]" in caplog.text


# --- main --------------------------------------------------------------------

def _patch_main_collaborators(tcloud_main, monkeypatch, mesh_client, records=None, fetch_error=None):
    monkeypatch.setattr(tcloud_main, "MeshStackClient", lambda *args, **kwargs: mesh_client)
    monkeypatch.setattr(tcloud_main, "setup_logging", lambda **kwargs: None)
    monkeypatch.setattr(tcloud_main, "should_process_last_month", lambda: False)

    session = FakeSession(FakeResponse([]))
    monkeypatch.setattr(tcloud_main, "build_session", lambda token: session)

    def fake_fetch(*args, **kwargs):
        if fetch_error is not None:
            raise fetch_error
        return iter(records or [])

    monkeypatch.setattr(tcloud_main, "fetch_daily_consumption", fake_fetch)
    return session


def test_main_returns_0_and_closes_session(tcloud_main, monkeypatch, sample_records, fake_mesh_client_factory):
    set_env(monkeypatch, TCLOUD_API_TOKEN="abc", USAGE_PERIOD="2025-09")
    mesh = fake_mesh_client_factory()
    session = _patch_main_collaborators(tcloud_main, monkeypatch, mesh, records=sample_records)

    assert tcloud_main.main() == 0
    assert len(mesh.submissions) == 2
    assert session.closed is True


def test_main_returns_1_when_fetch_fails(tcloud_main, monkeypatch, fake_mesh_client_factory):
    set_env(monkeypatch, TCLOUD_API_TOKEN="abc", USAGE_PERIOD="2025-09")
    mesh = fake_mesh_client_factory()
    _patch_main_collaborators(tcloud_main, monkeypatch, mesh, fetch_error=TCloudApiError("boom", status_code=500))

    assert tcloud_main.main() == 1
    assert mesh.submissions == []


def test_main_returns_0_when_only_submissions_fail(tcloud_main, monkeypatch, sample_records, fake_mesh_client_factory):
    set_env(monkeypatch, TCLOUD_API_TOKEN="abc", USAGE_PERIOD="2025-09")
    mesh = fake_mesh_client_factory(failing_projects=[PROJECT_A, PROJECT_B])
    _patch_main_collaborators(tcloud_main, monkeypatch, mesh, records=sample_records)

    assert tcloud_main.main() == 0


def test_main_iterates_contracts(tcloud_main, monkeypatch, sample_records, fake_mesh_client_factory):
    set_env(monkeypatch, TCLOUD_API_TOKEN="abc", USAGE_PERIOD="2025-09", TCLOUD_CONTRACT_IDS="1,2")
    mesh = fake_mesh_client_factory()
    _patch_main_collaborators(tcloud_main, monkeypatch, mesh, records=sample_records)

    seen_contracts = []
    original = tcloud_main.process_month

    def spy(mesh_client, session, config, platform_id, month, contract_id=None):
        seen_contracts.append(contract_id)
        return original(mesh_client, session, config, platform_id, month, contract_id)

    monkeypatch.setattr(tcloud_main, "process_month", spy)

    assert tcloud_main.main() == 0
    assert seen_contracts == [1, 2]


def test_main_fails_fast_without_token_before_meshstack(tcloud_main, monkeypatch):
    set_env(monkeypatch)
    monkeypatch.setattr(tcloud_main, "setup_logging", lambda **kwargs: None)

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("MeshStackClient must not be constructed when config is invalid")

    monkeypatch.setattr(tcloud_main, "MeshStackClient", must_not_be_called)

    with pytest.raises(ValueError, match="TCLOUD_API_TOKEN"):
        tcloud_main.main()
