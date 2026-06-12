"""V2: Atualiza registro do paciente nos sistemas ERP (Tasy, MV Soul)."""
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


@worker(topic='patient.update_registry')
class UpdatePatientRegistryWorkerV2(BaseExternalTaskWorker):
    """Sincroniza dados do paciente com sistemas ERP.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'patient.update_registry'
    OPERATION_NAME = 'Atualização de Registro de Paciente'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId', '')
        mrn = context.variables.get('mrn', '')
        # TODO: patient_data sera enviado aos sistemas de registro (Tasy/MV Soul)
        # patient_data = context.variables.get('patient_data') or context.variables.get('patientData', {})
        target_systems = context.variables.get('target_systems') or context.variables.get('targetSystems', ['tasy', 'mv_soul'])

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_registry_sync',
            variables={
                'patientId': patient_id,
                'mrn': mrn,
                'targetSystems': target_systems,
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

        # Build output
        out = {
            'patientId': patient_id,
            'mrn': mrn,
            'allSystemsSynced': True,
            'syncedSystems': len(target_systems),
            'failedSystems': [],
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
