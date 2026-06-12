"""Worker: Escalate Contestation SLA Breach.

Triggered when glosa contestation exceeds the defined SLA.
Escalates to denial management supervisor.
"""
import logging
from dataclasses import dataclass
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker

logger = logging.getLogger(__name__)

TOPIC = "platform.sla_escalation_contestation"


@dataclass
class SlaEscalationInput:
    encounter_fhir_id: str
    tenant_id: str
    claim_fhir_id: str = ""


class SlaEscalationContestationWorker(BaseExternalTaskWorker):
    TOPIC = TOPIC

    def execute(self, task):
        variables = task.get_variables()
        inp = SlaEscalationInput(
            encounter_fhir_id=variables.get("encounterFhirId", ""),
            tenant_id=variables.get("tenantId", ""),
            claim_fhir_id=variables.get("claimFhirId", ""),
        )
        logger.warning(
            "Contestation SLA breach detected",
            extra={
                "encounter_fhir_id": inp.encounter_fhir_id,
                "tenant_id": inp.tenant_id,
                "event": "sla_escalation_contestation",
            },
        )
        return task.complete({"slaEscalated": True, "escalationType": "CONTESTATION_SLA"})
