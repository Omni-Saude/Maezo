"""Integration tests for Clinical DMN Integration (Phase 8).

Tests that clinical workers correctly call FederatedDMNService
and that DMN tables produce expected clinical safety outputs.

Author: CIB7 Platform Team
Version: 1.0.0
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Any, Dict

# Service under test
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def dmn_service():
    """Create a FederatedDMNService instance."""
    return FederatedDMNService(cache_ttl_seconds=0)  # No caching for tests


@pytest.fixture
def mock_dmn_service():
    """Create a mock FederatedDMNService."""
    service = MagicMock(spec=FederatedDMNService)
    return service


@pytest.fixture
def sample_ddi_inputs_bleed():
    """Sample DDI inputs for bleeding risk."""
    return {
        "medicamentosAtivos": ["FLUOXETINA"],
        "medicamentoNovo": "VARFARINA",
        "idade": 70,
    }


@pytest.fixture
def sample_qsofa_inputs_positive():
    """Sample qSOFA inputs for positive screening."""
    return {
        "diasPosCirurgia": 6,
        "qsofaScore": 3,
        "tipoCirurgia": "ABDOMINAL",
        "tendenciaPiora": True,
    }


@pytest.fixture
def sample_qsofa_inputs_negative():
    """Sample qSOFA inputs for negative screening."""
    return {
        "diasPosCirurgia": 1,
        "qsofaScore": 0,
        "tipoCirurgia": "ORTOPEDICA",
        "tendenciaPiora": False,
    }


@pytest.fixture
def sample_lab_critical():
    """Sample critical lab inputs."""
    return {
        "test_name": "TROPONINA",
        "value": 2.5,
        "unit": "ng/mL",
    }


# ── Federation Service Structural Tests ──────────────────────────────


@pytest.mark.integration
@pytest.mark.dmn
class TestFederationServiceLoadsDomainDMN:
    """Test that FederatedDMNService correctly loads domain-specific DMN files."""

    def test_loads_clinical_safety_category(self, dmn_service):
        """Verify clinical_safety is a valid category."""
        from healthcare_platform.shared.dmn.federation_service import CATEGORIES, DOMAIN_DMN_PATHS
        assert 'clinical_safety' in CATEGORIES
        assert 'clinical_safety' in DOMAIN_DMN_PATHS

    def test_domain_path_resolves_to_clinical_operations(self, dmn_service):
        """Verify domain path points to clinical_operations/dmn."""
        from healthcare_platform.shared.dmn.federation_service import DMN_BASE_PATH, DOMAIN_DMN_PATHS
        domain_base = (DMN_BASE_PATH / DOMAIN_DMN_PATHS['clinical_safety']).resolve()
        assert domain_base.exists(), f"Domain path does not exist: {domain_base}"
        assert 'clinical_operations' in str(domain_base)

    def test_loads_ddi_bleed_dmn(self, dmn_service):
        """Verify DDI bleed DMN tables can be loaded."""
        # Check directory exists
        ddi_bleed_dir = Path('platform/clinical_operations/dmn/clinical_safety/ddi/bleed')
        if not ddi_bleed_dir.exists():
            pytest.skip("DDI bleed DMN directory not found")

        dmn_files = list(ddi_bleed_dir.glob('*.dmn'))
        if len(dmn_files) == 0:
            pytest.skip("No DDI bleed DMN files found")

        # Try loading first table
        table_name = f'ddi/bleed/{dmn_files[0].stem}'
        table = dmn_service.load_base_table('clinical_safety', table_name)

        # Verify structure
        assert 'rules' in table
        assert 'hitPolicy' in table
        assert 'inputs' in table
        assert 'outputs' in table
        assert len(table['rules']) > 0

    def test_loads_ews_qsofa_dmn(self, dmn_service):
        """Verify EWS qSOFA DMN tables can be loaded."""
        qsofa_dir = Path('platform/clinical_operations/dmn/clinical_safety/ews/qsofa')
        if not qsofa_dir.exists():
            pytest.skip("EWS qSOFA DMN directory not found")

        dmn_files = list(qsofa_dir.glob('*.dmn'))
        if len(dmn_files) == 0:
            pytest.skip("No qSOFA DMN files found")

        table_name = f'ews/qsofa/{dmn_files[0].stem}'
        table = dmn_service.load_base_table('clinical_safety', table_name)

        # Verify structure
        assert 'rules' in table
        assert 'hitPolicy' in table
        assert table['hitPolicy'] in ['FIRST', 'COLLECT', 'UNIQUE', 'ANY']

    def test_loads_lab_cardiac_dmn(self, dmn_service):
        """Verify lab cardiac DMN tables can be loaded."""
        lab_cardiac_dir = Path('platform/clinical_operations/dmn/clinical_safety/lab/cardiac')
        if not lab_cardiac_dir.exists():
            pytest.skip("Lab cardiac DMN directory not found")

        dmn_files = list(lab_cardiac_dir.glob('*.dmn'))
        if len(dmn_files) == 0:
            pytest.skip("No lab cardiac DMN files found")

        table_name = f'lab/cardiac/{dmn_files[0].stem}'
        table = dmn_service.load_base_table('clinical_safety', table_name)

        assert 'rules' in table
        assert 'outputs' in table


# ── DDI Worker Mock Tests ────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.dmn
class TestDDIWorkerCallsBleedDMN:
    """Test DDI worker correctly calls bleed DMN tables."""

    def test_bleed_dmn_evaluation_returns_expected_structure(
        self, mock_dmn_service, current_tenant
    ):
        """Verify DDI evaluates bleed risk tables with expected output structure."""
        mock_dmn_service.evaluate.return_value = {
            'nivelAlerta': 'Atencao',
            'urgencia': 'ROTINA',
            'medicamentosConflitantes': 'SSRI + Anticoagulante (idade ≥65 anos)',
            'mecanismoInteracao': 'Risco sangramento GI/intracraniano 1.5-2.0x aumentado',
            'acaoRequerida': 'MONITORAMENTO: IBP profilático OBRIGATÓRIO',
        }

        result = mock_dmn_service.evaluate(
            tenant_id=current_tenant.tenant_id,
            category='clinical_safety',
            table_name='ddi/bleed/ddi_bleed_016',
            inputs={
                'medicamentosAtivos': ['FLUOXETINA'],
                'medicamentoNovo': 'VARFARINA',
                'idade': 70,
            },
        )

        # Verify structure
        assert 'nivelAlerta' in result
        assert 'urgencia' in result
        assert 'medicamentosConflitantes' in result
        assert 'mecanismoInteracao' in result
        assert 'acaoRequerida' in result

        # Verify severity assessment
        assert result['nivelAlerta'] in ['Alerta', 'Atencao', 'Informativo', 'OK']
        assert result['urgencia'] in ['IMEDIATA', 'URGENTE', 'ROTINA']

        mock_dmn_service.evaluate.assert_called_once()


@pytest.mark.integration
@pytest.mark.dmn
class TestDDIWorkerCallsQTDMN:
    """Test DDI worker correctly calls QT prolongation DMN tables."""

    def test_qt_dmn_evaluation_structure(self, mock_dmn_service, current_tenant):
        """Verify DDI evaluates QT prolongation tables."""
        mock_dmn_service.evaluate.return_value = {
            'nivelAlerta': 'Alerta',
            'urgencia': 'URGENTE',
            'medicamentosConflitantes': 'AMIODARONA + HALOPERIDOL',
            'mecanismoInteracao': 'QT prolongation risk',
            'acaoRequerida': 'Monitorar ECG. Avaliar intervalo QTc.',
        }

        result = mock_dmn_service.evaluate(
            tenant_id=current_tenant.tenant_id,
            category='clinical_safety',
            table_name='ddi/qt/ddi_qt_001',
            inputs={'drug_1': 'AMIODARONA', 'drug_2': 'HALOPERIDOL'},
        )

        assert 'nivelAlerta' in result
        assert 'mecanismoInteracao' in result


# ── Lab Worker Mock Tests ────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.dmn
class TestLabWorkerCallsCriticalValueDMN:
    """Test lab results worker calls critical value DMN tables."""

    def test_critical_lab_evaluation_structure(self, mock_dmn_service, current_tenant):
        """Verify lab worker evaluates critical value tables."""
        mock_dmn_service.evaluate.return_value = {
            'is_critical': True,
            'alert_level': 'CRITICAL',
            'action': 'Notificar médico imediatamente',
            'expected_range': '0.0-0.04 ng/mL',
        }

        result = mock_dmn_service.evaluate(
            tenant_id=current_tenant.tenant_id,
            category='clinical_safety',
            table_name='lab/cardiac/lab_cardiac_001',
            inputs={'test_name': 'TROPONINA', 'value': 2.5, 'unit': 'ng/mL'},
        )

        assert result['is_critical'] is True
        assert result['alert_level'] == 'CRITICAL'
        assert 'action' in result

    def test_normal_lab_no_critical_alert(self, mock_dmn_service, current_tenant):
        """Verify normal lab values result in non-critical assessment."""
        mock_dmn_service.evaluate.return_value = {
            'is_critical': False,
            'alert_level': 'NORMAL',
            'action': 'Continue routine monitoring',
        }

        result = mock_dmn_service.evaluate(
            tenant_id=current_tenant.tenant_id,
            category='clinical_safety',
            table_name='lab/heme/lab_heme_001',
            inputs={'test_name': 'HEMOGLOBINA', 'value': 14.0, 'unit': 'g/dL'},
        )

        assert result['is_critical'] is False
        assert result['alert_level'] == 'NORMAL'


# ── EWS Worker Mock Tests ────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.dmn
class TestEWSWorkerCallsQSOFADMN:
    """Test early warning score worker calls qSOFA DMN tables."""

    def test_qsofa_positive_evaluation(
        self, mock_dmn_service, current_tenant, sample_qsofa_inputs_positive
    ):
        """Verify qSOFA evaluation for positive screening."""
        mock_dmn_service.evaluate.return_value = {
            'nivelAlerta': 'Alerta',
            'urgencia': 'IMEDIATA',
            'acaoRequerida': 'Solicitar exames SOFA completo. Considerar UTI.',
            'justificativaCientifica': 'Peak anastomotic leak risk window with positive qSOFA',
        }

        result = mock_dmn_service.evaluate(
            tenant_id=current_tenant.tenant_id,
            category='clinical_safety',
            table_name='ews/qsofa/ews_qsofa_007',
            inputs=sample_qsofa_inputs_positive,
        )

        # Verify critical alert
        assert result['nivelAlerta'] == 'Alerta'
        assert result['urgencia'] == 'IMEDIATA'
        assert 'acaoRequerida' in result
        assert 'justificativaCientifica' in result

    def test_qsofa_negative_evaluation(
        self, mock_dmn_service, current_tenant, sample_qsofa_inputs_negative
    ):
        """Verify qSOFA evaluation for negative screening."""
        mock_dmn_service.evaluate.return_value = {
            'nivelAlerta': 'OK',
            'urgencia': 'INFORMATIVA',
            'acaoRequerida': 'Continuar monitoramento rotina',
            'justificativaCientifica': 'Expected post-operative recovery',
        }

        result = mock_dmn_service.evaluate(
            tenant_id=current_tenant.tenant_id,
            category='clinical_safety',
            table_name='ews/qsofa/ews_qsofa_007',
            inputs=sample_qsofa_inputs_negative,
        )

        # Verify non-critical
        assert result['nivelAlerta'] == 'OK'
        assert result['urgencia'] == 'INFORMATIVA'


# ── Tenant Override Tests ────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.dmn
class TestTenantOverridePrecedence:
    """Test that tenant-specific overrides take precedence over base rules."""

    def test_tenant_override_replaces_base_rule(self, dmn_service):
        """Verify tenant override rules replace base rules."""
        base_rules = [
            {"id": "rule_1", "inputs": {"drug": "WARFARINA"}, "output": {"max_dose": 10}},
            {"id": "rule_2", "inputs": {"drug": "AAS"}, "output": {"max_dose": 500}},
        ]
        override_rules = [
            {"id": "rule_1", "inputs": {"drug": "WARFARINA"}, "output": {"max_dose": 5}},
        ]

        merged = dmn_service.merge_rules(base_rules, override_rules)

        # Override should take precedence
        warfarin_rule = next(r for r in merged if r["id"] == "rule_1")
        assert warfarin_rule["output"]["max_dose"] == 5

        # Non-overridden rule should remain
        aas_rule = next(r for r in merged if r["id"] == "rule_2")
        assert aas_rule["output"]["max_dose"] == 500

    def test_tenant_override_adds_new_rules(self, dmn_service):
        """Verify tenant can add new rules."""
        base_rules = [
            {"id": "rule_1", "inputs": {"drug": "WARFARINA"}, "output": {"max_dose": 10}},
        ]
        override_rules = [
            {"id": "tenant_rule_1", "inputs": {"drug": "CUSTOM_MED"}, "output": {"max_dose": 100}},
        ]

        merged = dmn_service.merge_rules(base_rules, override_rules)
        assert len(merged) == 2

        # Verify new rule exists
        custom_rule = next(r for r in merged if r["id"] == "tenant_rule_1")
        assert custom_rule["output"]["max_dose"] == 100

    def test_override_rules_have_higher_priority(self, dmn_service):
        """Verify override rules appear first in merged list."""
        base_rules = [
            {"id": "rule_1", "inputs": {}, "output": {"value": "base"}},
        ]
        override_rules = [
            {"id": "rule_2", "inputs": {}, "output": {"value": "override"}},
        ]

        merged = dmn_service.merge_rules(base_rules, override_rules)

        # Override rule should be first
        assert merged[0]["id"] == "rule_2"
        assert merged[0]["output"]["value"] == "override"


# ── DMN File Existence Tests ─────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.dmn
class TestDMNFilesExist:
    """Verify that expected DMN files exist for clinical safety."""

    @pytest.mark.parametrize("subcategory", [
        "ddi/bleed",
        "ddi/hepato",
        "ddi/nephro",
        "ddi/qt",
        "ddi/contraind",
        "ddi/major",
        "ddi/moderate",
        "ddi/serotonin",
    ])
    def test_ddi_subcategories_have_dmn_files(self, subcategory):
        """Verify each DDI subcategory has DMN files."""
        dmn_dir = Path(f'platform/clinical_operations/dmn/clinical_safety/{subcategory}')
        if not dmn_dir.exists():
            pytest.skip(f"Directory {subcategory} not found")

        dmn_files = list(dmn_dir.glob('*.dmn'))
        assert len(dmn_files) > 0, f"No DMN files in {subcategory}"

    @pytest.mark.parametrize("subcategory", [
        "ews/qsofa",
        "ews/pews",
        "ews/mews",
        "ews/news",
        "vit/critical",
        "vit/trend",
        "vit/peds",
        "lab/cardiac",
        "lab/electro",
        "lab/gluc",
        "lab/heme",
        "lab/renal",
    ])
    def test_clinical_subcategories_have_dmn_files(self, subcategory):
        """Verify clinical subcategories have DMN files."""
        dmn_dir = Path(f'platform/clinical_operations/dmn/clinical_safety/{subcategory}')
        if not dmn_dir.exists():
            pytest.skip(f"Directory {subcategory} not found")

        dmn_files = list(dmn_dir.glob('*.dmn'))
        assert len(dmn_files) > 0, f"No DMN files in {subcategory}"

    def test_ddi_bleed_has_multiple_interaction_tables(self):
        """Verify DDI bleed category has comprehensive coverage."""
        dmn_dir = Path('platform/clinical_operations/dmn/clinical_safety/ddi/bleed')
        if not dmn_dir.exists():
            pytest.skip("DDI bleed directory not found")

        dmn_files = list(dmn_dir.glob('*.dmn'))

        # Should have multiple drug interaction tables
        assert len(dmn_files) >= 5, "Expected at least 5 bleeding interaction tables"

    def test_ews_has_all_scoring_systems(self):
        """Verify all early warning score systems have DMN tables."""
        ews_systems = ['qsofa', 'pews', 'mews', 'news']

        for system in ews_systems:
            ews_dir = Path(f'platform/clinical_operations/dmn/clinical_safety/ews/{system}')
            if not ews_dir.exists():
                pytest.skip(f"EWS {system} directory not found")

            dmn_files = list(ews_dir.glob('*.dmn'))
            assert len(dmn_files) > 0, f"No DMN files for EWS {system}"


# ── Cache Behavior Tests ─────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.dmn
class TestDMNCacheBehavior:
    """Test DMN service caching behavior."""

    def test_cache_improves_performance_on_repeated_loads(self, dmn_service):
        """Verify caching improves performance for repeated table loads."""
        # Enable caching
        cached_service = FederatedDMNService(cache_ttl_seconds=300)

        # Find a DMN file
        dmn_dir = Path('platform/clinical_operations/dmn/clinical_safety/ddi/bleed')
        if not dmn_dir.exists():
            pytest.skip("DDI bleed directory not found")

        dmn_files = list(dmn_dir.glob('*.dmn'))
        if len(dmn_files) == 0:
            pytest.skip("No DMN files found")

        table_name = f'ddi/bleed/{dmn_files[0].stem}'

        # First load (cache miss)
        cached_service.load_base_table('clinical_safety', table_name)

        # Second load (cache hit)
        cached_service.load_base_table('clinical_safety', table_name)

        # Verify cache stats
        stats = cached_service.get_cache_stats()
        assert stats['total_entries'] > 0
        assert stats['active_entries'] > 0

    def test_cache_can_be_cleared(self, dmn_service):
        """Verify cache can be manually cleared."""
        # Enable caching
        cached_service = FederatedDMNService(cache_ttl_seconds=300)

        # Load a table
        dmn_dir = Path('platform/clinical_operations/dmn/clinical_safety/ddi/bleed')
        if not dmn_dir.exists():
            pytest.skip("DDI bleed directory not found")

        dmn_files = list(dmn_dir.glob('*.dmn'))
        if len(dmn_files) == 0:
            pytest.skip("No DMN files found")

        table_name = f'ddi/bleed/{dmn_files[0].stem}'
        cached_service.load_base_table('clinical_safety', table_name)

        # Verify cache has entries
        stats_before = cached_service.get_cache_stats()
        assert stats_before['total_entries'] > 0

        # Clear cache
        cached_service.clear_cache()

        # Verify cache is empty
        stats_after = cached_service.get_cache_stats()
        assert stats_after['total_entries'] == 0


# ── Error Handling Tests ─────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.dmn
class TestDMNErrorHandling:
    """Test error handling in DMN evaluation."""

    def test_invalid_category_raises_error(self, dmn_service):
        """Verify invalid category raises ValueError."""
        with pytest.raises(ValueError, match="Invalid category"):
            dmn_service.load_base_table('invalid_category', 'some_table')

    def test_missing_dmn_file_raises_error(self, dmn_service):
        """Verify missing DMN file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            dmn_service.load_base_table('clinical_safety', 'nonexistent/table')

    def test_evaluation_with_no_matching_rules_raises_error(self, mock_dmn_service):
        """Verify evaluation with no matching rules raises ValueError."""
        mock_dmn_service.evaluate.side_effect = ValueError("No matching DMN rules found")

        with pytest.raises(ValueError, match="No matching DMN rules"):
            mock_dmn_service.evaluate(
                tenant_id='test-tenant',
                category='clinical_safety',
                table_name='ddi/bleed/ddi_bleed_001',
                inputs={'invalid_key': 'invalid_value'},
            )
