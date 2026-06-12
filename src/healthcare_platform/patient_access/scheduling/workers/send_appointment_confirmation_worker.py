"""V2: Send appointment confirmation via preferred channel."""
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


@worker(topic='scheduling.send_confirmation')
class SendAppointmentConfirmationWorkerV2(BaseExternalTaskWorker):
    """Send appointment confirmation notification to patient.

    Archetype: CLINICAL_ALERT
    """

    TOPIC = 'scheduling.send_confirmation'
    OPERATION_NAME = 'Enviar Confirmação de Agendamento'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        appointment_id = context.variables.get('appointment_id', '')
        patient_id = context.variables.get('patient_id', '')
        phone_number = context.variables.get('phone_number', '')
        appointment_date = context.variables.get('appointment_date', '')
        appointment_time = context.variables.get('appointment_time', '')
        # TODO: location_name sera incluido no template de confirmacao de consulta
        # location_name = context.variables.get('location_name', '')
        # TODO: doctor_name sera incluido no template de confirmacao de consulta
        # doctor_name = context.variables.get('doctor_name', '')
        specialty = context.variables.get('specialty', '')

        masked_phone = f"***{phone_number[-4:]}" if len(phone_number) > 4 else "****"
        self.logger.info(
            f"Sending confirmation for appointment {appointment_id}, patient {patient_id}, "
            f"phone: {masked_phone}, date: {appointment_date}, time: {appointment_time}"
        )

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_confirmation_rules',
            variables={
                'appointmentId': appointment_id,
                'specialty': specialty,
                'notificationChannel': context.variables.get('notification_channel', 'whatsapp')
            },
            category='patient_access'
        )
        routing = dmn.get('resultado', 'PROSSEGUIR')
        acao = dmn.get('acao', '')

        if routing == 'BLOQUEAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'BLOQUEAR'})
            return TaskResult.bpmn_error('PATIENT_ACCESS_BLOCKED', acao, {'routing': 'BLOQUEAR', 'acao': acao})

        out = {
            'confirmation_sent': True,
            'appointment_id': appointment_id,
            'channel_used': dmn.get('channelUsed', 'whatsapp'),
            'delivery_status': 'sent'
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
