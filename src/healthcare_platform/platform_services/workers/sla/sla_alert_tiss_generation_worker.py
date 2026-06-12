"""Worker: Alert TISS Generation SLA Risk.

Triggered when TISS XML generation approaches the 24h SLA.
Non-interrupting alert for billing team.
"""
import logging
from dataclasses import dataclass
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker

logger = logging.getLogger(__name__)

TOPIC = "platform.sla_alert_tiss_generation"


@dataclass
class SlaAlertInput:
    encounter_fhir_id: str
    tenant_id: str
    claim_fhir_id: str = ""


class SlaAlertTissGenerationWorker(BaseExternalTaskWorker):
    TOPIC = TOPIC

    def execute(self, task):
        variables = task.get_variables()
        inp = SlaAlertInput(
            encounter_fhir_id=variables.get("encounterFhirId", ""),
            tenant_id=variables.get("tenantId", ""),
            claim_fhir_id=variables.get("claimFhirId", ""),
        )
        logger.warning(
            "TISS generation SLA risk",
            extra={
                "encounter_fhir_id": inp.encounter_fhir_id,
                "tenant_id": inp.tenant_id,
                "event": "sla_alert_tiss_generation",
            },
        )
        return task.complete({"slaAlerted": True, "alertType": "TISS_GENERATION_24H"})
