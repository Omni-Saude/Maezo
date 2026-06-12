#!/usr/bin/env python3
"""
MAEZO — Seed de dados FHIR stub para ambiente de desenvolvimento.

Carrega recursos FHIR minimos no HAPI FHIR R4 via REST API.
Usa PUT com IDs fixos para garantir idempotencia (rodar N vezes = mesmo resultado).

Uso:
  python3 scripts/dev/seed_fhir_data.py                              # localhost
  python3 scripts/dev/seed_fhir_data.py --url http://192.168.1.100:8082/fhir
"""

import argparse
import json
import sys
import time

try:
    import httpx
except ImportError:
    print("httpx nao instalado. Execute: pip install httpx")
    sys.exit(1)

# -- Cores -------------------------------------------------------------------
GREEN = "\033[0;32m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
NC = "\033[0m"


def ok(msg):
    print(f"{GREEN}  ok{NC} {msg}")


def err(msg):
    print(f"{RED}  FAIL{NC} {msg}")


def log(msg):
    print(f"{BLUE}[seed]{NC} {msg}")


# -- Recursos FHIR ----------------------------------------------------------

ORGANIZATION = {
    "resourceType": "Organization",
    "id": "org-austa",
    "identifier": [
        {
            "system": "http://www.saude.gov.br/fhir/r4/NamingSystem/cnes",
            "value": "1234567",
        }
    ],
    "active": True,
    "name": "Hospital Austa - Sao Jose do Rio Preto",
    "type": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/organization-type",
                    "code": "prov",
                    "display": "Healthcare Provider",
                }
            ]
        }
    ],
    "address": [
        {
            "line": ["Av. Brigadeiro Faria Lima, 5544"],
            "city": "Sao Jose do Rio Preto",
            "state": "SP",
            "postalCode": "15090-000",
            "country": "BR",
        }
    ],
}

PRACTITIONERS = [
    {
        "resourceType": "Practitioner",
        "id": "pract-medico-001",
        "identifier": [
            {
                "system": "http://www.saude.gov.br/fhir/r4/NamingSystem/crm",
                "value": "CRM-SP-123456",
            }
        ],
        "active": True,
        "name": [{"family": "Santos", "given": ["Roberto", "Carlos"]}],
        "qualification": [
            {
                "code": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0360",
                            "code": "MD",
                            "display": "Doctor of Medicine",
                        }
                    ]
                }
            }
        ],
    },
    {
        "resourceType": "Practitioner",
        "id": "pract-enfermeiro-001",
        "identifier": [
            {
                "system": "http://www.saude.gov.br/fhir/r4/NamingSystem/coren",
                "value": "COREN-SP-654321",
            }
        ],
        "active": True,
        "name": [{"family": "Oliveira", "given": ["Ana", "Paula"]}],
        "qualification": [
            {
                "code": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0360",
                            "code": "RN",
                            "display": "Registered Nurse",
                        }
                    ]
                }
            }
        ],
    },
    {
        "resourceType": "Practitioner",
        "id": "pract-admin-001",
        "active": True,
        "name": [{"family": "Lima", "given": ["Marcos"]}],
    },
]

PATIENTS = [
    {
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
        "name": [{"use": "official", "family": "Silva", "given": ["Joao", "Pedro"]}],
        "gender": "male",
        "birthDate": "1980-05-15",
        "telecom": [
            {"system": "phone", "value": "+5511987654321", "use": "mobile"},
            {"system": "email", "value": "joao.silva@email.com"},
        ],
        "address": [
            {
                "use": "home",
                "line": ["Rua das Flores, 123"],
                "city": "Sao Paulo",
                "state": "SP",
                "postalCode": "01234-567",
                "country": "BR",
            }
        ],
        "managingOrganization": {"reference": "Organization/org-austa"},
    },
    {
        "resourceType": "Patient",
        "id": "patient-pediatric-001",
        "identifier": [
            {
                "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
                "value": "55566677788",
            }
        ],
        "name": [{"use": "official", "family": "Costa", "given": ["Ana", "Julia"]}],
        "gender": "female",
        "birthDate": "2018-04-12",
        "managingOrganization": {"reference": "Organization/org-austa"},
    },
    {
        "resourceType": "Patient",
        "id": "patient-geriatric-001",
        "identifier": [
            {
                "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
                "value": "77788899900",
            }
        ],
        "name": [
            {"use": "official", "family": "Ferreira", "given": ["Jose", "Antonio"]}
        ],
        "gender": "male",
        "birthDate": "1945-02-28",
        "managingOrganization": {"reference": "Organization/org-austa"},
    },
    {
        "resourceType": "Patient",
        "id": "patient-cns-001",
        "identifier": [
            {
                "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
                "value": "11122233344",
            },
            {
                "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns",
                "value": "123456789012345",
            },
        ],
        "name": [
            {"use": "official", "family": "Oliveira", "given": ["Carlos", "Eduardo"]}
        ],
        "gender": "male",
        "birthDate": "1975-08-10",
        "managingOrganization": {"reference": "Organization/org-austa"},
    },
    {
        "resourceType": "Patient",
        "id": "patient-foreign-001",
        "identifier": [
            {
                "system": "http://austa.com.br/fhir/identifier/passport",
                "value": "AB123456",
            }
        ],
        "name": [{"use": "official", "family": "Gonzalez", "given": ["Roberto"]}],
        "gender": "male",
        "birthDate": "1985-11-22",
        "managingOrganization": {"reference": "Organization/org-austa"},
    },
]

COVERAGES = [
    {
        "resourceType": "Coverage",
        "id": "coverage-bradesco-001",
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "HIP",
                    "display": "health insurance plan policy",
                }
            ]
        },
        "subscriber": {"reference": "Patient/patient-valid-001"},
        "beneficiary": {"reference": "Patient/patient-valid-001"},
        "payor": [{"display": "Bradesco Saude"}],
        "class": [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/coverage-class",
                            "code": "plan",
                        }
                    ]
                },
                "value": "BRADESCO-ENFERMARIA",
                "name": "Bradesco Saude Enfermaria",
            }
        ],
    },
    {
        "resourceType": "Coverage",
        "id": "coverage-sus-001",
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "PUBLICPOL",
                    "display": "public healthcare",
                }
            ]
        },
        "subscriber": {"reference": "Patient/patient-cns-001"},
        "beneficiary": {"reference": "Patient/patient-cns-001"},
        "payor": [{"display": "SUS - Sistema Unico de Saude"}],
    },
]

ENCOUNTERS = [
    {
        "resourceType": "Encounter",
        "id": "encounter-internacao-001",
        "status": "in-progress",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "IMP",
            "display": "inpatient encounter",
        },
        "type": [
            {
                "coding": [
                    {
                        "system": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRTipoAtendimento",
                        "code": "01",
                        "display": "Internacao",
                    }
                ]
            }
        ],
        "subject": {"reference": "Patient/patient-valid-001"},
        "participant": [
            {
                "individual": {"reference": "Practitioner/pract-medico-001"},
            }
        ],
        "period": {"start": "2026-03-01T08:00:00-03:00"},
        "serviceProvider": {"reference": "Organization/org-austa"},
    },
    {
        "resourceType": "Encounter",
        "id": "encounter-ambulatorio-001",
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB",
            "display": "ambulatory",
        },
        "subject": {"reference": "Patient/patient-geriatric-001"},
        "participant": [
            {
                "individual": {"reference": "Practitioner/pract-medico-001"},
            }
        ],
        "period": {
            "start": "2026-03-03T10:00:00-03:00",
            "end": "2026-03-03T10:30:00-03:00",
        },
        "serviceProvider": {"reference": "Organization/org-austa"},
    },
]

CLAIMS = [
    {
        "resourceType": "Claim",
        "id": "claim-internacao-001",
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "institutional",
                }
            ]
        },
        "use": "claim",
        "patient": {"reference": "Patient/patient-valid-001"},
        "created": "2026-03-05",
        "provider": {"reference": "Organization/org-austa"},
        "priority": {"coding": [{"code": "normal"}]},
        "insurance": [
            {
                "sequence": 1,
                "focal": True,
                "coverage": {"reference": "Coverage/coverage-bradesco-001"},
            }
        ],
        "item": [
            {
                "sequence": 1,
                "productOrService": {
                    "coding": [
                        {
                            "system": "http://www.ans.gov.br/tiss/procedimentos",
                            "code": "10101012",
                            "display": "Consulta medica em consultorio",
                        }
                    ]
                },
                "quantity": {"value": 1},
                "unitPrice": {"value": 150.00, "currency": "BRL"},
            }
        ],
        "total": {"value": 150.00, "currency": "BRL"},
    },
    {
        "resourceType": "Claim",
        "id": "claim-sus-001",
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "institutional",
                }
            ]
        },
        "use": "claim",
        "patient": {"reference": "Patient/patient-cns-001"},
        "created": "2026-03-05",
        "provider": {"reference": "Organization/org-austa"},
        "priority": {"coding": [{"code": "normal"}]},
        "insurance": [
            {
                "sequence": 1,
                "focal": True,
                "coverage": {"reference": "Coverage/coverage-sus-001"},
            }
        ],
        "item": [
            {
                "sequence": 1,
                "productOrService": {
                    "coding": [
                        {
                            "system": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRProcedimentosSIGTAP",
                            "code": "0301010064",
                            "display": "Consulta medica em atencao basica",
                        }
                    ]
                },
                "quantity": {"value": 1},
                "unitPrice": {"value": 10.00, "currency": "BRL"},
            }
        ],
        "total": {"value": 10.00, "currency": "BRL"},
    },
]


def seed_resource(client: httpx.Client, resource: dict) -> bool:
    """PUT um recurso FHIR (idempotente)."""
    rtype = resource["resourceType"]
    rid = resource["id"]
    url = f"{client.base_url}/{rtype}/{rid}"

    try:
        resp = client.put(
            f"/{rtype}/{rid}",
            json=resource,
        )
        if resp.status_code in (200, 201):
            ok(f"{rtype}/{rid}")
            return True
        else:
            err(f"{rtype}/{rid} — HTTP {resp.status_code}: {resp.text[:200]}")
            return False
    except httpx.ConnectError:
        err(f"{rtype}/{rid} — conexao recusada")
        return False


def wait_for_fhir(client: httpx.Client, timeout: int = 120) -> bool:
    """Aguarda HAPI FHIR responder (distroless sem healthcheck)."""
    log(f"Aguardando HAPI FHIR ficar pronto (timeout {timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = client.get("/metadata")
            if resp.status_code == 200:
                ok("HAPI FHIR pronto")
                return True
        except (httpx.ConnectError, httpx.ReadTimeout):
            pass
        time.sleep(3)
        print(".", end="", flush=True)
    print()
    err(f"HAPI FHIR nao respondeu em {timeout}s")
    return False


def main():
    parser = argparse.ArgumentParser(description="Seed FHIR stub data")
    parser.add_argument(
        "--url", default="http://localhost:8082/fhir", help="HAPI FHIR base URL"
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Nao aguardar HAPI FHIR (assume que ja esta pronto)",
    )
    args = parser.parse_args()

    client = httpx.Client(
        base_url=args.url,
        headers={"Content-Type": "application/fhir+json"},
        timeout=30.0,
    )

    if not args.no_wait:
        if not wait_for_fhir(client):
            sys.exit(1)

    log("Carregando recursos FHIR stub...")

    total = 0
    success = 0

    # Ordem importa: Organization primeiro (referenciado por outros)
    all_resources = (
        [ORGANIZATION] + PRACTITIONERS + PATIENTS + COVERAGES + ENCOUNTERS + CLAIMS
    )

    for resource in all_resources:
        total += 1
        if seed_resource(client, resource):
            success += 1

    print()
    if success == total:
        log(f"Seed completo: {success}/{total} recursos carregados")
    else:
        log(f"Seed parcial: {success}/{total} recursos ({total - success} falharam)")
        sys.exit(1)


if __name__ == "__main__":
    main()
