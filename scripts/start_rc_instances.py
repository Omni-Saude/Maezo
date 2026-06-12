"""Inicia 10 instancias RC com cenarios distintos para smoke test dos workers."""
import requests
import uuid
import time
import sys
from requests.auth import HTTPBasicAuth

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE   = "http://localhost:8085/engine-rest"
auth   = HTTPBasicAuth("admin", "admin")
TENANT = "Maezo_rc"


def start(key, variables, label):
    payload = {
        "variables": {
            k: {"value": v, "type": "String"}
            for k, v in variables.items()
        }
    }
    r = requests.post(
        f"{BASE}/process-definition/key/{key}/tenant-id/{TENANT}/start",
        json=payload, auth=auth, timeout=15,
    )
    if r.status_code == 200:
        inst_id = r.json()["id"]
        print(f"  OK  [{label}] {key} -> {inst_id[:8]}...")
        return inst_id
    else:
        print(f"  ERR [{label}] {key} -> HTTP {r.status_code}: {r.text[:150]}")
        return None


print("\n-- Iniciando 10 instancias RC ------------------------------------------")

instances = []

# 1. SP_RC_003 - Atendimento Clinico (happy path, UNIMED)
i = start("SP_RC_003_Clinical_Service", {
    "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
    "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
    "payerId":     "UNIMED-SP",
    "procedureCode": "10101012",
}, "RC-003 Happy Path / UNIMED")
if i: instances.append((i, "SP_RC_003_Clinical_Service"))

# 2. SP_RC_003 - Atendimento Clinico (AMIL, procedimento complexo)
i = start("SP_RC_003_Clinical_Service", {
    "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
    "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
    "payerId":     "AMIL",
    "procedureCode": "30722018",
}, "RC-003 Proc Complexo / AMIL")
if i: instances.append((i, "SP_RC_003_Clinical_Service"))

# 3. SP_RC_003 - Urgencia / BRADESCO
i = start("SP_RC_003_Clinical_Service", {
    "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
    "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
    "payerId":     "BRADESCO",
    "procedureCode": "31309016",
    "priority":    "URGENT",
}, "RC-003 Urgencia / BRADESCO")
if i: instances.append((i, "SP_RC_003_Clinical_Service"))

# 4. SP_RC_004 - Producao Clinica (cirurgia eletiva)
i = start("SP_RC_004_Clinical_Production", {
    "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
    "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
    "procedureCode": "31309016",
    "quantity":    "1",
    "specialty":   "ORTOPEDIA",
}, "RC-004 Producao / Cirurgia Eletiva")
if i: instances.append((i, "SP_RC_004_Clinical_Production"))

# 5. SP_RC_004 - Producao Clinica (exames laboratoriais)
i = start("SP_RC_004_Clinical_Production", {
    "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
    "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
    "procedureCode": "40304361",
    "quantity":    "3",
    "specialty":   "PATOLOGIA_CLINICA",
}, "RC-004 Producao / Exames Lab")
if i: instances.append((i, "SP_RC_004_Clinical_Production"))

# 6. SP_RC_005 - Codificacao e Auditoria (suspeita upcoding)
i = start("SP_RC_005_Coding_Audit", {
    "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
    "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
    "rawCodes":    "10101012,30722018",
    "diagnosisCodes": "J18.9,Z00.0",
    "payerId":     "SULAMERICA",
}, "RC-005 Audit / Upcoding Suspeito")
if i: instances.append((i, "SP_RC_005_Coding_Audit"))

# 7. SP_RC_005 - Codificacao (OPME, alta complexidade)
i = start("SP_RC_005_Coding_Audit", {
    "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
    "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
    "rawCodes":    "31309016,10101012,40304361",
    "diagnosisCodes": "M16.1",
    "payerId":     "NOTREDAME",
    "hasOPME":     "true",
}, "RC-005 Audit / OPME Alta Complexidade")
if i: instances.append((i, "SP_RC_005_Coding_Audit"))

# 8. SP_RC_007 - Glosa administrativa / UNIMED
i = start("SP_RC_007_Denial_Management", {
    "batchId":      f"BATCH-{uuid.uuid4().hex[:8]}",
    "payerResponse": '{"status":"denied","reason":"GLOSA-001","value":1250.00}',
    "payerId":      "UNIMED-SP",
    "glosaType":    "ADMINISTRATIVA",
}, "RC-007 Glosa Admin / UNIMED")
if i: instances.append((i, "SP_RC_007_Denial_Management"))

# 9. SP_RC_007 - Glosa tecnica / AMIL (alto valor)
i = start("SP_RC_007_Denial_Management", {
    "batchId":      f"BATCH-{uuid.uuid4().hex[:8]}",
    "payerResponse": '{"status":"denied","reason":"GLOSA-008","value":8900.00}',
    "payerId":      "AMIL",
    "glosaType":    "TECNICA",
    "appealDeadlineDays": "15",
}, "RC-007 Glosa Tecnica / AMIL (alto valor)")
if i: instances.append((i, "SP_RC_007_Denial_Management"))

# 10. SP_RC_006 - Faturamento SADT / BRADESCO
i = start("SP_RC_006_Billing_Submission", {
    "encounterId":  f"ENC-{uuid.uuid4().hex[:8]}",
    "patientId":    f"PAT-{uuid.uuid4().hex[:8]}",
    "payerId":      "BRADESCO",
    "guideType":    "SADT",
    "totalValue":   "3400.00",
    "procedureCodes": "10101012,40304361",
}, "RC-006 Billing / SADT BRADESCO")
if i: instances.append((i, "SP_RC_006_Billing_Submission"))

print(f"\n-- {len(instances)}/10 instancias iniciadas. Aguardando 8s para workers processarem...")
time.sleep(8)

# Verificar estado das instancias
print("\n-- Estado das instancias -----------------------------------------------")
header = f"{'ESTADO':<12} {'PROCESSO':<35} {'INSTANCIA'}"
print(header)
print("-" * 75)
for iid, key in instances:
    r = requests.get(f"{BASE}/history/process-instance/{iid}", auth=auth, timeout=10)
    if r.status_code == 200:
        d = r.json()
        state = d.get("state", "?")
        short_key = key.replace("SP_RC_00", "RC-00")
        print(f"{state:<12} {short_key:<35} {iid[:12]}...")
    else:
        print(f"{'ERRO':<12} {key:<35} {iid[:12]}...")

# Contar por estado
print("\n-- Resumo --------------------------------------------------------------")
states = {}
for iid, _ in instances:
    r = requests.get(f"{BASE}/history/process-instance/{iid}", auth=auth, timeout=10)
    if r.status_code == 200:
        s = r.json().get("state", "UNKNOWN")
        states[s] = states.get(s, 0) + 1
for s, n in sorted(states.items()):
    print(f"  {s}: {n}")

# Contar tarefas processadas pelo worker mock
r = requests.get(f"{BASE}/history/external-task-log", params={"type": "complete", "maxResults": 200}, auth=auth, timeout=10)
if r.status_code == 200:
    logs = r.json()
    print(f"\n  Tasks completadas pelo worker (historico recente): {len(logs)}")
