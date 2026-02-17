"""V2: Envia saudação de aniversário personalizada com dicas de bem-estar."""
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


@worker(topic='relationship.birthday')
class PatientBirthdayWorkerV2(BaseExternalTaskWorker):
    """Envia mensagem de aniversário personalizada com dica de saúde adequada à idade.

    Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'relationship.birthday'
    OPERATION_NAME = 'Saudação de Aniversário'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId', '')
        patient_name = context.variables.get('patient_name') or context.variables.get('patientName', 'Paciente')
        phone_number = context.variables.get('phone_number') or context.variables.get('phoneNumber', '')
        age = context.variables.get('age', 0)
        health_conditions = context.variables.get('health_conditions') or context.variables.get('healthConditions', [])

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_birthday_greeting',
            variables={
                'patientId': patient_id,
                'patientName': patient_name,
                'age': age,
                'healthConditions': health_conditions if isinstance(health_conditions, str) else ','.join(health_conditions),
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
        notification_sent = dmn.get('notification_sent', True)
        message_id = dmn.get('message_id', f'birthday_{patient_id[:8]}')

        out = {
            'notificationSent': notification_sent,
            'messageId': message_id,
            'sentAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
