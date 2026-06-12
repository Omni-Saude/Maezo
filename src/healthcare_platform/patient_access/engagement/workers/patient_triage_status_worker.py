"""V2: Notifica paciente sobre resultado da classificação de triagem."""
from __future__ import annotations

import time

from healthcare_platform.revenue_cycle.billing.workers.base import worker
from healthcare_platform.shared.observability.correlation import (
    extract_correlation,
    log_worker_start,
    log_worker_end,
)
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


@worker(topic='emergency.triage_status')
class PatientTriageStatusWorkerV2(BaseExternalTaskWorker):
    """Notifica paciente sobre classificação de triagem e próximos passos.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'emergency.triage_status'
    OPERATION_NAME = 'Status de Triagem'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId')
        triage_level = context.variables.get('triage_level') or context.variables.get('triageLevel', 3)
        triage_description = context.variables.get('triage_description') or context.variables.get('triageDescription', '')
        next_steps = context.variables.get('next_steps') or context.variables.get('nextSteps', '')
        # TODO: phone_number sera usado na integracao de notificacao WhatsApp
        # phone_number = context.variables.get('phone_number') or context.variables.get('phoneNumber')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='triage_status_notification',
            variables={
                'patientId': patient_id,
                'triageLevel': triage_level,
                'triageDescription': triage_description,
            },
            category='patient_access',
        )
        routing = dmn.get('resultado', 'PROSSEGUIR')
        acao = dmn.get('acao', '')

        if routing == 'BLOQUEAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'BLOQUEAR'})
            return TaskResult.bpmn_error(
                'PATIENT_ACCESS_BLOCKED', acao, {'routing': 'BLOQUEAR', 'acao': acao},
            )

        # Build output variables
        out = {
            'notificationSent': True,
            'patientId': patient_id,
            'triageLevel': triage_level,
            'triageDescription': triage_description,
            'nextSteps': next_steps,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
