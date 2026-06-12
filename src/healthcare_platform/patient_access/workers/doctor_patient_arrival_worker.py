"""V2: Notifica médico quando paciente chega para consulta agendada."""
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


@worker(topic='scheduling.patient_arrival')
class DoctorPatientArrivalWorkerV2(BaseExternalTaskWorker):
    """Envia notificação WhatsApp para médico sobre chegada do paciente.

        Archetype: CLINICAL_ALERT
    """

    TOPIC = 'scheduling.patient_arrival'
    OPERATION_NAME = 'Notificação de Chegada de Paciente'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        doctor_id = context.variables.get('doctor_id') or context.variables.get('doctorId', '')
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId', '')
        # TODO: patient_name sera usado na mensagem de notificacao ao medico
        # patient_name = context.variables.get('patient_name') or context.variables.get('patientName', 'Paciente')
        appointment_id = context.variables.get('appointment_id') or context.variables.get('appointmentId', '')
        appointment_time = context.variables.get('appointment_time') or context.variables.get('appointmentTime', '')
        location = context.variables.get('location', '')
        # TODO: phone_number sera usado na integracao de notificacao WhatsApp
        # phone_number = context.variables.get('phone_number') or context.variables.get('phoneNumber', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='doctor_patient_arrival_notification',
            variables={
                'doctorId': doctor_id,
                'patientId': patient_id,
                'appointmentId': appointment_id,
                'appointmentTime': appointment_time,
                'location': location,
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
        message_id = dmn.get('message_id', f'msg_{appointment_id[:8]}')

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
