import importlib.util
from typing import Any, Dict, List

import pytest

from helpers import PLATFORM_DIR, PROJECT_B, FakeMeshClient, daily_record


@pytest.fixture
def sample_records() -> List[Dict[str, Any]]:
    return [
        # same product, three days, EL, project A
        daily_record(consumption_date="2025-09-01T00:00:00+02:00", quantity=24.0, amount=0.1),
        daily_record(consumption_date="2025-09-02T00:00:00+02:00", quantity=24.0, amount=0.1, status="AGGREGATION_PROCESSED"),
        daily_record(consumption_date="2025-09-03T00:00:00+02:00", quantity=12.0, amount=0.05),
        # same product but recurring, project A
        daily_record(consumption_type="RC", quantity=720.0, amount=10.0),
        # another region for the same product, project A (merged into the EL group)
        daily_record(region="EU-NL", quantity=6.0, amount=0.025),
        # project B
        daily_record(project_id=PROJECT_B, product="OTC_ECS_S3", product_description="ECS s3.large", quantity=100.0, amount=5.0),
        # no project id
        daily_record(project_id=None, quantity=1.0, amount=1.0),
    ]


@pytest.fixture
def tcloud_main():
    """Load platforms/tcloud/main.py under a unique module name."""
    spec = importlib.util.spec_from_file_location("tcloud_main", PLATFORM_DIR / "main.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_mesh_client_factory():
    return FakeMeshClient
