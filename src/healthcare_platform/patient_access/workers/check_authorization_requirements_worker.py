"""V2: Verifica requisitos de autorização para procedimentos médicos."""
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


@worker(topic='patient.check_authorization')
class CheckAuthorizationRequirementsWorkerV2(BaseExternalTaskWorker):
    """Verifica se procedimento/serviço requer autorização prévia ANS.

        Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = 'patient.check_authorization'
    OPERATION_NAME = 'Verificação de Requisitos de Autorização'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        procedure_code = context.variables.get('procedure_code') or context.variables.get('procedureCode', '')
        service_type = context.variables.get('service_type') or context.variables.get('serviceType', '')
        operator_code = context.variables.get('operator_code') or context.variables.get('operatorCode', '')
        plan_code = context.variables.get('plan_code') or context.variables.get('planCode', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_authorization_check',
            variables={
                'procedureCode': procedure_code,
                'serviceType': service_type,
                'operatorCode': operator_code,
                'planCode': plan_code,
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
        requires_authorization = dmn.get('requires_authorization', False)
        authorization_type = dmn.get('authorization_type', 'none')
        authorization_criteria = dmn.get('authorization_criteria', [])
        estimated_approval_time = dmn.get('estimated_approval_time')

        out = {
            'requiresAuthorization': requires_authorization,
            'authorizationType': authorization_type,
            'authorizationCriteria': authorization_criteria,
            'estimatedApprovalTime': estimated_approval_time,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
