"""
Comprehensive tests for all 13 surgical workers.
Tests success (PROSSEGUIR), block (BLOQUEAR), and review (REVISAR) scenarios.
"""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus

# Import all surgical workers
from healthcare_platform.clinical_operations.workers.surgical.surgery_scheduling_worker import SurgerySchedulingWorker
from healthcare_platform.clinical_operations.workers.surgical.surgical_team_assignment_worker import SurgicalTeamAssignmentWorker
from healthcare_platform.clinical_operations.workers.surgical.surgical_checklist_worker import SurgicalChecklistWorker
from healthcare_platform.clinical_operations.workers.surgical.or_turnover_worker import ORTurnoverWorker
from healthcare_platform.clinical_operations.workers.surgical.surgical_equipment_worker import SurgicalEquipmentWorker
from healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker import SurgicalCountVerificationWorker
from healthcare_platform.clinical_operations.workers.surgical.surgical_specimen_worker import SurgicalSpecimenWorker
from healthcare_platform.clinical_operations.workers.surgical.post_op_recovery_worker import PostOpRecoveryWorker


@pytest.fixture
def mock_dmn_service():
    """Mock DMN service that returns configurable results."""
    service = MagicMock()
    service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "Aprovado", "risco": "BAIXO"}
    return service


@pytest.fixture
def context():
    """Standard test context."""
    return TaskContext(
        task_id="test-task-1",
        process_instance_id="proc-123",
        tenant_id="HOSPITAL_A",
        variables={},
        worker_id="surgical.test",
    )


# ============================================================================
# 1. SurgerySchedulingWorker Tests
# ============================================================================
class TestSurgerySchedulingWorker:
    def test_success_case(self, mock_dmn_service, context):
        worker = SurgerySchedulingWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "procedureCode": "PROC123",
            "surgeonId": "SURG001",
            "requestedDate": "2026-03-01",
            "urgencyLevel": "ELETIVO",
            "estimatedDuration": 120,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Agendamento aprovado",
            "salaSugerida": "SALA-01",
            "horarioSugerido": "08:00",
            "priorityScore": 70,
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"
        assert result.variables["correlation_id"] == "proc-123"
        assert result.variables["salaSugerida"] == "SALA-01"

    def test_block_case(self, mock_dmn_service, context):
        worker = SurgerySchedulingWorker(dmn_service=mock_dmn_service)
        context.variables = {"urgencyLevel": "URGENTE"}
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Sem sala disponível",
            "priorityScore": 90,
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "SURG_SCHEDULING_BLOCKED"
        assert result.variables["correlation_id"] == "proc-123"

    def test_review_case(self, mock_dmn_service, context):
        worker = SurgerySchedulingWorker(dmn_service=mock_dmn_service)
        context.variables = {"urgencyLevel": "ELETIVO"}
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR",
            "acao": "Revisar manualmente",
            "priorityScore": 50,
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["requiresReview"] is True


# ============================================================================
# 2. SurgicalTeamAssignmentWorker Tests
# ============================================================================
class TestSurgicalTeamAssignmentWorker:
    def test_success_case(self, mock_dmn_service, context):
        worker = SurgicalTeamAssignmentWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "surgeonId": "SURG001",
            "anesthesiologistRequired": True,
            "nursingStaffRequired": 2,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Equipe alocada",
            "risco": "BAIXO",
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["correlation_id"] == "proc-123"

    def test_block_case(self, mock_dmn_service, context):
        worker = SurgicalTeamAssignmentWorker(dmn_service=mock_dmn_service)
        context.variables = {"surgeonId": "SURG999"}
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Cirurgião não disponível",
            "risco": "ALTO",
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "SURG_TEAM_UNAVAILABLE"


# ============================================================================
# 8. SurgicalChecklistWorker Tests
# ============================================================================
class TestSurgicalChecklistWorker:
    def test_success_case(self, mock_dmn_service, context):
        worker = SurgicalChecklistWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "teamMembersConfirmed": True,
            "patientIdentityReconfirmed": True,
            "procedureConfirmed": True,
            "siteConfirmed": True,
            "antibioticGiven": True,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Checklist completo",
            "risco": "BAIXO",
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["correlation_id"] == "proc-123"

    def test_block_case(self, mock_dmn_service, context):
        worker = SurgicalChecklistWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "teamMembersConfirmed": False,
            "patientIdentityReconfirmed": False,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Checklist incompleto",
            "risco": "ALTO",
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "SURG_SAFETY"


# ============================================================================
# 9. ORTurnoverWorker Tests
# ============================================================================
class TestORTurnoverWorker:
    def test_success_case(self, mock_dmn_service, context):
        worker = ORTurnoverWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "previousCaseComplexity": "MEDIO",
            "cleaningLevel": "STANDARD",
            "nextCaseSetupNeeds": "STANDARD",
            "turnaroundTimeMinutes": 30,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Tempo adequado",
            "risco": "BAIXO",
            "expectedTime": 30,
            "suggestions": [],
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["expectedTime"] == 30
        assert result.variables["correlation_id"] == "proc-123"

    def test_block_case(self, mock_dmn_service, context):
        worker = ORTurnoverWorker(dmn_service=mock_dmn_service)
        context.variables = {"turnaroundTimeMinutes": 10}
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Tempo insuficiente",
            "risco": "ALTO",
            "expectedTime": 45,
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "SURG_OR_TURNOVER"


# ============================================================================
# 10. SurgicalEquipmentWorker Tests
# ============================================================================
class TestSurgicalEquipmentWorker:
    def test_success_case(self, mock_dmn_service, context):
        worker = SurgicalEquipmentWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "procedureType": "LAPAROSCOPY",
            "equipmentList": ["CAM001", "LIGHT001"],
            "sterilizationStatus": "COMPLETE",
            "calibrationCurrent": True,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Equipamento pronto",
            "risco": "BAIXO",
            "missingEquipment": [],
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["correlation_id"] == "proc-123"

    def test_block_case(self, mock_dmn_service, context):
        worker = SurgicalEquipmentWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "sterilizationStatus": "PENDING",
            "calibrationCurrent": False,
        }
        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "BLOQUEAR",
                "acao": "Esterilização pendente",
                "risco": "ALTO",
                "missingEquipment": ["STERI001"],
            },
            {"risco": "BAIXO"},
        ]

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "SURG_EQUIPMENT"


# ============================================================================
# 11. SurgicalCountVerificationWorker Tests
# ============================================================================
class TestSurgicalCountVerificationWorker:
    def test_success_case(self, mock_dmn_service, context):
        worker = SurgicalCountVerificationWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "instrumentCountPre": 20,
            "instrumentCountPost": 20,
            "spongeCountPre": 10,
            "spongeCountPost": 10,
            "needleCountMatch": True,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Contagem correta",
            "risco": "BAIXO",
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["countMatches"] is True
        assert result.variables["correlation_id"] == "proc-123"

    def test_block_case_instrument_mismatch(self, mock_dmn_service, context):
        worker = SurgicalCountVerificationWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "instrumentCountPre": 20,
            "instrumentCountPost": 19,
            "spongeCountPre": 10,
            "spongeCountPost": 10,
            "needleCountMatch": True,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR",
            "acao": "",
            "risco": "MEDIO",
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "SURG_COUNT_MISMATCH"
        assert result.variables["instrumentDiff"] == -1


# ============================================================================
# 12. SurgicalSpecimenWorker Tests
# ============================================================================
class TestSurgicalSpecimenWorker:
    def test_success_case(self, mock_dmn_service, context):
        worker = SurgicalSpecimenWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "specimenType": "BIOPSY",
            "labelingComplete": True,
            "chainOfCustody": True,
            "pathologyOrderPlaced": True,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Espécime rastreado",
            "risco": "BAIXO",
            "trackingId": "SPEC-001",
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["trackingId"] == "SPEC-001"
        assert result.variables["correlation_id"] == "proc-123"

    def test_block_case(self, mock_dmn_service, context):
        worker = SurgicalSpecimenWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "labelingComplete": False,
            "chainOfCustody": False,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Rotulagem incompleta",
            "risco": "ALTO",
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "SURG_SPECIMEN"


# ============================================================================
# 13. PostOpRecoveryWorker Tests
# ============================================================================
class TestPostOpRecoveryWorker:
    def test_success_case(self, mock_dmn_service, context):
        worker = PostOpRecoveryWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "aldereteScore": 10,
            "painControlled": True,
            "nauseaControlled": True,
            "bleedingControlled": True,
            "consciousnessLevel": "ALERTA",
            "handoffType": "PACU",
            "vitalSignsStable": True,
        }
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Alta SRPA aprovada",
            "risco": "BAIXO",
        }

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["aldereteScore"] == 10
        assert result.variables["correlation_id"] == "proc-123"

    def test_block_case_low_alderete(self, mock_dmn_service, context):
        worker = PostOpRecoveryWorker(dmn_service=mock_dmn_service)
        context.variables = {
            "aldereteScore": 5,
            "painControlled": False,
            "vitalSignsStable": False,
        }
        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "BLOQUEAR",
                "acao": "Alderete insuficiente",
                "risco": "ALTO",
            },
            {"resultado": "PROSSEGUIR"},
            {"resultado": "REVISAR"},
        ]

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "SURG_RECOVERY"
