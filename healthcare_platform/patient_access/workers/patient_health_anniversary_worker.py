"""V2: Celebra marcos de saúde do paciente (livre de câncer, transplante, etc)."""
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


@worker(topic='relationship.anniversary')
class PatientHealthAnniversaryWorkerV2(BaseExternalTaskWorker):
    """Envia notificação comemorativa de marcos de saúde com opções de compartilhamento.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'relationship.anniversary'
    OPERATION_NAME = 'Aniversário de Saúde'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId')
        patient_name = context.variables.get('patient_name') or context.variables.get('patientName', '')
        milestone_type = context.variables.get('milestone_type') or context.variables.get('milestoneType', '')
        years_since = context.variables.get('years_since') or context.variables.get('yearsSince', 1)
        milestone_date = context.variables.get('milestone_date') or context.variables.get('milestoneDate', '')
        phone_number = context.variables.get('phone_number') or context.variables.get('phoneNumber')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='health_anniversary_notification',
            variables={
                'patientId': patient_id,
                'milestoneType': milestone_type,
                'yearsSince': years_since,
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
            'milestoneType': milestone_type,
            'yearsSince': years_since,
            'feedbackReceived': False,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
