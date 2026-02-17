"""Appointment, Slot, and Practitioner FHIR resource fixtures."""

from __future__ import annotations

from typing import Dict, Any


APPOINTMENT_CONSULTATION: Dict[str, Any] = {
    "resourceType": "Appointment",
    "id": "appointment-consultation-001",
    "status": "booked",
    "serviceType": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/service-type",
                    "code": "124",
                    "display": "General Practice",
                }
            ]
        }
    ],
    "appointmentType": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/v2-0276",
                "code": "ROUTINE",
                "display": "Routine appointment",
            }
        ]
    },
    "description": "Consulta de rotina - Clínica Geral",
    "start": "2024-03-15T10:00:00Z",
    "end": "2024-03-15T10:30:00Z",
    "minutesDuration": 30,
    "participant": [
        {
            "actor": {"reference": "Patient/patient-valid-001"},
            "status": "accepted",
        },
        {
            "actor": {"reference": "Practitioner/practitioner-general"},
            "status": "accepted",
        },
        {
            "actor": {"reference": "Location/location-001"},
            "status": "accepted",
        },
    ],
}

APPOINTMENT_SURGICAL: Dict[str, Any] = {
    "resourceType": "Appointment",
    "id": "appointment-surgical-001",
    "status": "booked",
    "serviceType": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/service-type",
                    "code": "221",
                    "display": "Surgery - General",
                }
            ]
        }
    ],
    "appointmentType": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/v2-0276",
                "code": "CHECKUP",
                "display": "Pre-operative assessment",
            }
        ]
    },
    "description": "Cirurgia eletiva - Colecistectomia laparoscópica",
    "start": "2024-03-20T08:00:00Z",
    "end": "2024-03-20T11:00:00Z",
    "minutesDuration": 180,
    "priority": 5,
    "participant": [
        {
            "actor": {"reference": "Patient/patient-valid-001"},
            "required": "required",
            "status": "accepted",
        },
        {
            "actor": {"reference": "Practitioner/surgeon-001"},
            "required": "required",
            "status": "accepted",
        },
        {
            "actor": {"reference": "Location/surgery-room-01"},
            "required": "required",
            "status": "accepted",
        },
    ],
}

APPOINTMENT_DIAGNOSTIC: Dict[str, Any] = {
    "resourceType": "Appointment",
    "id": "appointment-diagnostic-001",
    "status": "booked",
    "serviceType": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/service-type",
                    "code": "409",
                    "display": "Diagnostic Radiology",
                }
            ]
        }
    ],
    "appointmentType": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/v2-0276",
                "code": "ROUTINE",
                "display": "Routine appointment",
            }
        ]
    },
    "description": "Ressonância Magnética - Coluna Lombar",
    "start": "2024-03-18T14:00:00Z",
    "end": "2024-03-18T14:45:00Z",
    "minutesDuration": 45,
    "participant": [
        {
            "actor": {"reference": "Patient/patient-valid-001"},
            "status": "accepted",
        },
        {
            "actor": {"reference": "Location/imaging-room-02"},
            "status": "accepted",
        },
    ],
}

APPOINTMENT_FOLLOW_UP: Dict[str, Any] = {
    "resourceType": "Appointment",
    "id": "appointment-followup-001",
    "status": "booked",
    "serviceType": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/service-type",
                    "code": "57",
                    "display": "Cardiology",
                }
            ]
        }
    ],
    "appointmentType": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/v2-0276",
                "code": "FOLLOWUP",
                "display": "Follow-up",
            }
        ]
    },
    "description": "Retorno pós-procedimento cardíaco",
    "start": "2024-04-01T11:00:00Z",
    "end": "2024-04-01T11:30:00Z",
    "minutesDuration": 30,
    "basedOn": [{"reference": "Appointment/appointment-surgical-001"}],
    "participant": [
        {
            "actor": {"reference": "Patient/patient-valid-001"},
            "status": "accepted",
        },
        {
            "actor": {"reference": "Practitioner/cardiologist-001"},
            "status": "accepted",
        },
    ],
}

APPOINTMENT_CANCELLED: Dict[str, Any] = {
    "resourceType": "Appointment",
    "id": "appointment-cancelled-001",
    "status": "cancelled",
    "cancelationReason": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/appointment-cancellation-reason",
                "code": "pat",
                "display": "Patient",
            }
        ],
        "text": "Paciente solicitou cancelamento por motivos pessoais",
    },
    "serviceType": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/service-type",
                    "code": "124",
                    "display": "General Practice",
                }
            ]
        }
    ],
    "start": "2024-03-12T09:00:00Z",
    "end": "2024-03-12T09:30:00Z",
    "participant": [
        {
            "actor": {"reference": "Patient/patient-valid-001"},
            "status": "declined",
        },
    ],
}

APPOINTMENT_RESCHEDULED: Dict[str, Any] = {
    "resourceType": "Appointment",
    "id": "appointment-rescheduled-001",
    "status": "booked",
    "serviceType": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/service-type",
                    "code": "124",
                    "display": "General Practice",
                }
            ]
        }
    ],
    "start": "2024-03-22T15:00:00Z",  # Nova data
    "end": "2024-03-22T15:30:00Z",
    "minutesDuration": 30,
    "participant": [
        {
            "actor": {"reference": "Patient/patient-valid-001"},
            "status": "accepted",
        },
        {
            "actor": {"reference": "Practitioner/practitioner-general"},
            "status": "accepted",
        },
    ],
    "extension": [
        {
            "url": "http://austa.com.br/fhir/extension/rescheduled-from",
            "valueReference": {"reference": "Appointment/appointment-cancelled-001"},
        }
    ],
}

SLOT_AVAILABLE: Dict[str, Any] = {
    "resourceType": "Slot",
    "id": "slot-available-001",
    "schedule": {"reference": "Schedule/schedule-general-001"},
    "status": "free",
    "start": "2024-03-25T10:00:00Z",
    "end": "2024-03-25T10:30:00Z",
    "serviceType": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/service-type",
                    "code": "124",
                    "display": "General Practice",
                }
            ]
        }
    ],
}

PRACTITIONER_GENERAL: Dict[str, Any] = {
    "resourceType": "Practitioner",
    "id": "practitioner-general",
    "identifier": [
        {
            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
            "value": "98765432100",
        },
        {
            "system": "http://www.saude.gov.br/fhir/r4/NamingSystem/crm",
            "value": "CRM/SP 123456",
        },
    ],
    "name": [
        {
            "use": "official",
            "family": "Santos",
            "given": ["Maria", "Clara"],
            "prefix": ["Dr."],
        }
    ],
    "telecom": [
        {
            "system": "phone",
            "value": "+5511888999777",
            "use": "work",
        },
        {
            "system": "email",
            "value": "dra.maria.santos@austa.com.br",
            "use": "work",
        },
    ],
    "qualification": [
        {
            "code": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0360",
                        "code": "MD",
                        "display": "Medical Doctor",
                    }
                ],
                "text": "Médica - Clínica Geral",
            },
            "issuer": {"display": "Conselho Regional de Medicina de São Paulo"},
        }
    ],
}
