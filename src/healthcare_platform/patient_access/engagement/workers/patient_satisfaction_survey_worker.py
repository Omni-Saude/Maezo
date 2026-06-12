"""V2: Envia pesquisa de satisfação pós-visita com botões de avaliação NPS."""
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


@worker(topic='relationship.survey')
class PatientSatisfactionSurveyWorkerV2(BaseExternalTaskWorker):
    """Envia pesquisa de satisfação pós-visita com avaliação NPS.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'relationship.survey'
    OPERATION_NAME = 'Pesquisa de Satisfação'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId')
        visit_date = context.variables.get('visit_date') or context.variables.get('visitDate', '')
        visit_type = context.variables.get('visit_type') or context.variables.get('visitType', '')
        # TODO: provider_name sera usado no template de pesquisa de satisfacao
        # provider_name = context.variables.get('provider_name') or context.variables.get('providerName', '')
        department = context.variables.get('department', '')
        # TODO: phone_number sera usado na integracao de notificacao WhatsApp
        # phone_number = context.variables.get('phone_number') or context.variables.get('phoneNumber')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='satisfaction_survey_notification',
            variables={
                'patientId': patient_id,
                'visitType': visit_type,
                'visitDate': visit_date,
                'department': department,
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
            'visitType': visit_type,
            'visitDate': visit_date,
            'responseReceived': False,
            'npsScore': None,
            'feedback': None,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
