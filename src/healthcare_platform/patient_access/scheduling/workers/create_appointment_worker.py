"""V2: Create appointment in scheduling system."""
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


@worker(topic='scheduling.create_appointment')
class CreateAppointmentWorkerV2(BaseExternalTaskWorker):
    """Create appointment in scheduling system.

    Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'scheduling.create_appointment'
    OPERATION_NAME = 'Criar Agendamento'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        patient_id = context.variables.get('patientId', '')
        practitioner_id = context.variables.get('practitionerId', '')
        slot_id = context.variables.get('slotId', '')
        start_datetime = context.variables.get('startDatetime', '')
        end_datetime = context.variables.get('endDatetime', '')
        service_type = context.variables.get('serviceType', '')
        specialty_code = context.variables.get('specialtyCode', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_appointment_creation',
            variables={
                'patientId': patient_id,
                'practitionerId': practitioner_id,
                'slotId': slot_id,
                'serviceType': service_type,
                'specialtyCode': specialty_code
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

        appointment_id = dmn.get('appointmentId', context.process_instance_id)
        out = {
            'appointment_id': appointment_id,
            'appointment_reference': f"Appointment/{appointment_id}",
            'status': 'booked',
            'start_datetime': start_datetime,
            'end_datetime': end_datetime
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
