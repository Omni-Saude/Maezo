"""
Worker para integração com sistemas de laboratório (LIS).

Recebe resultados de exames laboratoriais via HL7/FHIR, mapeia para formato
interno, valida faixas de referência, e identifica resultados críticos.

Padrões:
- Protocolo ABC + Stub implementation
- Modelos Pydantic com i18n
- Decoradores @require_tenant e @track_task_execution
- Conformidade LGPD com hash de identificadores
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Métricas Prometheus
lab_integrations_total = Counter(
    "lab_integrations_total",
    "Total de integrações laboratoriais processadas",
    ["tenant_id", "test_type", "status"],
)

lab_duration_seconds = Histogram(
    "lab_integration_duration_seconds",
    "Duração das integrações laboratoriais",
    ["tenant_id", "test_type"],
)

lab_critical_results_total = Counter(
    "lab_critical_results_total",
    "Total de resultados críticos detectados",
    ["tenant_id", "test_type"],
)


class LaboratoryIntegrationException(DomainException):
    """Exceção lançada quando ocorrem erros na integração laboratorial."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="LAB_INTEGRATION_ERROR",
            bpmn_error_code="LabIntegrationError",
            details=details or {},
        )


# ============================================================================
# Modelos Pydantic
# ============================================================================


class IntegrateLaboratoryInput(BaseModel):
    """Input para integração laboratorial."""

    patient_id: str = Field(..., description=_("ID do paciente"))
    order_id: str = Field(..., description=_("ID do pedido de exame"))
    test_type: Literal["hematology", "biochemistry", "microbiology", "pathology"] = (
        Field(..., description=_("Tipo de exame laboratorial"))
    )
    hl7_message: str | None = Field(
        None, description=_("Mensagem HL7 bruta se disponível")
    )
    fhir_observation: dict[str, Any] | None = Field(
        None, description=_("Recurso FHIR Observation se disponível")
    )
    lab_system_code: str = Field(..., description=_("Código do sistema LIS de origem"))
    collected_at: datetime = Field(..., description=_("Data/hora da coleta"))
    resulted_at: datetime = Field(..., description=_("Data/hora da liberação"))
    validate_ranges: bool = Field(
        True, description=_("Validar contra faixas de referência")
    )


class LabResult(BaseModel):
    """Resultado de exame laboratorial."""

    test_code: str = Field(..., description=_("Código do exame"))
    test_name: str = Field(..., description=_("Nome do exame"))
    value: str = Field(..., description=_("Valor do resultado"))
    unit: str = Field(..., description=_("Unidade de medida"))
    reference_range: str | None = Field(
        None, description=_("Faixa de referência")
    )
    is_critical: bool = Field(False, description=_("Resultado crítico"))
    is_abnormal: bool = Field(False, description=_("Resultado anormal"))
    notes: str | None = Field(None, description=_("Observações do laboratório"))


class IntegrateLaboratoryOutput(BaseModel):
    """Output da integração laboratorial."""

    integration_id: str = Field(..., description=_("ID único da integração"))
    patient_id: str = Field(..., description=_("ID do paciente"))
    order_id: str = Field(..., description=_("ID do pedido"))
    test_type: str = Field(..., description=_("Tipo de exame"))
    results: list[LabResult] = Field(..., description=_("Resultados dos exames"))
    critical_results_count: int = Field(
        0, description=_("Quantidade de resultados críticos")
    )
    abnormal_results_count: int = Field(
        0, description=_("Quantidade de resultados anormais")
    )
    validation_status: Literal["validated", "warnings", "failed"] = Field(
        ..., description=_("Status da validação")
    )
    validation_messages: list[str] = Field(
        default_factory=list, description=_("Mensagens de validação")
    )
    fhir_resource_id: str | None = Field(
        None, description=_("ID do recurso FHIR criado")
    )
    integrated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp da integração"),
    )
    duration_ms: int = Field(..., description=_("Duração em milissegundos"))


# ============================================================================
# Protocol e Implementação
# ============================================================================


class IntegrateLaboratoryProtocol(ABC):
    """Protocolo para integração laboratorial."""

    @abstractmethod
    async def parse_hl7_message(self, hl7_message: str) -> dict[str, Any]:
        """
        Parseia mensagem HL7 de resultados laboratoriais.

        Args:
            hl7_message: Mensagem HL7 bruta

        Returns:
            Dados estruturados extraídos
        """
        pass

    @abstractmethod
    async def parse_fhir_observation(
        self, fhir_observation: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Parseia recurso FHIR Observation.

        Args:
            fhir_observation: Recurso FHIR Observation

        Returns:
            Dados estruturados extraídos
        """
        pass

    @abstractmethod
    async def validate_reference_ranges(
        self, results: list[LabResult]
    ) -> list[str]:
        """
        Valida resultados contra faixas de referência.

        Args:
            results: Lista de resultados laboratoriais

        Returns:
            Lista de mensagens de validação
        """
        pass

    @abstractmethod
    async def identify_critical_results(
        self, results: list[LabResult]
    ) -> list[LabResult]:
        """
        Identifica resultados críticos que requerem notificação imediata.

        Args:
            results: Lista de resultados laboratoriais

        Returns:
            Lista de resultados críticos
        """
        pass


class IntegrateLaboratoryStub(IntegrateLaboratoryProtocol):
    """Implementação stub para integração laboratorial."""

    def __init__(self, fhir_client: FHIRClientProtocol):
        self.fhir_client = fhir_client
        self._dmn = get_dmn_service()

    async def parse_hl7_message(self, hl7_message: str) -> dict[str, Any]:
        """Parseia mensagem HL7."""
        # Simulação de parsing HL7
        return {
            "results": [
                {
                    "test_code": "HB",
                    "test_name": "Hemoglobina",
                    "value": "12.5",
                    "unit": "g/dL",
                    "reference_range": "12.0-16.0",
                    "is_critical": False,
                    "is_abnormal": False,
                },
                {
                    "test_code": "GLU",
                    "test_name": "Glicemia",
                    "value": "450",
                    "unit": "mg/dL",
                    "reference_range": "70-100",
                    "is_critical": True,
                    "is_abnormal": True,
                    "notes": "Valor crítico - hiperglicemia severa",
                },
            ]
        }

    async def parse_fhir_observation(
        self, fhir_observation: dict[str, Any]
    ) -> dict[str, Any]:
        """Parseia recurso FHIR Observation."""
        results = []

        # Extrair dados do recurso FHIR
        code = fhir_observation.get("code", {}).get("coding", [{}])[0]
        value_quantity = fhir_observation.get("valueQuantity", {})
        reference_range = fhir_observation.get("referenceRange", [{}])[0]

        results.append(
            {
                "test_code": code.get("code", "UNKNOWN"),
                "test_name": code.get("display", "Unknown Test"),
                "value": str(value_quantity.get("value", "")),
                "unit": value_quantity.get("unit", ""),
                "reference_range": reference_range.get("text", ""),
                "is_critical": False,
                "is_abnormal": False,
            }
        )

        return {"results": results}

    async def validate_reference_ranges(
        self, results: list[LabResult]
    ) -> list[str]:
        """Valida resultados contra faixas de referência."""
        messages = []

        for result in results:
            if result.is_abnormal:
                messages.append(
                    _(
                        "Resultado {test_name} fora da faixa de referência: "
                        "{value} {unit} (ref: {reference_range})"
                    ).format(
                        test_name=result.test_name,
                        value=result.value,
                        unit=result.unit,
                        reference_range=result.reference_range or "N/A",
                    )
                )

        return messages

    async def identify_critical_results(
        self, results: list[LabResult]
    ) -> list[LabResult]:
        """Identifica resultados críticos."""
        critical_results = [r for r in results if r.is_critical]

        for result in critical_results:
            logger.warning(
                _("Resultado crítico identificado"),
                extra={
                    "test_name": result.test_name,
                    "value": result.value,
                    "unit": result.unit,
                },
            )

        return critical_results


# ============================================================================
# Função de Execução
# ============================================================================


@require_tenant
@track_task_execution
async def execute(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Executa integração de resultados laboratoriais.

    Args:
        input_data: Dados de entrada validados

    Returns:
        Resultado da integração

    Raises:
        LaboratoryIntegrationException: Se houver erro na integração
    """
    tenant = get_required_tenant()
    parsed_input = IntegrateLaboratoryInput(**input_data)


    integration_id = (
        f"lab_{parsed_input.patient_id}_{parsed_input.order_id}_"
        f"{int(parsed_input.resulted_at.timestamp())}"
    )

    patient_id_hash = hashlib.sha256(
        parsed_input.patient_id.encode()
    ).hexdigest()[:16]

    logger.info(
        _("Iniciando integração laboratorial"),
        extra={
            "tenant_id": tenant.id,
            "integration_id": integration_id,
            "patient_id_hash": patient_id_hash,
            "test_type": parsed_input.test_type,
        },
    )

    start_time = datetime.utcnow()
    # DMN decision support
    _dmn = get_dmn_service()
    try:
        _dmn_config = _dmn.evaluate(
            tenant_id=tenant.id,
            category='infrastructure',
            table_name='config/infra_001',
            inputs={'order_type': parsed_input.order_type},
        )
    except (FileNotFoundError, ValueError):
        _dmn_config = {}



    try:
        # Inicializar cliente FHIR (mock)
        from healthcare_platform.shared.integrations.fhir_client import FHIRClientStub

        fhir_client = FHIRClientStub()
        service = IntegrateLaboratoryStub(fhir_client=fhir_client)

        # Parsear dados de entrada
        parsed_data = None
        if parsed_input.hl7_message:
            parsed_data = await service.parse_hl7_message(parsed_input.hl7_message)
        elif parsed_input.fhir_observation:
            parsed_data = await service.parse_fhir_observation(
                parsed_input.fhir_observation
            )
        else:
            raise LaboratoryIntegrationException(
                message=_("Nenhum dado de entrada válido fornecido"),
                details={"integration_id": integration_id},
            )

        # Criar objetos LabResult
        results = [LabResult(**r) for r in parsed_data.get("results", [])]

        # Validar faixas de referência
        validation_messages = []
        if parsed_input.validate_ranges:
            validation_messages = await service.validate_reference_ranges(results)

        # Identificar resultados críticos
        critical_results = await service.identify_critical_results(results)

        # Contar anormais
        abnormal_count = sum(1 for r in results if r.is_abnormal)

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        output = IntegrateLaboratoryOutput(
            integration_id=integration_id,
            patient_id=parsed_input.patient_id,
            order_id=parsed_input.order_id,
            test_type=parsed_input.test_type,
            results=results,
            critical_results_count=len(critical_results),
            abnormal_results_count=abnormal_count,
            validation_status="validated" if not validation_messages else "warnings",
            validation_messages=validation_messages,
            fhir_resource_id=f"Observation/{integration_id}",
            duration_ms=duration_ms,
        )

        # Métricas
        lab_integrations_total.labels(
            tenant_id=tenant.id,
            test_type=parsed_input.test_type,
            status="success",
        ).inc()

        lab_duration_seconds.labels(
            tenant_id=tenant.id,
            test_type=parsed_input.test_type,
        ).observe(duration_ms / 1000.0)

        if critical_results:
            lab_critical_results_total.labels(
                tenant_id=tenant.id,
                test_type=parsed_input.test_type,
            ).inc(len(critical_results))

        logger.info(
            _("Integração laboratorial concluída com sucesso"),
            extra={
                "tenant_id": tenant.id,
                "integration_id": integration_id,
                "patient_id_hash": patient_id_hash,
                "results_count": len(results),
                "critical_count": len(critical_results),
                "duration_ms": duration_ms,
            },
        )

        return output.model_dump()

    except Exception as e:
        logger.error(
            _("Erro na integração laboratorial"),
            extra={
                "tenant_id": tenant.id,
                "integration_id": integration_id,
                "patient_id_hash": patient_id_hash,
                "error": str(e),
            },
            exc_info=True,
        )
        raise LaboratoryIntegrationException(
            message=_("Falha ao integrar resultados laboratoriais"),
            details={"integration_id": integration_id, "error": str(e)},
        )


# Topic Kafka
TOPIC = "platform.services.integrate-laboratory"
