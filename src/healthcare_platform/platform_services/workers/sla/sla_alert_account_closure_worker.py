"""Worker: Alert Account Closure SLA Risk.

Triggered when clinical production account closure approaches the 24h SLA.
Non-interrupting — alerts without stopping the process.
"""
import logging
from dataclasses import dataclass
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker

logger = logging.getLogger(__name__)

TOPIC = "platform.sla_alert_account_closure"


@dataclass
class SlaAlertInput:
    encounter_fhir_id: str
    tenant_id: str


class SlaAlertAccountClosureWorker(BaseExternalTaskWorker):
    TOPIC = TOPIC

    def execute(self, task):
        variables = task.get_variables()
        inp = SlaAlertInput(
            encounter_fhir_id=variables.get("encounterFhirId", ""),
            tenant_id=variables.get("tenantId", ""),
        )
        logger.warning(
            "Account closure SLA risk",
            extra={
                "encounter_fhir_id": inp.encounter_fhir_id,
                "tenant_id": inp.tenant_id,
                "event": "sla_alert_account_closure",
            },
        )
        return task.complete({"slaAlerted": True, "alertType": "ACCOUNT_CLOSURE_24H"})
