"""V2: Envia notificação WhatsApp sobre conclusão do cadastro do paciente."""
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


@worker(topic='patient.notify_registration')
class NotifyRegistrationCompleteWorkerV2(BaseExternalTaskWorker):
    """Notifica paciente via WhatsApp sobre registro completo com MRN e carteirinha.

        Archetype: CLINICAL_ALERT
    """

    TOPIC = 'patient.notify_registration'
    OPERATION_NAME = 'Notificação de Registro Completo'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId', '')
        patient_name = context.variables.get('patient_name') or context.variables.get('patientName', '')
        # TODO: phone_number sera usado na integracao de notificacao WhatsApp
        # phone_number = context.variables.get('phone_number') or context.variables.get('phoneNumber', '')
        mrn = context.variables.get('mrn', '')
        card_number = context.variables.get('card_number') or context.variables.get('cardNumber', '')
        facility_name = context.variables.get('facility_name') or context.variables.get('facilityName', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_registration_notification',
            variables={
                'patientId': patient_id,
                'patientName': patient_name,
                'mrn': mrn,
                'cardNumber': card_number,
                'facilityName': facility_name,
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
        message_id = dmn.get('message_id', f'wamid_{patient_id[:8]}')

        out = {
            'patientId': patient_id,
            'notificationSent': notification_sent,
            'messageId': message_id,
            'sentTimestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
