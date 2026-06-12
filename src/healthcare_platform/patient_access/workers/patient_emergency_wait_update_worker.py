"""V2: Atualiza paciente sobre tempo estimado de espera na emergência."""
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


@worker(topic='emergency.wait_update')
class PatientEmergencyWaitUpdateWorkerV2(BaseExternalTaskWorker):
    """Notifica paciente sobre tempo estimado de espera e posição na fila.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'emergency.wait_update'
    OPERATION_NAME = 'Atualização de Espera de Emergência'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId')
        estimated_wait = context.variables.get('estimated_wait_minutes') or context.variables.get('estimatedWaitMinutes', 0)
        queue_position = context.variables.get('queue_position') or context.variables.get('queuePosition', 0)
        triage_level = context.variables.get('triage_level') or context.variables.get('triageLevel', 3)
        # TODO: phone_number sera usado na integracao de notificacao WhatsApp
        # phone_number = context.variables.get('phone_number') or context.variables.get('phoneNumber')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='emergency_wait_notification',
            variables={
                'patientId': patient_id,
                'estimatedWaitMinutes': estimated_wait,
                'queuePosition': queue_position,
                'triageLevel': triage_level,
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
            'estimatedWaitMinutes': estimated_wait,
            'queuePosition': queue_position,
            'triageLevel': triage_level,
            'patientId': patient_id,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
