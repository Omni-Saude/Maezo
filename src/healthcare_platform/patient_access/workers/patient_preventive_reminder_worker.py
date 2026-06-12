"""V2: Lembra pacientes sobre cuidados preventivos atrasados com opções de agendamento."""
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


@worker(topic='relationship.preventive')
class PatientPreventiveReminderWorkerV2(BaseExternalTaskWorker):
    """Envia lembretes de cuidados preventivos com opções de agendamento.

        Archetype: CLINICAL_ALERT
    """

    TOPIC = 'relationship.preventive'
    OPERATION_NAME = 'Lembrete Preventivo'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId')
        # TODO: patient_name sera usado na mensagem de lembrete preventivo
        # patient_name = context.variables.get('patient_name') or context.variables.get('patientName', '')
        preventive_type = context.variables.get('preventive_type') or context.variables.get('preventiveType', '')
        last_date = context.variables.get('last_date') or context.variables.get('lastDate', '')
        recommended_frequency = context.variables.get('recommended_frequency') or context.variables.get('recommendedFrequency', 'annual')
        # TODO: phone_number sera usado na integracao de notificacao WhatsApp
        # phone_number = context.variables.get('phone_number') or context.variables.get('phoneNumber')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='preventive_reminder_notification',
            variables={
                'patientId': patient_id,
                'preventiveType': preventive_type,
                'lastDate': last_date,
                'recommendedFrequency': recommended_frequency,
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
            'preventiveType': preventive_type,
            'lastDate': last_date,
            'actionTaken': None,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
