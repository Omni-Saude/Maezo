#!/usr/bin/env python3
"""Inicia uma instância do processo SP-RC-002 no CIB Seven com dados FHIR de teste.

Uso:
    python scripts/start_rc002_instance.py
"""
import json
import httpx

CIB7_URL = "http://localhost:8085/engine-rest"

payload = {
    "variables": {
        "payerId": {"value": "UNIMED", "type": "String"},
        "cdEstabelecimento": {"value": 4, "type": "Integer"},
        "authorizationType": {"value": "consulta", "type": "String"},
        "carteirinha": {"value": "00301507000072309", "type": "String"},
        "cdConvenio": {"value": 1, "type": "Integer"},
        "dsConvenio": {"value": "Unimed", "type": "String"},
        "cdPrestador": {"value": "110020", "type": "String"},
        "nrCrm": {"value": "135677", "type": "String"},
        "nrAtendimento": {"value": 329152, "type": "Integer"},
        "nrSequencia": {"value": 341470, "type": "Integer"},
        "dtEntrada": {"value": "2024-01-01", "type": "String"},
        "dsCaraterAtendimento": {"value": "Urgência/Emergência", "type": "String"},
        "ieConsultaEmergencia": {"value": "S", "type": "String"},
        "ieTipoConsulta": {"value": "Primeira consulta", "type": "String"},
        "ieTipoAtendimento": {"value": "Consulta", "type": "String"},
        "ieRegimeAtendimento": {"value": "Pronto Socorro", "type": "String"},
        "tpAcidente": {"value": "Não acidente", "type": "String"},
        "dsIndClinica": {"value": "", "type": "String"},
        "dsObservacao": {"value": "", "type": "String"},
        "cdAusenciaValBenef": {"value": "", "type": "String"},
        "enrichedProcedures": {
            "value": json.dumps([{"code": "0", "display": "", "quantity": 1, "category": ""}]),
            "type": "String",
        },
        "diagnosisCodes": {
            "value": json.dumps([""]),
            "type": "String",
        },
    },
    "businessKey": "teste-homolog-341470",
}

print("Iniciando instância SP_RC_002_Pre_Service no CIB Seven...")
print(f"  CIB Seven URL: {CIB7_URL}")
print(f"  Business Key : {payload['businessKey']}")
print(f"  payerId      : UNIMED")
print(f"  nrSequencia  : 341470")
print(f"  nrAtendimento: 329152")

resp = httpx.post(
    f"{CIB7_URL}/process-definition/key/SP_RC_002_Pre_Service/tenant-id/Maezo_rc/start",
    json=payload,
    auth=("admin", "admin"),
    timeout=10,
)

if resp.status_code == 200:
    data = resp.json()
    print(f"\n  Instância criada com sucesso!")
    print(f"  process_instance_id: {data['id']}")
    print(f"  definition_id      : {data['definitionId']}")
    print(f"\n  Cockpit: http://localhost:8085/camunda/app/cockpit/default/#/process-instance/{data['id']}")
else:
    print(f"\n  ERRO {resp.status_code}: {resp.text}")
