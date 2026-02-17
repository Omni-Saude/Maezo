"""V2: Send appointment reminder notification to patient."""
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


@worker(topic='scheduling.send_reminder')
class SendReminderNotificationWorkerV2(BaseExternalTaskWorker):
    """Send appointment reminder notification to patient.

        Archetype: CLINICAL_ALERT
    """

    TOPIC = 'scheduling.send_reminder'
    OPERATION_NAME = 'Enviar Lembrete de Agendamento'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        appointment_id = context.variables.get('appointment_id', '')
        patient_id = context.variables.get('patient_id', '')
        phone_number = context.variables.get('phone_number', '')
        reminder_type = context.variables.get('reminder_type', '')
        appointment_date = context.variables.get('appointment_date', '')
        appointment_time = context.variables.get('appointment_time', '')

        masked_phone = f"***{phone_number[-4:]}" if len(phone_number) > 4 else "****"
        self.logger.info(
            f"Sending {reminder_type} reminder for appointment {appointment_id}, "
            f"patient {patient_id}, phone: {masked_phone}, date: {appointment_date}"
        )

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_reminder_rules',
            variables={
                'appointmentId': appointment_id,
                'reminderType': reminder_type,
                'appointmentDate': appointment_date
            },
            category='patient_access'
        )
        routing = dmn.get('resultado', 'PROSSEGUIR')
        acao = dmn.get('acao', '')

        if routing == 'BLOQUEAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'BLOQUEAR'})
            return TaskResult.bpmn_error('PATIENT_ACCESS_BLOCKED', acao, {'routing': 'BLOQUEAR', 'acao': acao})

        out = {
            'reminder_sent': True,
            'appointment_id': appointment_id,
            'reminder_type': reminder_type,
            'delivery_status': 'sent',
            'interactive_enabled': dmn.get('interactiveEnabled', True)
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
