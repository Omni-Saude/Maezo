"""Patient FHIR resource fixtures para testes."""

from typing import Dict, Any


PATIENT_VALID: Dict[str, Any] = {
    "resourceType": "Patient",
    "id": "patient-valid-001",
    "identifier": [
        {
            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
            "value": "12345678901",
        },
        {
            "system": "http://austa.com.br/fhir/identifier/mrn",
            "value": "MRN-123456",
        },
    ],
    "name": [
        {
            "use": "official",
            "family": "Silva",
            "given": ["João", "Pedro"],
        }
    ],
    "gender": "male",
    "birthDate": "1980-05-15",
    "telecom": [
        {
            "system": "phone",
            "value": "+5511987654321",
            "use": "mobile",
        },
        {
            "system": "email",
            "value": "joao.silva@email.com",
        },
    ],
    "address": [
        {
            "use": "home",
            "line": ["Rua das Flores, 123"],
            "city": "São Paulo",
            "state": "SP",
            "postalCode": "01234-567",
            "country": "BR",
        }
    ],
}

PATIENT_INVALID_CPF: Dict[str, Any] = {
    "resourceType": "Patient",
    "id": "patient-invalid-cpf",
    "identifier": [
        {
            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
            "value": "00000000000",  # CPF inválido
        },
    ],
    "name": [
        {
            "use": "official",
            "family": "Santos",
            "given": ["Maria"],
        }
    ],
    "gender": "female",
    "birthDate": "1990-03-20",
}

PATIENT_MISSING_FIELDS: Dict[str, Any] = {
    "resourceType": "Patient",
    "id": "patient-missing-fields",
    "identifier": [
        {
            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
            "value": "98765432100",
        },
    ],
    # Falta: name, gender, birthDate
}

PATIENT_WITH_CNS: Dict[str, Any] = {
    "resourceType": "Patient",
    "id": "patient-with-cns",
    "identifier": [
        {
            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
            "value": "11122233344",
        },
        {
            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns",
            "value": "123456789012345",  # CNS (Cartão Nacional de Saúde)
        },
    ],
    "name": [
        {
            "use": "official",
            "family": "Oliveira",
            "given": ["Carlos", "Eduardo"],
        }
    ],
    "gender": "male",
    "birthDate": "1975-08-10",
    "telecom": [
        {
            "system": "phone",
            "value": "+5511999887766",
            "use": "mobile",
        }
    ],
}

PATIENT_PEDIATRIC: Dict[str, Any] = {
    "resourceType": "Patient",
    "id": "patient-pediatric",
    "identifier": [
        {
            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
            "value": "55566677788",
        },
    ],
    "name": [
        {
            "use": "official",
            "family": "Costa",
            "given": ["Ana", "Júlia"],
        }
    ],
    "gender": "female",
    "birthDate": "2018-04-12",  # 6 anos de idade
    "contact": [
        {
            "relationship": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0131",
                            "code": "MTH",
                            "display": "Mother",
                        }
                    ]
                }
            ],
            "name": {
                "use": "official",
                "family": "Costa",
                "given": ["Mariana"],
            },
            "telecom": [
                {
                    "system": "phone",
                    "value": "+5511888777666",
                    "use": "mobile",
                }
            ],
        }
    ],
}

PATIENT_GERIATRIC: Dict[str, Any] = {
    "resourceType": "Patient",
    "id": "patient-geriatric",
    "identifier": [
        {
            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
            "value": "77788899900",
        },
    ],
    "name": [
        {
            "use": "official",
            "family": "Ferreira",
            "given": ["José", "Antônio"],
        }
    ],
    "gender": "male",
    "birthDate": "1945-02-28",  # 79 anos
    "telecom": [
        {
            "system": "phone",
            "value": "+5511777666555",
            "use": "home",
        }
    ],
    "address": [
        {
            "use": "home",
            "line": ["Rua dos Idosos, 456"],
            "city": "São Paulo",
            "state": "SP",
            "postalCode": "04567-890",
            "country": "BR",
        }
    ],
}

PATIENT_NEWBORN: Dict[str, Any] = {
    "resourceType": "Patient",
    "id": "patient-newborn",
    "identifier": [
        {
            "system": "http://austa.com.br/fhir/identifier/mrn",
            "value": "MRN-NEWBORN-001",
        },
    ],
    "name": [
        {
            "use": "official",
            "family": "Souza",
            "given": ["Recém-Nascido"],
        }
    ],
    "gender": "female",
    "birthDate": "2024-03-10",  # Nascimento recente
    "contact": [
        {
            "relationship": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0131",
                            "code": "MTH",
                            "display": "Mother",
                        }
                    ]
                }
            ],
            "name": {
                "use": "official",
                "family": "Souza",
                "given": ["Patrícia"],
            },
        }
    ],
}

PATIENT_FOREIGN: Dict[str, Any] = {
    "resourceType": "Patient",
    "id": "patient-foreign",
    "identifier": [
        {
            "system": "http://austa.com.br/fhir/identifier/passport",
            "value": "AB123456",
        },
    ],
    "name": [
        {
            "use": "official",
            "family": "Gonzalez",
            "given": ["Roberto"],
        }
    ],
    "gender": "male",
    "birthDate": "1985-11-22",
    "telecom": [
        {
            "system": "phone",
            "value": "+543412345678",  # Número argentino
            "use": "mobile",
        }
    ],
    "address": [
        {
            "use": "temp",
            "line": ["Hotel Brasil, Quarto 301"],
            "city": "São Paulo",
            "state": "SP",
            "postalCode": "01310-100",
            "country": "BR",
        }
    ],
}
