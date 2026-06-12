"""
load_test_rc.py — Gerador de carga para o dominio Revenue Cycle.

Estrategia:
  1. Le BPMNs e extrai topic -> variaveis de saida necessarias
  2. Inicia N instancias em paralelo em varios processos RC
  3. Roda threads de worker que fazem fetchAndLock + complete em TODOS os topicos
     com variaveis mock validas (satisfazendo os I/O mappings dos BPMNs)
  4. workers_rc real compete pelos topicos que ele assina (51 topicos)
  5. Relatorio em tempo real de throughput e latencia

Uso:
    python scripts/load_test_rc.py --instances 100 --workers 15 --duration 120
"""
import sys
import re
import time
import uuid
import threading
import argparse
import random
import json
from pathlib import Path
from collections import defaultdict
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE   = "http://localhost:8085/engine-rest"
AUTH   = HTTPBasicAuth("admin", "admin")
TENANT = "Maezo_rc"

GREEN  = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE   = "\033[0;34m"
RED    = "\033[0;31m"
CYAN   = "\033[0;36m"
NC     = "\033[0m"

# ---------------------------------------------------------------------------
# BPMN parsing — topic -> lista de variaveis necessarias no complete
# ---------------------------------------------------------------------------
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CAM_NS  = "http://camunda.org/schema/1.0/bpmn"


def parse_topic_output_vars(bpmn_dir: Path) -> dict[str, list[str]]:
    """Le todos os BPMNs e retorna {topic: [source_var_names]}."""
    result: dict[str, set] = {}
    for f in sorted(bpmn_dir.glob("*.bpmn")):
        try:
            tree = ET.parse(f)
        except Exception:
            continue
        for task in tree.getroot().iter(f"{{{BPMN_NS}}}serviceTask"):
            topic = task.get(f"{{{CAM_NS}}}topic")
            if not topic:
                continue
            if topic not in result:
                result[topic] = set()
            for op in task.findall(f".//{{{CAM_NS}}}outputParameter"):
                expr = (op.text or "").strip()
                result[topic].update(re.findall(r"\$\{(\w+)\}", expr))
    return {t: sorted(v) for t, v in result.items()}


# ---------------------------------------------------------------------------
# Mock value generator — produz valores realistas para cada variavel
# ---------------------------------------------------------------------------

_MOCK_STRINGS = {
    # authorizacao
    "authType":              "prior_auth",
    "requiresAuth":          "true",
    "authorizationNumber":   lambda: f"AUTH-{uuid.uuid4().hex[:8].upper()}",
    "authStatus":            "APPROVED",
    "authorizationStatus":   "APPROVED",
    "authNumber":            lambda: f"AUTH-{uuid.uuid4().hex[:6].upper()}",
    "authorizationRequired": "true",
    "authorizationType":     "prior_auth",
    "tasyUpdated":           "true",
    "validationStatus":      "OK",
    # procedimentos
    "capturedData":       lambda: json.dumps({"procedures": ["10101012"], "diagnoses": ["J18.9"]}),
    "captureTimestamp":   "2026-03-18T10:00:00Z",
    "enrichedData":       lambda: json.dumps({"enriched": True, "complete": True}),
    "diagnosisCodes":     "J18.9",
    "procedureCodes":     "10101012",
    "docComplete":        "true",
    "quantities":         lambda: json.dumps({"10101012": 1}),
    "units":              "UN",
    "validationResult":   "true",
    "validationErrors":   "",
    # producao
    "pricedProcedures":         lambda: json.dumps([{"code": "10101012", "value": 500.0}]),
    "totalValue":               "1500.00",
    "breakdown":                lambda: json.dumps({"labor": 300, "material": 200}),
    "productionId":             lambda: f"PROD-{uuid.uuid4().hex[:8].upper()}",
    "compatibilityResult":      "COMPATIBLE",
    "incompatibleItems":        "[]",
    "incompatibilities":        "[]",
    # coding
    "auditResult":          "APPROVED",
    "auditFindings":        lambda: json.dumps({"issues": []}),
    "fraudScore":           "0.05",
    "fraudIndicators":      "[]",
    "suggestedCodes":       lambda: json.dumps(["J18.9", "Z00.0"]),
    "suggestedProcedures":  lambda: json.dumps(["10101012", "30722018"]),
    "confidence":           "0.92",
    "extractedData":        lambda: json.dumps({"diagnosis": "J18.9", "procedures": ["10101012"]}),
    # billing
    "totalCharges":         "2500.00",
    "chargeBreakdown":      lambda: json.dumps({"procedure": 1500, "material": 1000}),
    "adjustedCharges":      lambda: json.dumps([{"code": "10101012", "value": 1500}]),
    "tissXml":              "<TISSXML><header/></TISSXML>",
    "submissionId":         lambda: f"TISS-{uuid.uuid4().hex[:8].upper()}",
    "submissionStatus":     "SENT",
    "schemaValid":          "true",
    "schemaErrors":         "[]",
    # glosa / recurso
    "glosaItems":       lambda: json.dumps([{"code": "10101012", "value": 500.0, "reason": "GLOSA-001"}]),
    "glosaCount":       "1",
    "classifiedGlosas": lambda: json.dumps([{"code": "10101012", "type": "ADMINISTRATIVA"}]),
    "primaryType":      "ADMINISTRATIVA",
    "rootCause":        "DOCUMENTACAO_INCOMPLETA",
    "analysisDetails":  "Documentacao insuficiente",
    "riskScore":        "0.3",
    "riskCategory":     "LOW",
    "preventionActions": lambda: json.dumps(["verificar_documentacao"]),
    "isEligible":       "true",
    "eligibilityReason": "Dentro do prazo",
    "appealEligible":   "true",
    "collectedData":    lambda: json.dumps({"docs": ["laudo.pdf"]}),
    "recoveryPlan":     lambda: json.dumps({"strategy": "RECURSO_ADMINISTRATIVO"}),
    "recoveryEligibility": lambda: json.dumps({"eligible": True}),
    "appealDocuments":  lambda: json.dumps(["laudo.pdf", "recurso.pdf"]),
    "appealPackage":    lambda: json.dumps({"complete": True}),
    "appealId":         lambda: f"APPEAL-{uuid.uuid4().hex[:8].upper()}",
    "submissionDate":   "2026-03-18",
    "currentStatus":    "APPROVED",
    "payerResponse":    lambda: json.dumps({"received": True, "status": "APPROVED"}),
    "appealStatus":     "APPROVED",
    # collection
    "payments":           lambda: json.dumps([{"id": "PAY-001", "value": 1500.0}]),
    "paymentCount":       "1",
    "paymentDate":        "2026-03-18",
    "matches":            lambda: json.dumps([{"paymentId": "PAY-001", "invoiceId": "NF-001"}]),
    "autoMatched":        "true",
    "pendingMatching":    "false",
    "confidence":         "0.95",
    "invoiceMatches":     lambda: json.dumps([{"invoiceId": "NF-001"}]),
    "patientMatches":     lambda: json.dumps([{"patientId": "PAT-001"}]),
    "protocolMatches":    lambda: json.dumps([{"protocolId": "PROT-001"}]),
    "netPaymentAmounts":  lambda: json.dumps({"NF-001": 1500.0}),
    "paymentVariance":    "0.00",
    "net":                "1500.00",
    "amount":             "1500.00",
    "adjusted":           "true",
    "adjustmentAmount":   "150.00",
    "adjustmentDetails":  lambda: json.dumps({"type": "contractual", "rate": 0.1}),
    "adjustmentsApplied": "true",
    "contractualAdjusted": "true",
    "totalAdjustments":   "150.00",
    "flaggedDiscrepancies": lambda: json.dumps([]),
    "discrepancy":        "false",
    "totalDiscrepancies": "0",
    "type":               "CREDIT",
    "duplicate":          "false",
    "duplicates":         "[]",
    "duplicatePayments":  "[]",
    "uniquePayments":     lambda: json.dumps([{"id": "PAY-001"}]),
    "reconciliationArchiveId": lambda: f"REC-{uuid.uuid4().hex[:8].upper()}",
    "saved":              "true",
    "success":            "true",
    "id":                 lambda: f"PAY-{uuid.uuid4().hex[:8].upper()}",
    "paymentIdentifiers": lambda: json.dumps([f"PAY-{uuid.uuid4().hex[:6].upper()}"]),
    "savedPayments":      "1",
    "classifiedPayments": lambda: json.dumps([{"id": "PAY-001", "type": "CREDIT"}]),
    "method":             "CREDIT_CARD",
    "paymentTypeBreakdown": lambda: json.dumps({"CREDIT": 1}),
    "currencyConverted":  "true",
    "collectionRate":     "0.85",
    "collectionTrend":    "IMPROVING",
    "rateByPayer":        lambda: json.dumps({"UNIMED": 0.9}),
    "dsoValue":           "45",
    "dsoTrend":           "STABLE",
    "cycleTimeByStage":   lambda: json.dumps({"billing": 5, "collection": 30}),
    "avgCycleTimeDays":   "35",
    "varianceAmount":     "50.00",
    "variancePercentage": "3.3",
    "leakageAmount":      "200.00",
    "leakageSources":     lambda: json.dumps(["underpayment"]),
    "leakagePoints":      lambda: json.dumps(["charge_entry"]),
    "penaltiesApplied":   "true",
    "penaltyAmount":      "150.00",
    "overpaymentProcessed": "true",
    "refund":             "false",
    "creditAmount":       "0.00",
    "status":             "PROCESSED",
    "underpaymentProcessed": "true",
    "outstandingAmount":  "100.00",
    "agingBucket":        "30-60",
    "daysOverdue":        "45",
    "prioritizedAccounts": lambda: json.dumps([{"id": "ACC-001", "priority": 1}]),
    "priority":           "HIGH",
    "highPriorityCount":  "1",
    "collectionStrategy": "STANDARD",
    "priorityList":       lambda: json.dumps([{"id": "ACC-001"}]),
    "callScheduled":      "true",
    "callTime":           "2026-03-19T09:00:00Z",
    "scheduled":          "true",
    "scheduledDateTime":  "2026-03-19T09:00:00Z",
    "letter":             "Prezado cliente...",
    "letterGenerated":    "true",
    "letterPath":         "/tmp/collection_letter.pdf",
    "sent":               "true",
    "dashboardUrl":       "http://grafana/d/rc-dashboard",
    "reportGenerated":    "true",
    "negotiated":         "true",
    "paymentPlansCreated": "1",
    "planId":             lambda: f"PLAN-{uuid.uuid4().hex[:6].upper()}",
    "negotiationResults": lambda: json.dumps({"agreed": True, "installments": 3}),
    "caseId":             lambda: f"CASE-{uuid.uuid4().hex[:6].upper()}",
    "caseNumber":         lambda: f"CASE-{uuid.uuid4().hex[:6].upper()}",
    "legalCaseCreated":   "true",
    "legalResult":        "PENDING",
    "escalated":          "true",
    "escalationTicket":   lambda: f"TKT-{uuid.uuid4().hex[:6].upper()}",
    "biUpdated":          "true",
    "updateTimestamp":    "2026-03-18T23:59:00Z",
    "forecastsUpdated":   "true",
    "projectedRevenue":   "150000.00",
    "weeklyReconciliation": lambda: json.dumps({"total": 15000, "matched": 14500}),
    "weeklyTotalAmount":  "15000.00",
    "monthlyReconciliation": lambda: json.dumps({"total": 60000, "matched": 58000}),
    "monthlyTotalAmount": "60000.00",
    "report":             lambda: json.dumps({"generated": True}),
    "total":              "60000.00",
    "summarySent":        "true",
    "sentDateTime":       "2026-03-18T08:00:00Z",
    "messageSent":        "true",
    "messageId":          lambda: f"MSG-{uuid.uuid4().hex[:6].upper()}",
    "validatedPayments":  lambda: json.dumps([{"id": "PAY-001", "valid": True}]),
    "errors":             "[]",
    "payerMetrics":       lambda: json.dumps({"UNIMED": {"dso": 30, "rate": 0.9}}),
    "slowPayersList":     "[]",
    "slowPayerAccounts":  "[]",
    "slowPayersDetected": "false",
    "slowPayers":         "[]",
    "riskScores":         lambda: json.dumps({"AMIL": 0.3}),
    "predictedDates":     lambda: json.dumps({"PAY-001": "2026-04-15"}),
    "confidenceScores":   lambda: json.dumps({"PAY-001": 0.85}),
    # analytics
    "payerRankings":        lambda: json.dumps([{"payer": "UNIMED", "score": 95}]),
    "problemPayers":        "[]",
    "executiveDashboard":   lambda: json.dumps({"generated": True, "period": "2026-03"}),
    "operationalMetrics":   lambda: json.dumps({"efficiency": 0.87}),
    "recommendations":      lambda: json.dumps(["optimize billing cycle"]),
    "opportunities":        lambda: json.dumps([{"type": "upcoding_prevention", "value": 5000}]),
    "potentialValue":       "5000.00",
    "actionPlan":           lambda: json.dumps({"steps": ["review_contracts"]}),
    "estimatedImpact":      "10000.00",
    "matchedPayments":      lambda: json.dumps([{"id": "PAY-001"}]),
    "unmatchedPayments":    "[]",
    "contractRecommendations": lambda: json.dumps(["renegotiate AMIL"]),
    "pricingRecommendations":  lambda: json.dumps(["increase OPME margin"]),
    "negotiationOutcomes":  lambda: json.dumps([{"payer": "AMIL", "result": "AGREED"}]),
    "updatedForecasts":     lambda: json.dumps({"Q2": 250000}),
    "forecastAccuracy":     "0.88",
    # coding continued
    "compatibilityResult":  "COMPATIBLE",
    "validationResult":     "true",
    "agingReport":          lambda: json.dumps({"generated": True}),
    "reportPath":           "/tmp/aging_report.pdf",
}


def mock_value(var_name: str) -> str:
    """Retorna um valor mock realista para a variavel pelo nome."""
    v = _MOCK_STRINGS.get(var_name)
    if v is not None:
        return v() if callable(v) else v

    n = var_name.lower()
    # Heuristicas por sufixo/prefixo
    if any(s in n for s in ("valid", "success", "sent", "complete", "applied", "match", "found", "enabled")):
        return "true"
    if any(s in n for s in ("amount", "value", "total", "price", "cost")):
        return str(round(random.uniform(100, 5000), 2))
    if any(s in n for s in ("count", "qty", "quantity", "num")):
        return str(random.randint(1, 10))
    if any(s in n for s in ("date", "time", "at", "timestamp")):
        return "2026-03-18T10:00:00Z"
    if any(s in n for s in ("id", "key", "ref", "number", "code")):
        return f"MOCK-{uuid.uuid4().hex[:8].upper()}"
    if any(s in n for s in ("status", "state", "result", "outcome")):
        return "COMPLETED"
    if any(s in n for s in ("list", "items", "array", "data", "json", "details")):
        return "[]"
    if any(s in n for s in ("rate", "score", "percent", "ratio", "confidence")):
        return str(round(random.uniform(0.7, 1.0), 2))
    if any(s in n for s in ("message", "text", "description", "reason", "notes")):
        return "Mock value"
    if any(s in n for s in ("flag", "is_", "has_", "bool")):
        return "true"
    return "mock_value"


# ---------------------------------------------------------------------------
# Processos e variáveis de start
# ---------------------------------------------------------------------------

PROCESSES = {
    "SP_RC_003_Clinical_Service": lambda: {
        "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
        "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
        "payerId":     random.choice(["UNIMED-SP", "AMIL", "BRADESCO", "SULAMERICA", "NOTREDAME"]),
        "procedureCode": random.choice(["10101012", "30722018", "31309016", "40304361"]),
    },
    "SP_RC_004_Clinical_Production": lambda: {
        "patientId":      f"PAT-{uuid.uuid4().hex[:8]}",
        "encounterId":    f"ENC-{uuid.uuid4().hex[:8]}",
        "procedureCodes": random.choice(["10101012", "30722018", "31309016"]),
        "payerId":        random.choice(["UNIMED-SP", "AMIL", "BRADESCO"]),
        "specialty":      random.choice(["ORTOPEDIA", "CLINICA_MEDICA", "CARDIOLOGIA"]),
    },
    "SP_RC_005_Coding_Audit": lambda: {
        "patientId":      f"PAT-{uuid.uuid4().hex[:8]}",
        "encounterId":    f"ENC-{uuid.uuid4().hex[:8]}",
        "rawCodes":       random.choice(["10101012", "10101012,30722018", "31309016,40304361"]),
        "diagnosisCodes": random.choice(["J18.9", "M16.1", "I10", "Z00.0"]),
        "payerId":        random.choice(["UNIMED-SP", "AMIL", "BRADESCO", "SULAMERICA"]),
    },
    "SP_RC_006_Billing_Submission": lambda: {
        "encounterId":  f"ENC-{uuid.uuid4().hex[:8]}",
        "patientId":    f"PAT-{uuid.uuid4().hex[:8]}",
        "payerId":      random.choice(["UNIMED-SP", "AMIL", "BRADESCO"]),
        "guideType":    random.choice(["SADT", "INTERNACAO", "CONSULTA"]),
        "totalValue":   str(round(random.uniform(500, 15000), 2)),
        "procedureCodes": "10101012",
    },
    "SP_RC_007_Denial_Management": lambda: {
        "batchId":       f"BATCH-{uuid.uuid4().hex[:8]}",
        "payerResponse": json.dumps({"status": "denied", "reason": f"GLOSA-{random.randint(1,10):03d}", "value": round(random.uniform(500, 8000), 2)}),
        "payerId":       random.choice(["UNIMED-SP", "AMIL", "BRADESCO", "SULAMERICA"]),
    },
    "SP_RC_008_Revenue_Collection": lambda: {
        "paymentBatchId": f"BATCH-{uuid.uuid4().hex[:8]}",
        "paymentFile":    f"RETORNO_{uuid.uuid4().hex[:6].upper()}.RET",
        "payerId":        random.choice(["UNIMED-SP", "AMIL", "BRADESCO"]),
        "totalExpected":  str(round(random.uniform(5000, 50000), 2)),
    },
}

# ---------------------------------------------------------------------------
# Metricas em memoria
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_stats = {
    "started":   0,
    "completed": 0,
    "tasks":     0,
    "errors":    0,
    "by_topic":  defaultdict(int),
}
_stop_event = threading.Event()


def inc(key, topic=None):
    with _lock:
        _stats[key] += 1
        if topic:
            _stats["by_topic"][topic] += 1


# ---------------------------------------------------------------------------
# Iniciar instancias
# ---------------------------------------------------------------------------

def start_instances(session: requests.Session, n_per_process: int) -> list[str]:
    """Inicia n_per_process instancias para cada processo disponivel."""
    ids = []
    for proc_key, vars_fn in PROCESSES.items():
        for _ in range(n_per_process):
            variables = vars_fn()
            payload = {"variables": {k: {"value": v, "type": "String"} for k, v in variables.items()}}
            try:
                r = session.post(
                    f"{BASE}/process-definition/key/{proc_key}/tenant-id/{TENANT}/start",
                    json=payload, timeout=15,
                )
                if r.status_code == 200:
                    ids.append(r.json()["id"])
                    inc("started")
                else:
                    inc("errors")
            except Exception:
                inc("errors")
    return ids


# ---------------------------------------------------------------------------
# Worker thread — fetchAndLock + complete em todos os topicos
# ---------------------------------------------------------------------------

WORKER_ID_PREFIX = "load-test-worker"
LOCK_MS = 30_000  # 30s lock


def worker_thread(worker_num: int, topic_vars: dict[str, list[str]], session: requests.Session):
    """Thread de worker: faz fetchAndLock em todos os topicos e completa."""
    worker_id = f"{WORKER_ID_PREFIX}-{worker_num}"
    topics_list = [
        {"topicName": t, "lockDuration": LOCK_MS}
        for t in topic_vars.keys()
    ]
    # Batch de 10 topicos por vez para nao sobrecarregar
    batch_size = 20

    while not _stop_event.is_set():
        # Pega um subconjunto aleatorio de topicos para variar
        sample = random.sample(topics_list, min(batch_size, len(topics_list)))
        try:
            r = session.post(
                f"{BASE}/external-task/fetchAndLock",
                json={"workerId": worker_id, "maxTasks": 5, "topics": sample},
                timeout=10,
            )
            if r.status_code != 200:
                time.sleep(0.5)
                continue
            tasks = r.json()
        except Exception:
            time.sleep(1)
            continue

        if not tasks:
            time.sleep(0.2)
            continue

        for task in tasks:
            if _stop_event.is_set():
                break
            task_id = task["id"]
            topic   = task["topicName"]
            needed_vars = topic_vars.get(topic, [])
            variables = {v: {"value": mock_value(v), "type": "String"} for v in needed_vars}
            try:
                r = session.post(
                    f"{BASE}/external-task/{task_id}/complete",
                    json={"workerId": worker_id, "variables": variables},
                    timeout=10,
                )
                if r.status_code == 204:
                    inc("tasks", topic)
                else:
                    inc("errors")
            except Exception:
                inc("errors")


# ---------------------------------------------------------------------------
# Monitor thread — imprime relatorio a cada intervalo
# ---------------------------------------------------------------------------

def monitor_thread(interval: int, start_time: float):
    prev_tasks = 0
    while not _stop_event.is_set():
        time.sleep(interval)
        elapsed = time.time() - start_time
        with _lock:
            tasks  = _stats["tasks"]
            errors = _stats["errors"]
            started = _stats["started"]
        tps = (tasks - prev_tasks) / interval
        prev_tasks = tasks
        print(
            f"{CYAN}[{elapsed:5.0f}s]{NC}"
            f"  instancias={GREEN}{started}{NC}"
            f"  tasks={GREEN}{tasks}{NC}"
            f"  tps={YELLOW}{tps:.1f}/s{NC}"
            f"  erros={RED}{errors}{NC}"
        )


# ---------------------------------------------------------------------------
# Relatorio final
# ---------------------------------------------------------------------------

def final_report(session: requests.Session, start_time: float):
    elapsed = time.time() - start_time
    print(f"\n{BLUE}{'='*65}{NC}")
    print(f"{BLUE}  RELATORIO FINAL — Load Test RC{NC}")
    print(f"{BLUE}{'='*65}{NC}")
    print(f"  Duracao total:    {elapsed:.1f}s")
    print(f"  Instancias abertas: {_stats['started']}")
    print(f"  Tasks processadas:  {GREEN}{_stats['tasks']}{NC}")
    print(f"  Erros:              {RED}{_stats['errors']}{NC}")
    print(f"  Throughput medio:   {YELLOW}{_stats['tasks']/max(elapsed,1):.1f} tasks/s{NC}")

    # Top topics por volume
    with _lock:
        by_topic = dict(_stats["by_topic"])
    top = sorted(by_topic.items(), key=lambda x: -x[1])[:15]
    if top:
        print(f"\n  Top 15 topicos:")
        for t, n in top:
            bar = "#" * min(n // 2, 30)
            print(f"    {t:<45} {n:>4}  {GREEN}{bar}{NC}")

    # Estado dos processos no engine
    try:
        r = session.get(f"{BASE}/process-definition/count", params={"tenantIdIn": TENANT}, timeout=10)
        print(f"\n  Definicoes RC no engine: {r.json().get('count', '?')}")
        r = session.get(f"{BASE}/history/process-instance",
            params={
                "processDefinitionKeyIn": ",".join(PROCESSES.keys()),
                "tenantIdIn": TENANT,
                "sortBy": "startTime", "sortOrder": "desc",
                "maxResults": 1000,
            }, timeout=15)
        instances = r.json()
        from collections import Counter
        states = Counter(i["state"] for i in instances)
        print(f"  Estado das instancias (ultimo lote):")
        for state, n in sorted(states.items()):
            icon = GREEN if state == "COMPLETED" else (YELLOW if state == "ACTIVE" else RED)
            print(f"    {icon}{state:<15}{NC} {n}")
    except Exception as e:
        print(f"  (nao foi possivel buscar status final: {e})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Load Test RC — MAEZO")
    parser.add_argument("--instances",  type=int, default=30,
                        help="Instancias por processo (default: 30, total ~180)")
    parser.add_argument("--workers",    type=int, default=12,
                        help="Threads de worker (default: 12)")
    parser.add_argument("--duration",   type=int, default=90,
                        help="Duracao maxima em segundos (default: 90)")
    parser.add_argument("--monitor",    type=int, default=5,
                        help="Intervalo do relatorio em segundos (default: 5)")
    parser.add_argument("--bpmn-dir",   default="src/healthcare_platform/revenue_cycle/bpmn",
                        help="Diretorio dos BPMNs")
    args = parser.parse_args()

    # Parse BPMNs
    bpmn_dir = Path(args.bpmn_dir)
    print(f"{BLUE}[1] Extraindo topicos dos BPMNs em {bpmn_dir}...{NC}")
    topic_vars = parse_topic_output_vars(bpmn_dir)
    print(f"    {len(topic_vars)} topicos encontrados")

    # Session HTTP
    session = requests.Session()
    session.auth = AUTH
    session.headers.update({"Content-Type": "application/json"})

    # Verificar CIB Seven
    try:
        r = session.get(f"{BASE}/engine", timeout=10)
        assert r.status_code == 200
        print(f"{GREEN}[2] CIB Seven UP — engine: {r.json()[0]['name']}{NC}")
    except Exception as e:
        print(f"{RED}CIB Seven nao disponivel: {e}{NC}")
        sys.exit(1)

    # Iniciar instancias
    n_proc = len(PROCESSES)
    total = args.instances * n_proc
    print(f"{BLUE}[3] Iniciando {args.instances} instancias x {n_proc} processos = {total} total...{NC}")
    t0 = time.time()
    instance_ids = start_instances(session, args.instances)
    start_time = time.time()
    print(f"    {GREEN}{_stats['started']} instancias iniciadas{NC} em {start_time-t0:.1f}s"
          f"  ({RED}{_stats['errors']} erros{NC})")

    # Threads de worker
    print(f"{BLUE}[4] Iniciando {args.workers} threads de worker...{NC}")
    threads = []
    for i in range(args.workers):
        t = threading.Thread(
            target=worker_thread,
            args=(i, topic_vars, session),
            daemon=True,
        )
        t.start()
        threads.append(t)

    # Thread de monitor
    mon = threading.Thread(target=monitor_thread, args=(args.monitor, start_time), daemon=True)
    mon.start()

    print(f"{GREEN}[5] Load test rodando por {args.duration}s... (Ctrl+C para parar antes){NC}")
    print(f"    Acompanhe em: {YELLOW}http://localhost:9090{NC} (Prometheus)"
          f" | {YELLOW}http://localhost:3000{NC} (Grafana)\n")

    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrompido pelo usuario{NC}")

    _stop_event.set()
    time.sleep(1)

    final_report(session, start_time)


if __name__ == "__main__":
    main()
