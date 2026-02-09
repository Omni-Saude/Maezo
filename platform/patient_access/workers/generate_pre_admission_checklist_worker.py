"""
Generate Pre-Admission Checklist Worker

CIB7 External Task Topic: scheduling.generate_checklist
BPMN Error Code: PATIENT_ACCESS_ERROR

Generates checklist of required documents and exams before admission.
Rules are based on appointment type (internação requires more documents).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


class PatientAccessException(DomainException):
    """Domain exception for patient access operations."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="PATIENT_ACCESS_ERROR",
            details=details,
            bpmn_error_code="PATIENT_ACCESS_ERROR",
        )


class ChecklistItem(BaseModel):
    """Individual checklist item."""

    item_id: str = Field(..., description="Unique identifier for checklist item")
    description: str = Field(..., description="Item description in Portuguese")
    required: bool = Field(..., description="Whether item is mandatory")
    deadline: str | None = Field(
        None, description="Deadline for item (ISO 8601 date)"
    )
    category: str = Field(..., description="Item category (document, exam, preparation)")
    notes: str | None = Field(None, description="Additional notes or instructions")


class GeneratePreAdmissionChecklistInput(BaseModel):
    """Input DTO for pre-admission checklist generation."""

    appointment_id: str = Field(..., description="FHIR Appointment ID")
    appointment_type: str = Field(
        ..., description="Appointment type (consulta, internacao, cirurgia, exame)"
    )
    specialty: str = Field(..., description="Medical specialty")
    procedure_code: str | None = Field(None, description="TUSS procedure code if applicable")
    patient_age: int = Field(..., description="Patient age in years")
    has_insurance: bool = Field(..., description="Whether patient has health insurance")
    insurance_plan: str | None = Field(None, description="Insurance plan name")


class GeneratePreAdmissionChecklistOutput(BaseModel):
    """Output DTO for pre-admission checklist."""

    checklist_items: list[ChecklistItem] = Field(
        ..., description="List of checklist items"
    )
    total_items: int = Field(..., description="Total number of items")
    required_items: int = Field(..., description="Number of required items")
    optional_items: int = Field(..., description="Number of optional items")
    earliest_deadline: str | None = Field(
        None, description="Earliest deadline among items (ISO 8601)"
    )
    instructions: str = Field(..., description="General instructions in Portuguese")


class PreAdmissionChecklistGeneratorProtocol(ABC):
    """Protocol for generating pre-admission checklists."""

    @abstractmethod
    async def generate_checklist(
        self,
        appointment_type: str,
        specialty: str,
        procedure_code: str | None,
        patient_age: int,
        has_insurance: bool,
        insurance_plan: str | None,
    ) -> list[ChecklistItem]:
        """
        Generate pre-admission checklist based on appointment details.

        Args:
            appointment_type: Type of appointment
            specialty: Medical specialty
            procedure_code: TUSS procedure code if applicable
            patient_age: Patient age in years
            has_insurance: Whether patient has health insurance
            insurance_plan: Insurance plan name

        Returns:
            List of checklist items
        """
        pass


class StubPreAdmissionChecklistGenerator(PreAdmissionChecklistGeneratorProtocol):
    """Stub implementation for testing."""

    def __init__(self):
        self.logger = get_logger(__name__, worker="scheduling.generate_checklist")

    async def generate_checklist(
        self,
        appointment_type: str,
        specialty: str,
        procedure_code: str | None,
        patient_age: int,
        has_insurance: bool,
        insurance_plan: str | None,
    ) -> list[ChecklistItem]:
        """Stub implementation - returns sample checklist."""
        from datetime import datetime, timedelta, timezone

        deadline_3days = (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat()
        deadline_1day = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()

        self.logger.info(
            "stub_checklist_generated",
            appointment_type=appointment_type,
            specialty=specialty,
            has_insurance=has_insurance,
        )

        # Base items for all appointments
        items = [
            ChecklistItem(
                item_id="doc_rg",
                description=_("Documento de identidade com foto (RG, CNH ou RNE)"),
                required=True,
                deadline=deadline_1day,
                category="document",
                notes=_("Original ou cópia autenticada"),
            ),
            ChecklistItem(
                item_id="doc_cpf",
                description=_("CPF (Cadastro de Pessoa Física)"),
                required=True,
                deadline=deadline_1day,
                category="document",
                notes=_("Original ou cópia"),
            ),
        ]

        # Add insurance documents if applicable
        if has_insurance:
            items.append(
                ChecklistItem(
                    item_id="doc_insurance_card",
                    description=_("Carteirinha do convênio"),
                    required=True,
                    deadline=deadline_1day,
                    category="document",
                    notes=_("Dentro da validade"),
                )
            )
            items.append(
                ChecklistItem(
                    item_id="doc_authorization",
                    description=_("Guia de autorização do convênio"),
                    required=True,
                    deadline=deadline_1day,
                    category="document",
                    notes=_("Com senha ou número de autorização"),
                )
            )

        # Add items based on appointment type
        if appointment_type in ["internacao", "cirurgia"]:
            items.extend(
                [
                    ChecklistItem(
                        item_id="exam_blood_type",
                        description=_("Resultado de tipagem sanguínea"),
                        required=True,
                        deadline=deadline_3days,
                        category="exam",
                        notes=_("Validade de 30 dias"),
                    ),
                    ChecklistItem(
                        item_id="exam_ecg",
                        description=_("Eletrocardiograma (ECG)"),
                        required=patient_age > 40,
                        deadline=deadline_3days,
                        category="exam",
                        notes=_("Obrigatório para pacientes acima de 40 anos"),
                    ),
                    ChecklistItem(
                        item_id="exam_chest_xray",
                        description=_("Raio-X de tórax"),
                        required=True,
                        deadline=deadline_3days,
                        category="exam",
                        notes=_("Validade de 90 dias"),
                    ),
                    ChecklistItem(
                        item_id="prep_fasting",
                        description=_("Jejum de 8 horas antes do procedimento"),
                        required=True,
                        deadline=None,
                        category="preparation",
                        notes=_("Não ingerir alimentos sólidos ou líquidos"),
                    ),
                ]
            )

        # Add items for surgical procedures
        if appointment_type == "cirurgia":
            items.append(
                ChecklistItem(
                    item_id="doc_consent_form",
                    description=_("Termo de consentimento cirúrgico assinado"),
                    required=True,
                    deadline=deadline_1day,
                    category="document",
                    notes=_("Será fornecido na admissão"),
                )
            )

        return items


class GeneratePreAdmissionChecklistWorker:
    """Worker to generate pre-admission checklists."""

    TOPIC = "scheduling.generate_checklist"

    def __init__(
        self,
        checklist_generator: PreAdmissionChecklistGeneratorProtocol | None = None,
    ):
        """
        Initialize worker.

        Args:
            checklist_generator: Service to generate checklists (defaults to stub)
        """
        self.checklist_generator = checklist_generator or StubPreAdmissionChecklistGenerator()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(task_type="scheduling.generate_checklist")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute pre-admission checklist generation.

        Args:
            task_variables: Task variables from CIB7 process

        Returns:
            Dictionary with checklist items and summary

        Raises:
            PatientAccessException: If checklist generation fails
        """
        tenant_id = get_required_tenant()

        try:
            # Parse and validate input
            input_data = GeneratePreAdmissionChecklistInput(**task_variables)

            self.logger.info(
                "generating_pre_admission_checklist",
                tenant_id=tenant_id,
                appointment_id=input_data.appointment_id,
                appointment_type=input_data.appointment_type,
                specialty=input_data.specialty,
            )

            # Generate checklist
            checklist_items = await self.checklist_generator.generate_checklist(
                appointment_type=input_data.appointment_type,
                specialty=input_data.specialty,
                procedure_code=input_data.procedure_code,
                patient_age=input_data.patient_age,
                has_insurance=input_data.has_insurance,
                insurance_plan=input_data.insurance_plan,
            )

            # Calculate summary statistics
            total_items = len(checklist_items)
            required_items = sum(1 for item in checklist_items if item.required)
            optional_items = total_items - required_items

            # Find earliest deadline
            deadlines = [item.deadline for item in checklist_items if item.deadline]
            earliest_deadline = min(deadlines) if deadlines else None

            # Generate general instructions
            instructions = self._generate_instructions(input_data.appointment_type)

            # Validate output
            output = GeneratePreAdmissionChecklistOutput(
                checklist_items=checklist_items,
                total_items=total_items,
                required_items=required_items,
                optional_items=optional_items,
                earliest_deadline=earliest_deadline,
                instructions=instructions,
            )

            self.logger.info(
                "pre_admission_checklist_generated",
                tenant_id=tenant_id,
                appointment_id=input_data.appointment_id,
                total_items=total_items,
                required_items=required_items,
                optional_items=optional_items,
            )

            return output.model_dump()

        except Exception as e:
            self.logger.error(
                "checklist_generation_failed",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PatientAccessException(
                message=_("Falha ao gerar checklist de pré-admissão: {error}").format(
                    error=str(e)
                ),
                details={
                    "appointment_id": task_variables.get("appointment_id"),
                    "appointment_type": task_variables.get("appointment_type"),
                    "error_type": type(e).__name__,
                },
            ) from e

    def _generate_instructions(self, appointment_type: str) -> str:
        """Generate general instructions based on appointment type."""
        instructions_map = {
            "consulta": _(
                "Apresente-se na recepção 15 minutos antes do horário agendado "
                "com seus documentos e exames anteriores."
            ),
            "internacao": _(
                "Complete todos os itens obrigatórios antes da data de internação. "
                "Apresente-se na recepção com 2 horas de antecedência. "
                "Traga um acompanhante e itens de higiene pessoal."
            ),
            "cirurgia": _(
                "Complete todos os exames pré-operatórios antes da data da cirurgia. "
                "Siga rigorosamente as instruções de jejum. "
                "Apresente-se com 3 horas de antecedência com um acompanhante responsável."
            ),
            "exame": _(
                "Apresente-se na recepção 10 minutos antes do horário agendado. "
                "Verifique se há orientações específicas de preparo para o seu exame."
            ),
        }

        return instructions_map.get(
            appointment_type,
            _("Apresente-se na recepção com antecedência mínima de 15 minutos."),
        )
