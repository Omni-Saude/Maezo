"""V2: Verifica autorização prévia de operadora de saúde para agendamentos."""
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


@worker(topic='scheduling.check_pre_auth')
class CheckPreAuthorizationWorkerV2(BaseExternalTaskWorker):
    """Valida se agendamento requer autorização prévia e verifica autorizações existentes.

    Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = 'scheduling.check_pre_auth'
    OPERATION_NAME = 'Verificação de Autorização Prévia'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId', '')
        coverage_id = context.variables.get('coverage_id') or context.variables.get('coverageId', '')
        service_type = context.variables.get('service_type') or context.variables.get('serviceType', '')
        procedure_codes = context.variables.get('procedure_codes') or context.variables.get('procedureCodes', [])
        estimated_cost = context.variables.get('estimated_cost') or context.variables.get('estimatedCost', 0)

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_pre_auth_check',
            variables={
                'patientId': patient_id,
                'coverageId': coverage_id,
                'serviceType': service_type,
                'procedureCodes': procedure_codes if isinstance(procedure_codes, str) else ','.join(procedure_codes),
                'estimatedCost': estimated_cost,
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
        pre_auth_required = dmn.get('pre_auth_required', False)
        authorization_status = dmn.get('authorization_status', 'not_required')
        authorization_number = dmn.get('authorization_number')
        requires_action = dmn.get('requires_action', False)
        action_message = dmn.get('action_message')

        out = {
            'preAuthRequired': pre_auth_required,
            'authorizationStatus': authorization_status,
            'authorizationNumber': authorization_number,
            'requiresAction': requires_action,
            'actionMessage': action_message,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
