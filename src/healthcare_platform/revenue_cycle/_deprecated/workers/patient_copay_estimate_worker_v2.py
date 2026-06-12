"""
Patient Copay Estimate Worker (Refactored)
Purpose: Validate and send pre-visit copay estimate via WhatsApp

TOPIC: financial.copay_estimate

Refactored using template-first approach:
- Phone/coverage validation extracted to DMN: copay_validation_adjudication.dmn
- Worker focuses on: DMN validation + copay formatting + WhatsApp send

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from healthcare_platform.shared.integrations.whatsapp_client import (
    WhatsAppClientProtocol,
)
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


# ── Pydantic Models (for backward compat with tests) ──

class PatientCopayEstimateInput(BaseModel):
    """Input model for copay estimate notification."""
    patient_id: str = Field(..., description="Patient identifier")
    phone_number: str = Field(..., pattern=r'^\+', description="Patient phone number (E.164 format)")
    appointment_id: str = Field(..., description="Appointment identifier")
    procedure_codes: List[str] = Field(..., description="Procedure codes")
    estimated_copay: float = Field(..., ge=0, description="Estimated copay amount in BRL")
    insurance_coverage: float = Field(..., ge=0, le=100, description="Insurance coverage percentage")
    appointment_date: str = Field(..., description="Appointment date")


class PatientCopayEstimateOutput(BaseModel):
    """Output model for copay estimate notification."""
    notification_sent: bool = Field(..., description="Whether notification was sent")
    message_id: Optional[str] = Field(None, description="WhatsApp message ID")
    sent_at: str = Field(..., description="ISO 8601 timestamp when sent")
    payment_action: Optional[str] = Field(None, description="Payment action taken")


def format_brl(amount: float) -> str:
    """Format amount as Brazilian Real (R$ 1.234,56)."""
    formatted = f"R$ {amount:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


class PatientCopayEstimateWorker(BaseExternalTaskWorker):
    """
    Refactored copay estimate worker.

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for validation (phone format, coverage range, copay sign)
    3. Format copay amount
    4. Send WhatsApp notification with payment options
    """

    TOPIC = "financial.copay_estimate"
    DMN_DECISION_KEY = "copay_validation_adjudication"
    DMN_CATEGORY = "cash_operations/estimates"

    def __init__(
        self,
        whatsapp_client: Optional[WhatsAppClientProtocol] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.whatsapp_client = whatsapp_client

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute copay estimate notification."""
        try:
            variables = context.variables
            patient_id = variables.get("patientId", "")
            phone_number = variables.get("phoneNumber", "")
            appointment_id = variables.get("appointmentId", "")
            estimated_copay = float(variables.get("estimatedCopay", 0))
            insurance_coverage = float(variables.get("insuranceCoverage", 0))
            appointment_date = variables.get("appointmentDate", "")

            if not patient_id or not phone_number or not appointment_id:
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_INPUT",
                    error_message="Missing patientId, phoneNumber, or appointmentId",
                )

            # Determine phone format for DMN
            phone_format = "E.164" if phone_number.startswith("+") else "invalid"

            # Evaluate DMN for validation
            dmn_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DECISION_KEY,
                variables={
                    "phoneFormat": phone_format,
                    "insuranceCoverage": insurance_coverage,
                    "estimatedCopay": estimated_copay,
                },
                category=self.DMN_CATEGORY,
            )

            resultado = dmn_result.get("resultado", "PROSSEGUIR")
            acao = dmn_result.get("acao", "")
            risco = dmn_result.get("risco", "BAIXO")

            # BLOQUEAR = validation failed
            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(
                    error_code="ERR_COPAY_VALIDATION",
                    error_message=acao,
                    variables={"resultado": resultado, "risco": risco},
                )

            # REVISAR = needs manual review
            if resultado == "REVISAR":
                return TaskResult.success({
                    "notificationSent": False,
                    "requiresReview": True,
                    "resultado": resultado,
                    "acao": acao,
                    "risco": risco,
                })

            # PROSSEGUIR = send notification
            formatted_copay = format_brl(estimated_copay)
            # DEPRECATED: payment_url era usado no link de pagamento enviado ao paciente
            # payment_url = f"https://portal.maezo.com.br/pay/{appointment_id}"

            message_id = None
            if self.whatsapp_client:
                message_id = self.whatsapp_client.send_template(
                    to=phone_number,
                    template_name="copay_estimate_v1",
                    language_code="pt_BR",
                    body_params=[
                        appointment_date,
                        formatted_copay,
                        f"{insurance_coverage:.0f}%",
                    ],
                )

            return TaskResult.success({
                "notificationSent": True,
                "messageId": message_id,
                "sentAt": datetime.utcnow().isoformat(),
                "resultado": resultado,
                "acao": acao,
                "risco": risco,
                "formattedCopay": formatted_copay,
            })

        except Exception as e:
            self.logger.error(f"Copay estimate failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_COPAY_ESTIMATE",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
