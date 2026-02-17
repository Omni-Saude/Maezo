"""Shared fixtures for contract_extraction tests."""
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from healthcare_platform.contract_extraction.models import Base
from healthcare_platform.contract_extraction.services.contract_service import ContractService
from healthcare_platform.contract_extraction.tenant_file_manager import TenantFileManager
from healthcare_platform.contract_extraction.dmn_generator import DMNGenerator


FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_TENANT_IDS = ["hospital-a", "amh-sp", "amh-rj", "amh-mg"]
VALID_PAYER_IDS = ["ses-df", "unimed-rj", "sulamerica-sp"]


def _dedup_indexes(metadata) -> None:
    """Remove duplicate index names caused by both index=True and __table_args__."""
    for table in metadata.tables.values():
        seen, to_remove = set(), []
        for idx in list(table.indexes):
            (to_remove if idx.name in seen else seen.add(idx.name) or []).append(idx)  # noqa
        for idx in to_remove:
            table.indexes.discard(idx)


@pytest.fixture(scope="module")
def engine():
    _dedup_indexes(Base.metadata)
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.rollback()
    sess.close()


@pytest.fixture
def dmn_mock():
    mock = MagicMock()
    mock.generate.return_value = "<xml/>"
    mock.generate_and_save.return_value = Path("test.dmn")
    return mock


@pytest.fixture
def service(session, dmn_mock):
    return ContractService(session, dmn_generator=dmn_mock)


# ---------------------------------------------------------------------------
# Mock rule factory & sample fixtures (Phase 4a)
# ---------------------------------------------------------------------------

def _make_mock_rule(archetype: str, category: str, rule_definition: dict, **overrides):
    """Create a mock ContractRule-like object."""
    rule = MagicMock()
    rule.id = overrides.get("id", str(uuid.uuid4()))
    rule.payer_id = overrides.get("payer_id", "ses-df")
    rule.tenant_id = overrides.get("tenant_id", "hospital-a")

    arch_mock = MagicMock()
    arch_mock.value = archetype
    rule.archetype = arch_mock

    cat_mock = MagicMock()
    cat_mock.value = category
    rule.category = cat_mock

    rule.rule_definition = rule_definition
    rule.version = overrides.get("version", "1.0.0")
    return rule


@pytest.fixture
def mock_rule():
    """Factory fixture for creating mock ContractRule objects."""
    return _make_mock_rule


@pytest.fixture
def mock_tenant_id():
    """Returns a valid tenant ID."""
    return VALID_TENANT_IDS[0]


@pytest.fixture
def mock_payer_id():
    """Returns a valid payer ID."""
    return VALID_PAYER_IDS[0]


@pytest.fixture
def tmp_file_manager(tmp_path):
    """TenantFileManager backed by tmp_path."""
    return TenantFileManager(base_path=tmp_path)


@pytest.fixture
def tmp_generator(tmp_path):
    """DMNGenerator with a tmp-backed TenantFileManager."""
    fm = TenantFileManager(base_path=tmp_path)
    return DMNGenerator(file_manager=fm)


@pytest.fixture
def sample_pricing_rule():
    """A realistic pricing rule for TUSS code 03.05.01.004-2."""
    return _make_mock_rule("PRICING", "PRICING", {
        "procedure_code": {"operator": "eq", "value": "03.05.01.004-2"},
        "payer_id": {"operator": "eq", "value": "SES-DF"},
        "quantity": {"operator": "gte", "value": 1},
        "output_unit_price": 450.00,
        "output_total_price": 450.00,
        "output_currency": "BRL",
    })


@pytest.fixture
def sample_bundle_rule():
    """A realistic bundling rule for mastectomy + lymphadenectomy."""
    return _make_mock_rule("BUNDLING", "BUNDLE", {
        "primary_code": {"operator": "eq", "value": "04.09.01.059-2"},
        "secondary_code": {"operator": "eq", "value": "04.09.01.060-6"},
        "same_act": {"operator": "eq", "value": True},
        "output_is_bundled": True,
        "output_bundle_price": 3200.00,
        "output_bundle_code": "BUNDLE-MAST-001",
    })


@pytest.fixture
def sample_auth_rule():
    """A realistic authorization rule for high-value procedures."""
    return _make_mock_rule("AUTHORIZATION", "AUTHORIZATION", {
        "procedure_code": {"operator": "eq", "value": "04.09.01.059-2"},
        "amount": {"operator": "gte", "value": 5000},
        "payer_id": {"operator": "eq", "value": "SES-DF"},
        "output_requires_auth": True,
        "output_auth_type": "SUPERVISOR_REQUIRED",
        "output_urgency_level": "HIGH",
    })


@pytest.fixture
def load_fixture():
    """Load a JSON fixture file from tests/fixtures/."""
    def _load(filename: str):
        with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return _load
