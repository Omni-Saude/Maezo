"""V2: Register dependent patient linked to primary holder."""
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


@worker(topic='patient.register_dependent')
class RegisterDependentWorkerV2(BaseExternalTaskWorker):
    """Register dependent patient with primary holder relationship.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'patient.register_dependent'
    OPERATION_NAME = 'Registrar Dependente'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        dependent_patient_id = context.variables.get('dependent_patient_id', '')
        primary_holder_patient_id = context.variables.get('primary_holder_patient_id', '')
        relationship_type = context.variables.get('relationship_type', '')
        insurance_plan_id = context.variables.get('insurance_plan_id', '')

        self.logger.info(
            f"Registering dependent {dependent_patient_id} for holder {primary_holder_patient_id}, "
            f"relationship: {relationship_type}, plan: {insurance_plan_id}"
        )

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_dependent_registration',
            variables={
                'dependentId': dependent_patient_id,
                'holderId': primary_holder_patient_id,
                'relationshipType': relationship_type,
                'insurancePlanId': insurance_plan_id
            },
            category='patient_access'
        )
        routing = dmn.get('resultado', 'PROSSEGUIR')
        acao = dmn.get('acao', '')

        if routing == 'BLOQUEAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'BLOQUEAR'})
            return TaskResult.bpmn_error('PATIENT_ACCESS_BLOCKED', acao, {'routing': 'BLOQUEAR', 'acao': acao})

        out = {
            'dependent_patient_id': dependent_patient_id,
            'primary_holder_patient_id': primary_holder_patient_id,
            'related_person_id': dmn.get('relatedPersonId', ''),
            'relationship_type': relationship_type,
            'insurance_plan_id': insurance_plan_id
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
