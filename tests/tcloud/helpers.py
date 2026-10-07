import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PLATFORM_DIR = REPO_ROOT / "platforms" / "tcloud"
CORE_DIR = REPO_ROOT / "src" / "core"

for path in (PLATFORM_DIR, CORE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class FakeResponse:
    """Minimal stand-in for requests.Response supporting the streaming API we use."""

    def __init__(
        self,
        lines: Optional[List[str]] = None,
        status_code: int = 200,
        text: str = "",
        raise_after: Optional[int] = None,
    ):
        self.lines = lines or []
        self.status_code = status_code
        self.text = text
        self.raise_after = raise_after
        self.closed = False

    def iter_lines(self, chunk_size: int = 512, decode_unicode: bool = False) -> Iterator[str]:
        for index, line in enumerate(self.lines):
            if self.raise_after is not None and index >= self.raise_after:
                raise requests.exceptions.ChunkedEncodingError("connection broken mid-stream")
            yield line

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class FakeSession:
    """Records the last GET call and returns a preconfigured FakeResponse."""

    def __init__(self, response: FakeResponse):
        self.response = response
        self.last_url: Optional[str] = None
        self.last_params: Optional[Dict[str, Any]] = None
        self.last_kwargs: Dict[str, Any] = {}
        self.closed = False

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> FakeResponse:
        self.last_url = url
        self.last_params = params
        self.last_kwargs = kwargs
        return self.response

    def close(self) -> None:
        self.closed = True


def daily_record(**overrides: Any) -> Dict[str, Any]:
    record = {
        "aggregation_id": "6695b30b94bcea55c2d7703b",
        "amount": 0.1,
        "consumption_date": "2025-09-01T00:00:00+02:00",
        "consumption_type": "EL",
        "contract": 1000012345,
        "product": "OTC_KMS_UD_C",
        "product_description": "KMS Customer Masterkey",
        "project_id": "845f7226c0d8450793ab07ab1ca80d70",
        "quantity": 24.0,
        "quantity_type": "h",
        "region": "EU-DE",
        "resource_id": "3eaf12bc-9f70-4e33-849b-fe9cd0de3d36",
        "status": "NEW",
    }
    record.update(overrides)
    return record


PROJECT_A = "845f7226c0d8450793ab07ab1ca80d70"
PROJECT_B = "0123456789abcdef0123456789abcdef"


class FakeMeshClient:
    """Records submitted usage reports; fails for configured project ids."""

    def __init__(self, failing_projects: Optional[List[str]] = None):
        self.failing_projects = set(failing_projects or [])
        self.submissions: List[Dict[str, Any]] = []

    def submit_usage_report(self, platform_tenant_id: str, date: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.submissions.append({"tenant_id": platform_tenant_id, "date": date, "payload": payload})
        if platform_tenant_id in self.failing_projects:
            return {"status": "failure", "message": "HTTP error: 404 tenant not found"}
        return {"status": "success", "result": ""}
