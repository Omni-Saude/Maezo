"""V2: Create new patient record in the system."""
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


@worker(topic='patient.create_record')
class CreatePatientRecordWorkerV2(BaseExternalTaskWorker):
    """Create new patient record in the system.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'patient.create_record'
    OPERATION_NAME = 'Criar Registro de Paciente'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        cpf_hash = context.variables.get('cpfHash', '')
        cns_hash = context.variables.get('cnsHash', '')
        name = context.variables.get('name', '')
        birth_date = context.variables.get('birthDate', '')
        gender = context.variables.get('gender', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_record_creation',
            variables={
                'cpfHash': cpf_hash,
                'gender': gender,
                'birthDate': birth_date
            },
            category='patient_access'
        )
        routing = dmn.get('resultado', 'PROSSEGUIR')
        acao = dmn.get('acao', '')

        if routing == 'BLOQUEAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'BLOQUEAR'})
            return TaskResult.bpmn_error(
                'PATIENT_ACCESS_BLOCKED',
                acao,
                {'routing': 'BLOQUEAR', 'acao': acao}
            )

        patient_id = dmn.get('patientId', context.process_instance_id)
        out = {
            'patient_id': patient_id,
            'patient_reference': f"Patient/{patient_id}",
            'created': True
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
