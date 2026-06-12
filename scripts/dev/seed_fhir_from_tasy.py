#!/usr/bin/env python3
"""
MAEZO — Seed HAPI FHIR local com dados reais do Oracle Tasy.

Conecta no Oracle Tasy, executa as queries das views V01/V04/V05/V06/V07/
V24/V03/V09/MedAdmin/DiagReport, transforma cada linha em FHIR JSON e
faz POST no HAPI FHIR local (localhost:8082).

Uso:
  py scripts/dev/seed_fhir_from_tasy.py
  py scripts/dev/seed_fhir_from_tasy.py --dry-run
  py scripts/dev/seed_fhir_from_tasy.py --catalog encounter --limit 50
  py scripts/dev/seed_fhir_from_tasy.py --catalog organization,practitioner
  py scripts/dev/seed_fhir_from_tasy.py --url http://localhost:8082/fhir
  py scripts/dev/seed_fhir_from_tasy.py --env ignorar/hapifhir/.env

Dependencias:
  pip install oracledb httpx python-dotenv
"""

import argparse
import base64
import os
import re
import sys

# Força UTF-8 no stdout/stderr para evitar erros de encoding no Windows (cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from datetime import date, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("python-dotenv nao instalado. Execute: pip install python-dotenv")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("httpx nao instalado. Execute: pip install httpx")
    sys.exit(1)

try:
    import oracledb
except ImportError:
    print("oracledb nao instalado. Execute: pip install oracledb")
    sys.exit(1)

# ── Cores ─────────────────────────────────────────────────────────────────────
GREEN  = "\033[0;32m"
RED    = "\033[0;31m"
YELLOW = "\033[0;33m"
BLUE   = "\033[0;34m"
CYAN   = "\033[0;36m"
BOLD   = "\033[1m"
NC     = "\033[0m"

def ok(msg):   print(f"{GREEN}  [OK]{NC}      {msg}")
def fail(msg): print(f"{RED}  [FAIL]{NC}    {msg}")
def warn(msg): print(f"{YELLOW}  [WARN]{NC}    {msg}")
def info(msg): print(f"{BLUE}  [INFO]{NC}    {msg}")
def skip(msg): print(f"{CYAN}  [SKIP]{NC}    {msg}")

def header(msg):
    print(f"\n{BOLD}{CYAN}{'=' * 68}")
    print(f"  {msg}")
    print(f"{'=' * 68}{NC}\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _str(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    s = str(val).strip()
    return s if s else None


_FHIR_ID_RE = re.compile(r'[^A-Za-z0-9\-\.]')

def _fhir_id(*parts) -> str:
    raw = "-".join(str(p) for p in parts if p is not None)
    return _FHIR_ID_RE.sub("-", raw)[:64].strip("-")


def _date(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(val, date):
        return val.isoformat()
    return _str(val)


def _bool(val, true_val="S") -> bool:
    if val is None:
        return False
    return str(val).strip().upper() == true_val.upper()


def _b64(val) -> str | None:
    if val is None:
        return None
    try:
        text = val.read() if hasattr(val, "read") else str(val)
        return base64.b64encode(text.encode("utf-8", errors="replace")).decode()
    except Exception:
        return None


def post_resource(fhir: httpx.Client, resource_type: str, body: dict, dry_run: bool) -> bool:
    rid = body.get("id", "?")
    if dry_run:
        return True
    try:
        r = fhir.put(f"/{resource_type}/{rid}", json=body)
        if r.status_code in (200, 201):
            return True
        fail(f"{resource_type}/{rid} → HTTP {r.status_code}: {r.text[:400]}")
        return False
    except Exception as e:
        fail(f"{resource_type}/{rid} → {e}")
        return False


def print_report(label: str, total: int, sent: int, ok_count: int, field_counts: dict[str, int]):
    print(f"\n  {BOLD}Resultado — {label}{NC}")
    print(f"  {'-' * 60}")
    print(f"  Lidos no Oracle : {total}")
    print(f"  Enviados ao FHIR: {sent}")
    col = GREEN if ok_count == sent else (YELLOW if ok_count > sent * 0.8 else RED)
    print(f"  Sucesso         : {col}{ok_count}{NC}  |  Falha: {sent - ok_count}")
    if field_counts and sent:
        print(f"\n  {'Campo FHIR':<40} {'Preenchido':<14} {'%'}")
        print(f"  {'-' * 60}")
        for field, count in field_counts.items():
            pct = count / sent * 100
            cor = GREEN if pct >= 80 else (YELLOW if pct >= 40 else RED)
            print(f"  {field:<40} {count:>4}/{sent:<8} {cor}{pct:>5.1f}%{NC}")


# ── Conexões ──────────────────────────────────────────────────────────────────

def connect_oracle() -> oracledb.Connection:
    client_dir = os.getenv("ORACLE_CLIENT_DIR", "")
    if client_dir and Path(client_dir).exists():
        oracledb.init_oracle_client(lib_dir=client_dir)
        info(f"Oracle Instant Client: {client_dir}")
    else:
        info("Oracle thin mode (sem Instant Client)")
    return oracledb.connect(
        user=os.environ["ORACLE_USER"],
        password=os.environ["ORACLE_PASSWORD"],
        host=os.environ["ORACLE_HOST"],
        port=int(os.getenv("ORACLE_PORT", "1521")),
        service_name=os.environ["ORACLE_SERVICE"],
    )


def connect_fhir(base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=60,
        headers={
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        },
    )


# ── Catálogos ─────────────────────────────────────────────────────────────────

def seed_organizations(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V24 — Organization (Operadoras / Convênios)")
    SQL = """
        SELECT c.cd_convenio, c.ds_convenio, c.cd_cgc, ce.cd_ans, c.ie_situacao
        FROM convenio c, convenio_estabelecimento ce
        WHERE c.cd_convenio = ce.cd_convenio
          AND ce.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY c.cd_convenio DESC
    """
    cur = ora.cursor()
    cur.execute(SQL, tenant=tenant, limit=limit)
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "name": 0, "active": 0, "identifier[cnpj]": 0, "identifier[ans]": 0}

    for row in rows:
        r = dict(zip(cols, row))
        identifiers = []
        if r.get("cd_cgc"):
            identifiers.append({
                "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cnpj",
                "value": _str(r["cd_cgc"]),
            })
        if r.get("cd_ans"):
            identifiers.append({
                "system": "http://tasy.com/fhir/identifier/ans",
                "value": _str(r["cd_ans"]),
            })
        body = {
            "resourceType": "Organization",
            "id": str(r["cd_convenio"]),
            "active": _bool(r.get("ie_situacao"), "A"),
            "name": _str(r.get("ds_convenio")),
            "identifier": identifiers,
            "type": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/organization-type",
                                   "code": "ins", "display": "Insurance Company"}]}],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        sent += 1
        if post_resource(fhir, "Organization", body, dry_run):
            ok_n += 1
            if body.get("id"):          fc["id"] += 1
            if body.get("name"):        fc["name"] += 1
            if body.get("active") is not None: fc["active"] += 1
            if any(i.get("system","").endswith("cnpj") for i in identifiers): fc["identifier[cnpj]"] += 1
            if any(i.get("system","").endswith("ans")  for i in identifiers): fc["identifier[ans]"] += 1

    print_report("Organization", total, sent, ok_n, fc)


def seed_practitioners(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V07 — Practitioner (Médicos)")
    SQL = """
        SELECT m.cd_pessoa_fisica, m.nr_crm, m.nm_guerra, m.uf_crm,
               me.cd_especialidade,
               obter_desc_especialidade(me.cd_especialidade) ds_especialidade,
               pf.nr_telefone_celular, pf.cd_estabelecimento
        FROM medico m, medico_especialidade me, pessoa_fisica pf
        WHERE m.cd_pessoa_fisica = pf.cd_pessoa_fisica
          AND m.cd_pessoa_fisica = me.cd_pessoa_fisica
          AND pf.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY m.cd_pessoa_fisica DESC
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Practitioner — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "name": 0, "identifier[crm]": 0, "qualification": 0, "telecom": 0}

    for row in rows:
        r = dict(zip(cols, row))
        qualifications = []
        if r.get("cd_especialidade"):
            qualifications.append({
                "code": {
                    "coding": [{"system": "http://www.ans.gov.br/cbos",
                                 "code": _str(r["cd_especialidade"]),
                                 "display": _str(r.get("ds_especialidade"))}]
                }
            })
        telecom = []
        if r.get("nr_telefone_celular"):
            telecom.append({"system": "phone", "use": "mobile", "value": _str(r["nr_telefone_celular"])})

        body = {
            "resourceType": "Practitioner",
            "id": str(r["cd_pessoa_fisica"]),
            "identifier": [{"system": "http://tasy.com/fhir/identifier/crm",
                             "value": _str(r.get("nr_crm")),
                             "assigner": {"display": _str(r.get("uf_crm"))}}],
            "name": [{"text": _str(r.get("nm_guerra"))}],
            "qualification": qualifications,
            "telecom": telecom,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        sent += 1
        if post_resource(fhir, "Practitioner", body, dry_run):
            ok_n += 1
            if body.get("id"):          fc["id"] += 1
            if body["name"][0].get("text"): fc["name"] += 1
            if body["identifier"][0].get("value"): fc["identifier[crm]"] += 1
            if qualifications:          fc["qualification"] += 1
            if telecom:                 fc["telecom"] += 1

    print_report("Practitioner", total, sent, ok_n, fc)


def seed_patients(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V02 — Patient (Pacientes)")
    SQL = """
        SELECT p.cd_pessoa_fisica, p.nm_pessoa_fisica, p.dt_nascimento,
               p.ie_sexo, p.nr_cpf, p.nr_telefone_celular
        FROM pessoa_fisica p
        WHERE p.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY p.cd_pessoa_fisica DESC
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Patient — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    GENDER_MAP = {"M": "male", "F": "female", "I": "unknown"}
    sent = ok_n = 0
    fc = {"id": 0, "name": 0, "birthDate": 0, "gender": 0, "identifier[cpf]": 0, "telecom": 0}

    for row in rows:
        r = dict(zip(cols, row))
        telecom = []
        if r.get("nr_telefone_celular"):
            telecom.append({"system": "phone", "use": "mobile", "value": _str(r["nr_telefone_celular"])})
        identifiers = []
        if r.get("nr_cpf"):
            identifiers.append({"system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
                                 "value": _str(r["nr_cpf"])})

        body = {
            "resourceType": "Patient",
            "id": str(r["cd_pessoa_fisica"]),
            "identifier": identifiers,
            "name": [{"text": _str(r.get("nm_pessoa_fisica"))}],
            "birthDate": _date(r.get("dt_nascimento")),
            "gender": GENDER_MAP.get(_str(r.get("ie_sexo", "")) or "", "unknown"),
            "telecom": telecom,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        sent += 1
        if post_resource(fhir, "Patient", body, dry_run):
            ok_n += 1
            if body.get("id"):              fc["id"] += 1
            if body["name"][0].get("text"): fc["name"] += 1
            if body.get("birthDate"):       fc["birthDate"] += 1
            if body.get("gender"):          fc["gender"] += 1
            if identifiers:                 fc["identifier[cpf]"] += 1
            if telecom:                     fc["telecom"] += 1

    print_report("Patient", total, sent, ok_n, fc)


def seed_encounters(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V01 — Encounter (Atendimentos)")
    SQL = """
        SELECT a.nr_atendimento, a.cd_estabelecimento,
               a.cd_pessoa_fisica, a.ie_tipo_atendimento,
               a.dt_entrada, a.dt_alta, a.ie_status_atendimento,
               b.cd_convenio, a.cd_medico_resp,
               a.ie_carater_inter_sus, a.ie_tipo_consulta,
               b.ie_regime_internacao, a.cd_motivo_alta,
               (SELECT c.cd_setor_atendimento
                FROM ATEND_PACIENTE_UNIDADE c
                WHERE c.nr_atendimento = a.nr_atendimento
                ORDER BY c.dt_entrada_unidade DESC
                FETCH FIRST 1 ROWS ONLY) cd_setor_atendimento,
               (SELECT c.ds_indicacao
                FROM AUTORIZACAO_CONVENIO c
                WHERE c.nr_atendimento = a.nr_atendimento
                ORDER BY c.nr_sequencia DESC
                FETCH FIRST 1 ROWS ONLY) ds_indicacao
        FROM ATENDIMENTO_PACIENTE a, ATEND_CATEGORIA_CONVENIO b
        WHERE a.nr_atendimento = b.nr_atendimento
          AND a.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY a.nr_atendimento DESC
    """
    STATUS_MAP = {"A": "in-progress", "F": "finished", "C": "cancelled"}
    CLASS_MAP  = {"C": ("AMB", "ambulatory"), "I": ("IMP", "inpatient encounter"),
                  "U": ("EMER", "emergency"),  "A": ("AMB", "ambulatory"),
                  "S": ("AMB", "ambulatory")}
    PRIORITY_MAP = {"U": "urgent", "E": "elective", "EL": "elective",
                    "A": "asap",   "R": "routine"}

    cur = ora.cursor()
    cur.execute(SQL, tenant=tenant, limit=limit)
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {
        "status": 0, "class": 0, "serviceType": 0, "priority": 0,
        "type": 0, "period.start": 0, "period.end": 0,
        "hospitalization.admitSource": 0, "hospitalization.dischargeDisposition": 0,
        "reasonCode": 0, "participant": 0,
    }

    for row in rows:
        r = dict(zip(cols, row))
        tipo = _str(r.get("ie_tipo_atendimento")) or ""
        cls_code, cls_display = CLASS_MAP.get(tipo[:1].upper(), ("AMB", "ambulatory"))
        carater = _str(r.get("ie_carater_inter_sus")) or ""

        hospitalization = {}
        if r.get("ie_regime_internacao"):
            hospitalization["admitSource"] = {
                "coding": [{"system": "http://tasy.com/fhir/CodeSystem/regime-internacao",
                             "code": _str(r["ie_regime_internacao"])}]
            }
        if r.get("cd_motivo_alta"):
            hospitalization["dischargeDisposition"] = {
                "coding": [{"system": "http://tasy.com/fhir/CodeSystem/motivo-alta",
                             "code": _str(r["cd_motivo_alta"])}]
            }

        participants = []
        if r.get("cd_medico_resp"):
            participants.append({
                "individual": {"reference": f"Practitioner/{r['cd_medico_resp']}"}
            })

        reason_code = []
        if r.get("ds_indicacao"):
            reason_code.append({"text": _str(r["ds_indicacao"])})

        body = {
            "resourceType": "Encounter",
            "id": str(r["nr_atendimento"]),
            "identifier": [{"system": "http://tasy.com/fhir/identifier/atendimento",
                             "value": str(r["nr_atendimento"])}],
            "status": STATUS_MAP.get(_str(r.get("ie_status_atendimento")) or "", "unknown"),
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                      "code": cls_code, "display": cls_display},
            "serviceType": {"coding": [{"system": "http://tasy.com/fhir/CodeSystem/tipo-atendimento",
                                         "code": tipo}]} if tipo else None,
            "priority": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActPriority",
                                      "code": PRIORITY_MAP.get(carater.upper(), carater)}]} if carater else None,
            "type": [{"coding": [{"system": "http://tasy.com/fhir/CodeSystem/tipo-consulta",
                                   "code": _str(r.get("ie_tipo_consulta"))}]}] if r.get("ie_tipo_consulta") else [],
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"},
            "serviceProvider": {"type": "Organization",
                                 "identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                                 "value": str(r["cd_convenio"])}} if r.get("cd_convenio") else None,
            "period": {
                "start": _date(r.get("dt_entrada")),
                "end":   _date(r.get("dt_alta")),
            },
            "hospitalization": hospitalization if hospitalization else None,
            "participant": participants,
            "reasonCode": reason_code,
            "extension": [
                ext for ext in [
                    {"url": "http://tasy.com/fhir/extension/cdEstabelecimento",
                     "valueInteger": int(r["cd_estabelecimento"])} if r.get("cd_estabelecimento") else None,
                    {"url": "http://tasy.com/fhir/extension/cdSetor",
                     "valueString": _str(r["cd_setor_atendimento"])} if r.get("cd_setor_atendimento") else None,
                ] if ext is not None
            ] or None,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        # limpa None
        body = {k: v for k, v in body.items() if v is not None and v != [] and v != {}}

        sent += 1
        if post_resource(fhir, "Encounter", body, dry_run):
            ok_n += 1
            if body.get("status"):                              fc["status"] += 1
            if body.get("class"):                               fc["class"] += 1
            if body.get("serviceType"):                         fc["serviceType"] += 1
            if body.get("priority"):                            fc["priority"] += 1
            if body.get("type"):                                fc["type"] += 1
            if body.get("period", {}).get("start"):             fc["period.start"] += 1
            if body.get("period", {}).get("end"):               fc["period.end"] += 1
            if body.get("hospitalization", {}).get("admitSource"):         fc["hospitalization.admitSource"] += 1
            if body.get("hospitalization", {}).get("dischargeDisposition"):fc["hospitalization.dischargeDisposition"] += 1
            if body.get("reasonCode"):                          fc["reasonCode"] += 1
            if body.get("participant"):                         fc["participant"] += 1

    print_report("Encounter", total, sent, ok_n, fc)


def seed_coverages(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V05 — Coverage (Convênio do Paciente)")
    SQL = """
        SELECT ap.cd_pessoa_fisica, ac.cd_convenio,
               obter_desc_convenio(ac.cd_convenio) nm_convenio,
               ac.cd_plano_convenio, ac.cd_usuario_convenio,
               ac.dt_validade_carteira, ac.cd_tipo_acomodacao,
               ap.cd_estabelecimento, ap.nr_atendimento
        FROM atendimento_paciente ap, atend_categoria_convenio ac
        WHERE ap.nr_atendimento = ac.nr_atendimento
          AND ap.cd_estabelecimento = :tenant
          AND ap.dt_cancelamento IS NULL
          AND ROWNUM <= :limit
        ORDER BY ap.nr_atendimento DESC
    """
    cur = ora.cursor()
    cur.execute(SQL, tenant=tenant, limit=limit)
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "beneficiary": 0, "payor": 0,
          "identifier[carteirinha]": 0, "class[plan]": 0,
          "type": 0, "period.end": 0}

    for row in rows:
        r = dict(zip(cols, row))
        cov_class = []
        if r.get("cd_plano_convenio"):
            cov_class.append({
                "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/coverage-class",
                                      "code": "plan"}]},
                "value": _str(r["cd_plano_convenio"]),
            })
        identifiers = []
        if r.get("cd_usuario_convenio"):
            identifiers.append({"system": "http://tasy.com/fhir/identifier/carteirinha",
                                 "value": _str(r["cd_usuario_convenio"])})

        body = {
            "resourceType": "Coverage",
            "id": f"{r['cd_pessoa_fisica']}-{r['cd_convenio']}",
            "status": "active",
            "identifier": identifiers,
            "beneficiary": {"reference": f"Patient/{r['cd_pessoa_fisica']}"},
            "payor": [{"type": "Organization",
                        "identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                        "value": str(r["cd_convenio"])},
                        "display": _str(r.get("nm_convenio"))}],
            "class": cov_class,
            "type": {"coding": [{"system": "http://tasy.com/fhir/CodeSystem/tipo-cobertura",
                                   "code": _str(r.get("cd_tipo_acomodacao")) or "AH"}]} if r.get("cd_tipo_acomodacao") else None,
            "period": {"end": _date(r.get("dt_validade_carteira"))} if r.get("dt_validade_carteira") else None,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None}

        sent += 1
        if post_resource(fhir, "Coverage", body, dry_run):
            ok_n += 1
            if body.get("status"):      fc["status"] += 1
            if body.get("beneficiary"): fc["beneficiary"] += 1
            if body.get("payor"):       fc["payor"] += 1
            if identifiers:             fc["identifier[carteirinha]"] += 1
            if cov_class:               fc["class[plan]"] += 1
            if body.get("type"):        fc["type"] += 1
            if body.get("period"):      fc["period.end"] += 1

    print_report("Coverage", total, sent, ok_n, fc)


def seed_procedures(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V04 — Procedure (Procedimentos TUSS)")
    SQL = """
        SELECT pp.nr_seq_proc_interno, p.nr_atendimento, p.cd_pessoa_fisica,
               pp.cd_procedimento,
               coalesce(obter_desc_proc_interno(pp.nr_seq_proc_interno),
                        obter_desc_procedimento(pp.cd_procedimento, pp.ie_origem_proced)) ds_procedimento,
               pp.ie_status_execucao, pp.dt_baixa, pp.dt_inicio, pp.dt_fim,
               pp.qt_procedimento, pp.cd_medico_exec,
               (SELECT pa.nr_sequencia_autor
                FROM procedimento_autorizado pa
                WHERE pa.nr_prescricao = pp.nr_prescricao
                  AND pa.nr_seq_prescricao = pp.nr_sequencia
                FETCH FIRST 1 ROWS ONLY) nr_seq_autorizacao,
               p.cd_estabelecimento
        FROM prescr_medica p, prescr_procedimento pp
        WHERE p.nr_prescricao = pp.nr_prescricao
          AND p.dt_liberacao IS NOT NULL
          AND p.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY pp.nr_seq_proc_interno DESC
    """
    STATUS_MAP = {"R": "preparation", "C": "completed", "E": "in-progress",
                  "X": "not-done",    "S": "on-hold"}

    cur = ora.cursor()
    cur.execute(SQL, tenant=tenant, limit=limit)
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "code.code": 0, "code.display": 0,
          "subject": 0, "encounter": 0, "performedDateTime": 0,
          "performer": 0, "extension[quantity]": 0, "extension[authorization]": 0}

    for row in rows:
        r = dict(zip(cols, row))
        extensions = []
        if r.get("qt_procedimento"):
            extensions.append({"url": "http://tasy.com/fhir/extension/quantity",
                                "valueInteger": int(r["qt_procedimento"])})
        if r.get("nr_seq_autorizacao"):
            extensions.append({"url": "http://tasy.com/fhir/extension/authorization",
                                "valueString": str(r["nr_seq_autorizacao"])})
        performers = []
        if r.get("cd_medico_exec"):
            performers.append({"actor": {"reference": f"Practitioner/{r['cd_medico_exec']}"}})

        body = {
            "resourceType": "Procedure",
            "id": str(r["nr_seq_proc_interno"]),
            "identifier": [{"system": "http://tasy.com/fhir/identifier/procedimento",
                             "value": str(r["nr_seq_proc_interno"])}],
            "status": STATUS_MAP.get(_str(r.get("ie_status_execucao")) or "", "unknown"),
            "code": {
                "coding": [{"system": "http://www.ans.gov.br/tuss",
                             "code": _str(r.get("cd_procedimento")),
                             "display": _str(r.get("ds_procedimento"))}]
            },
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"},
            "encounter": {"reference": f"Encounter/{r['nr_atendimento']}"},
            "performedPeriod": {
                "start": _date(r.get("dt_inicio") or r.get("dt_baixa")),
                "end":   _date(r.get("dt_fim")),
            } if (r.get("dt_inicio") or r.get("dt_baixa")) else None,
            "performer": performers,
            "extension": extensions,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }

        sent += 1
        if post_resource(fhir, "Procedure", body, dry_run):
            ok_n += 1
            if body.get("status"):                              fc["status"] += 1
            if body["code"]["coding"][0].get("code"):           fc["code.code"] += 1
            if body["code"]["coding"][0].get("display"):        fc["code.display"] += 1
            if body.get("subject"):                             fc["subject"] += 1
            if body.get("encounter"):                           fc["encounter"] += 1
            if body.get("performedPeriod"):                     fc["performedDateTime"] += 1
            if performers:                                      fc["performer"] += 1
            if any(e["url"].endswith("quantity")      for e in extensions): fc["extension[quantity]"] += 1
            if any(e["url"].endswith("authorization") for e in extensions): fc["extension[authorization]"] += 1

    print_report("Procedure", total, sent, ok_n, fc)


def seed_claim_responses(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V06 — ClaimResponse (Autorizações)")
    SQL = """
        SELECT ac.nr_sequencia, ac.nr_atendimento, ac.cd_pessoa_fisica,
               ac.cd_convenio, ac.cd_autorizacao, ac.ie_carater_int_tiss,
               ac.dt_autorizacao, ac.dt_validade_guia,
               ac.ie_tiss_tipo_acidente, ac.cd_estabelecimento,
               ac.ds_indicacao, ac.ds_observacao, ac.qt_dia_solicitado
        FROM autorizacao_convenio ac
        WHERE ac.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY ac.nr_sequencia DESC
    """
    ACCIDENT_MAP = {"0": "Nao acidente", "1": "Acidente de Transito",
                    "2": "Acidente de Trabalho", "9": "Outros"}

    cur = ora.cursor()
    cur.execute(SQL, tenant=tenant, limit=limit)
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "outcome": 0, "patient": 0, "insurer": 0,
          "preAuthRef": 0, "extension[encounter]": 0, "extension[accident]": 0}

    for row in rows:
        r = dict(zip(cols, row))
        extensions = [
            {"url": "http://tasy.com/fhir/extension/encounter",
             "valueReference": {"reference": f"Encounter/{r['nr_atendimento']}"}},
        ]
        acidente = _str(r.get("ie_tiss_tipo_acidente"))
        if acidente:
            extensions.append({
                "url": "http://tasy.com/fhir/extension/accident",
                "valueCodeableConcept": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                                 "code": "ACCIDENT",
                                 "display": ACCIDENT_MAP.get(acidente, acidente)}]
                },
            })
        if r.get("ds_indicacao"):
            extensions.append({"url": "http://tasy.com/fhir/extension/dsIndicacao",
                                "valueString": _str(r["ds_indicacao"])})
        if r.get("ds_observacao"):
            extensions.append({"url": "http://tasy.com/fhir/extension/dsObservacao",
                                "valueString": _str(r["ds_observacao"])})
        if r.get("qt_dia_solicitado") is not None:
            extensions.append({"url": "http://tasy.com/fhir/extension/qtDiaSolicitado",
                                "valueInteger": int(r["qt_dia_solicitado"] or 0)})

        body = {
            "resourceType": "ClaimResponse",
            "id": str(r["nr_sequencia"]),
            "identifier": [{"system": "http://tasy.com/fhir/identifier/autorizacao",
                             "value": str(r["nr_sequencia"])}],
            "status": "active",
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type",
                                   "code": "institutional"}]},
            "use": "preauthorization",
            "outcome": "queued",
            "patient": {"reference": f"Patient/{r['cd_pessoa_fisica']}"},
            "insurer": {"type": "Organization",
                         "identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                         "value": str(r["cd_convenio"])}},
            "request": {"reference": f"Claim/{r['nr_sequencia']}"},
            "created": _date(r.get("dt_autorizacao")) or datetime.now().isoformat(),
            "preAuthRef": _str(r.get("cd_autorizacao")),
            "preAuthPeriod": {"end": _date(r.get("dt_validade_guia"))} if r.get("dt_validade_guia") else None,
            "extension": extensions,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None}

        sent += 1
        if post_resource(fhir, "ClaimResponse", body, dry_run):
            ok_n += 1
            if body.get("status"):      fc["status"] += 1
            if body.get("outcome"):     fc["outcome"] += 1
            if body.get("patient"):     fc["patient"] += 1
            if body.get("insurer"):     fc["insurer"] += 1
            if body.get("preAuthRef"):  fc["preAuthRef"] += 1
            fc["extension[encounter]"] += 1
            if acidente:                fc["extension[accident]"] += 1

    print_report("ClaimResponse", total, sent, ok_n, fc)


def seed_conditions(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V03 — Condition (Diagnósticos CID-10)")
    SQL = """
        SELECT a.nr_atendimento, a.cd_estabelecimento, a.cd_pessoa_fisica,
               b.cd_doenca,
               obter_diagnost_doenca_atend(a.nr_atendimento) ds_diag,
               b.dt_diagnostico, b.ie_classificacao_doenca, b.ie_tipo_diagnostico
        FROM atendimento_paciente a
        JOIN diagnostico_doenca b ON b.nr_atendimento = a.nr_atendimento
        WHERE a.cd_estabelecimento = :tenant
          AND b.dt_liberacao IS NOT NULL
          AND b.ie_situacao = 'A'
          AND ROWNUM <= :limit
        ORDER BY a.nr_atendimento DESC
    """
    TYPE_MAP = {"P": "encounter-diagnosis", "S": "problem-list-item", "C": "problem-list-item"}
    STATUS_MAP = {"A": "active", "R": "resolved", "I": "inactive"}

    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Condition — query falhou (tabela DIAGNOSTICO_DOENCA?): {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"code.cid": 0, "code.text": 0, "category": 0,
          "clinicalStatus": 0, "encounter": 0, "subject": 0}

    for row in rows:
        r = dict(zip(cols, row))
        tipo = _str(r.get("ie_tipo_diagnostico")) or "P"
        status_val = _str(r.get("ie_classificacao_doenca")) or "A"

        body = {
            "resourceType": "Condition",
            "id": f"{r['nr_atendimento']}-{_str(r['cd_doenca']) or 'X'}",
            "clinicalStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                             "code": STATUS_MAP.get(status_val, "active")}]
            },
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category",
                                        "code": TYPE_MAP.get(tipo, "encounter-diagnosis")}]}],
            "code": {
                "coding": [{"system": "http://hl7.org/fhir/sid/icd-10",
                             "code": _str(r.get("cd_doenca"))}],
                "text": _str(r.get("ds_diag")),
            },
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"},
            "encounter": {"reference": f"Encounter/{r['nr_atendimento']}"},
            "recordedDate": _date(r.get("dt_diagnostico")),
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }

        sent += 1
        if post_resource(fhir, "Condition", body, dry_run):
            ok_n += 1
            if body["code"]["coding"][0].get("code"): fc["code.cid"] += 1
            if body["code"].get("text"):               fc["code.text"] += 1
            if body.get("category"):                   fc["category"] += 1
            if body.get("clinicalStatus"):             fc["clinicalStatus"] += 1
            if body.get("encounter"):                  fc["encounter"] += 1
            if body.get("subject"):                    fc["subject"] += 1

    print_report("Condition", total, sent, ok_n, fc)


def seed_document_references(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V09 — DocumentReference (Evoluções Clínicas + Assinatura)")
    # Colunas reais de EVOLUCAO_PACIENTE: PK=CD_EVOLUCAO, author=CD_MEDICO,
    # status=IE_SITUACAO ('A'=ativo), DS_EVOLUCAO é LONG (não CLOB).
    # NR_SEQ_ASSINATURA != NULL indica que o documento tem assinatura digital.
    # Não tem CD_ESTABELECIMENTO — filtro via JOIN com ATENDIMENTO_PACIENTE.
    SQL = """
        SELECT e.cd_evolucao, e.nr_atendimento, e.cd_pessoa_fisica,
               e.ds_evolucao, e.ie_tipo_evolucao, e.dt_evolucao,
               e.cd_medico, e.nr_seq_assinatura, e.ie_situacao
        FROM evolucao_paciente e
        JOIN atendimento_paciente ap ON ap.nr_atendimento = e.nr_atendimento
        WHERE ap.cd_estabelecimento = :tenant
          AND e.ie_situacao = 'A'
          AND ROWNUM <= :limit
        ORDER BY e.cd_evolucao DESC
    """
    TYPE_MAP = {"E": "11488-4", "L": "18748-4", "N": "34109-9"}
    TYPE_DISPLAY = {"E": "Evolucao medica", "L": "Laudo", "N": "Nota de enfermagem"}

    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"DocumentReference — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "type": 0, "content": 0, "date": 0,
          "author": 0, "authenticator[signed]": 0, "context.encounter": 0}

    for row in rows:
        r = dict(zip(cols, row))
        tipo = _str(r.get("ie_tipo_evolucao")) or "E"
        conteudo = _b64(r.get("ds_evolucao"))
        has_signature = r.get("nr_seq_assinatura") is not None

        body = {
            "resourceType": "DocumentReference",
            "id": str(r["cd_evolucao"]),
            "status": "current",
            "type": {"coding": [{"system": "http://loinc.org",
                                   "code": TYPE_MAP.get(tipo, "11488-4"),
                                   "display": TYPE_DISPLAY.get(tipo, tipo)}]},
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"},
            "date": _date(r.get("dt_evolucao")),
            "author": [{"identifier": {"system": "http://tasy.com/fhir/identifier/crm",
                                        "value": str(r["cd_medico"])}}] if r.get("cd_medico") else [],
            # authenticator = médico autor quando documento tem assinatura digital
            "authenticator": {"identifier": {"system": "http://tasy.com/fhir/identifier/crm",
                                              "value": str(r["cd_medico"])}} if has_signature and r.get("cd_medico") else None,
            "content": [{"attachment": {
                "contentType": "text/plain",
                "data": conteudo,
            }}] if conteudo else [],
            "context": {"encounter": [{"reference": f"Encounter/{r['nr_atendimento']}"}]},
            "extension": [{"url": "http://tasy.com/fhir/extension/assinatura",
                           "valueInteger": int(r["nr_seq_assinatura"])}] if has_signature else [],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}

        sent += 1
        if post_resource(fhir, "DocumentReference", body, dry_run):
            ok_n += 1
            if body.get("status"):              fc["status"] += 1
            if body.get("type"):                fc["type"] += 1
            if body.get("content"):             fc["content"] += 1
            if body.get("date"):                fc["date"] += 1
            if body.get("author"):              fc["author"] += 1
            if body.get("authenticator"):       fc["authenticator[signed]"] += 1
            if body.get("context"):             fc["context.encounter"] += 1

    print_report("DocumentReference", total, sent, ok_n, fc)


def seed_medication_admin(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("MedicationAdministration (PRESCR_MAT_HOR — Checagem/Administracao)")
    # Tabela real: PRESCR_MAT_HOR (nao existe CHECAGEM_MEDICAMENTO no Tasy).
    # DT_CHECAGEM = data/hora da administracao; NM_USUARIO_ADM = quem administrou.
    # Status: NM_USUARIO_ADM IS NOT NULL = completed; NULL = not-done.
    SQL = """
        SELECT h.nr_sequencia, h.nr_atendimento, h.nr_prescricao,
               h.nr_seq_material, h.cd_material, m.ds_material,
               h.qt_dose, h.cd_unidade_medida_dose, h.ds_horario,
               h.dt_horario, h.dt_checagem, h.nm_usuario_adm,
               h.dt_suspensao, h.dt_recusa, h.ie_situacao,
               p.cd_pessoa_fisica
        FROM prescr_mat_hor h
        JOIN prescr_medica p ON p.nr_prescricao = h.nr_prescricao
        LEFT JOIN material m ON m.cd_material = h.cd_material
        WHERE p.cd_estabelecimento = :tenant
          AND h.ie_situacao != 'C'
          AND ROWNUM <= :limit
        ORDER BY h.nr_sequencia DESC
    """

    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"MedicationAdministration — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "medication": 0, "subject": 0,
          "effectiveDateTime": 0, "performer": 0, "dosage": 0, "request": 0}

    for row in rows:
        r = dict(zip(cols, row))
        # Status: checado+assinado = completed; recusado = not-done; suspenso = stopped; default = in-progress
        if r.get("dt_checagem") and r.get("nm_usuario_adm"):
            status = "completed"
        elif r.get("dt_recusa"):
            status = "not-done"
        elif r.get("dt_suspensao"):
            status = "stopped"
        else:
            status = "in-progress"

        effective = _date(r.get("dt_checagem") or r.get("dt_horario"))

        body = {
            "resourceType": "MedicationAdministration",
            "id": str(r["nr_sequencia"]),
            "status": status,
            "medicationCodeableConcept": {
                "coding": [{"system": "http://tasy.com/fhir/CodeSystem/material",
                             "code": _str(r.get("cd_material"))}],
                "text": _str(r.get("ds_material")),
            },
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
            "context": {"reference": f"Encounter/{r['nr_atendimento']}"} if r.get("nr_atendimento") else None,
            "effectiveDateTime": effective,
            "performer": [{"actor": {"display": str(r["nm_usuario_adm"])}}] if r.get("nm_usuario_adm") else [],
            "dosage": {
                "dose": {"value": float(r["qt_dose"]),
                         "unit": _str(r.get("cd_unidade_medida_dose"))},
                "text": _str(r.get("ds_horario")),
            } if r.get("qt_dose") else None,
            "request": {"reference": f"MedicationRequest/{r['nr_seq_material']}"} if r.get("nr_seq_material") else None,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}

        sent += 1
        if post_resource(fhir, "MedicationAdministration", body, dry_run):
            ok_n += 1
            if body.get("status"):              fc["status"] += 1
            if body.get("medicationCodeableConcept"): fc["medication"] += 1
            if body.get("subject"):             fc["subject"] += 1
            if body.get("effectiveDateTime"):   fc["effectiveDateTime"] += 1
            if body.get("performer"):           fc["performer"] += 1
            if body.get("dosage"):              fc["dosage"] += 1
            if body.get("request"):             fc["request"] += 1

    print_report("MedicationAdministration", total, sent, ok_n, fc)


def seed_diagnostic_reports(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("DiagnosticReport (Laudos — LAUDO_PACIENTE)")
    # Tabela real: LAUDO_PACIENTE (não existe tabela genérica LAUDO).
    # Não tem cd_estabelecimento próprio — JOIN com PRESCR_MEDICA para filtrar tenant.
    # IE_STATUS_LAUDO: LL=final(liberado), LD=partial(digitado), LC=cancelled.
    # DS_LAUDO é LONG (igual a DS_EVOLUCAO).
    SQL = """
        SELECT lp.nr_sequencia, lp.nr_atendimento, lp.cd_pessoa_fisica,
               lp.ds_titulo_laudo, lp.ie_status_laudo,
               COALESCE(lp.dt_liberacao, lp.dt_laudo) dt_conclusao,
               lp.cd_medico_resp, lp.ds_laudo
        FROM laudo_paciente lp
        JOIN prescr_medica pm ON pm.nr_prescricao = lp.nr_prescricao
        WHERE pm.cd_estabelecimento = :tenant
          AND lp.ie_status_laudo != 'LC'
          AND ROWNUM <= :limit
        ORDER BY lp.nr_sequencia DESC
    """
    STATUS_MAP = {"LL": "final", "LD": "partial", "LC": "cancelled"}

    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"DiagnosticReport — query falhou: {e}")
        warn("Verifique se LAUDO_PACIENTE tem dados com cd_estabelecimento={tenant} via PRESCR_MEDICA.")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "code.text": 0, "subject": 0,
          "encounter": 0, "effectiveDateTime": 0, "performer": 0, "conclusion": 0}

    for row in rows:
        r = dict(zip(cols, row))
        conclusao = _b64(r.get("ds_laudo"))

        body = {
            "resourceType": "DiagnosticReport",
            "id": str(r["nr_sequencia"]),
            "status": STATUS_MAP.get(_str(r.get("ie_status_laudo")) or "", "unknown"),
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                                        "code": "LAB"}]}],
            "code": {"text": _str(r.get("ds_titulo_laudo")) or "Laudo"},
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
            "encounter": {"reference": f"Encounter/{r['nr_atendimento']}"} if r.get("nr_atendimento") else None,
            "effectiveDateTime": _date(r.get("dt_conclusao")),
            "performer": [{"identifier": {"system": "http://tasy.com/fhir/identifier/crm",
                                           "value": str(r["cd_medico_resp"])}}] if r.get("cd_medico_resp") else [],
            # DS_LAUDO (LONG) em base64 no presentedForm
            "presentedForm": [{"contentType": "text/plain", "data": conclusao}] if conclusao else [],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}

        sent += 1
        if post_resource(fhir, "DiagnosticReport", body, dry_run):
            ok_n += 1
            if body.get("status"):              fc["status"] += 1
            if body["code"].get("text"):        fc["code.text"] += 1
            if body.get("subject"):             fc["subject"] += 1
            if body.get("encounter"):           fc["encounter"] += 1
            if body.get("effectiveDateTime"):   fc["effectiveDateTime"] += 1
            if body.get("performer"):           fc["performer"] += 1
            if body.get("presentedForm"):       fc["conclusion"] += 1

    print_report("DiagnosticReport", total, sent, ok_n, fc)


# ── Novos catálogos ───────────────────────────────────────────────────────────

def _build_medication_coding(r: dict) -> list:
    codings = []
    if r.get("cd_snomed"):
        codings.append({"system": "http://snomed.info/sct",
                        "code": _str(r["cd_snomed"]), "display": _str(r.get("ds_material"))})
    if r.get("cd_dcb"):
        codings.append({"system": "http://www.anvisa.gov.br/dcb",
                        "code": _str(r["cd_dcb"]), "display": _str(r.get("ds_material"))})
    if r.get("nr_registro_anvisa"):
        codings.append({"system": "http://www.anvisa.gov.br/registro",
                        "code": _str(r["nr_registro_anvisa"])})
    codings.append({"system": "http://tasy.com/fhir/CodeSystem/material",
                    "code": _str(r.get("cd_material")), "display": _str(r.get("ds_material"))})
    return codings


def seed_medication_requests(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V08 — MedicationRequest (Prescrições Médicas)")
    SQL = """
        SELECT * FROM (
            SELECT pm.nr_prescricao, pm.nr_atendimento, pm.cd_pessoa_fisica,
                   pm.cd_medico, pm.dt_prescricao, pm.dt_suspensao, pm.ds_motivo_susp,
                   mh.cd_material,
                   MAX(mh.qt_dose)                AS qt_dose,
                   MAX(mh.cd_unidade_medida_dose) AS cd_unidade_medida_dose,
                   MAX(mh.ie_situacao)            AS ie_situacao,
                   mat.ds_material, mat.cd_snomed, mat.nr_registro_anvisa,
                   mat.cd_dcb, mat.ie_controle_medico
            FROM TASY.PRESCR_MEDICA pm
            JOIN TASY.PRESCR_MAT_HOR mh ON mh.nr_prescricao = pm.nr_prescricao
            LEFT JOIN TASY.MATERIAL mat ON mat.cd_material = TO_NUMBER(mh.cd_material)
            WHERE pm.cd_estabelecimento = :tenant
              AND pm.dt_liberacao IS NOT NULL
              AND pm.dt_prescricao >= TRUNC(SYSDATE) - 90
            GROUP BY pm.nr_prescricao, pm.nr_atendimento, pm.cd_pessoa_fisica,
                     pm.cd_medico, pm.dt_prescricao, pm.dt_suspensao, pm.ds_motivo_susp,
                     mh.cd_material, mat.ds_material, mat.cd_snomed,
                     mat.nr_registro_anvisa, mat.cd_dcb, mat.ie_controle_medico
            ORDER BY pm.dt_prescricao DESC
        ) WHERE ROWNUM <= :limit
    """
    MED_STATUS = {"A": "active", "C": "completed", "S": "stopped", "X": "cancelled"}
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"MedicationRequest — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "status": 0, "medication": 0, "subject": 0,
          "encounter": 0, "requester": 0, "dosage": 0}

    for row in rows:
        r = dict(zip(cols, row))
        status = MED_STATUS.get(_str(r.get("ie_situacao")) or "", "unknown")
        if r.get("dt_suspensao"):
            status = "stopped"
        codings = _build_medication_coding(r)
        body = {
            "resourceType": "MedicationRequest",
            "id": f"{r['nr_prescricao']}-{r['cd_material']}",
            "status": status,
            "intent": "order",
            "medicationCodeableConcept": {
                "coding": codings,
                "text": _str(r.get("ds_material")) or _str(r.get("cd_material")),
            },
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"},
            "encounter": {"reference": f"Encounter/{r['nr_atendimento']}"},
            "authoredOn": _date(r.get("dt_prescricao")),
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        if r.get("cd_medico"):
            body["requester"] = {"reference": f"Practitioner/{r['cd_medico']}"}
        if r.get("ds_motivo_susp"):
            body["statusReason"] = {"text": _str(r["ds_motivo_susp"])}
        if r.get("qt_dose"):
            body["dosageInstruction"] = [{"doseAndRate": [{"doseQuantity": {
                "value": float(r["qt_dose"]),
                "unit": _str(r.get("cd_unidade_medida_dose")) or "",
            }}]}]
        if r.get("ie_controle_medico") == 1:
            body.setdefault("extension", []).append({
                "url": "http://tasy.com/fhir/StructureDefinition/controlled-substance",
                "valueBoolean": True,
            })
        sent += 1
        if post_resource(fhir, "MedicationRequest", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("status"):           fc["status"] += 1
            if codings:                      fc["medication"] += 1
            if body.get("subject"):          fc["subject"] += 1
            if body.get("encounter"):        fc["encounter"] += 1
            if body.get("requester"):        fc["requester"] += 1
            if body.get("dosageInstruction"): fc["dosage"] += 1

    print_report("MedicationRequest", total, sent, ok_n, fc)


def seed_charge_items(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V10 — ChargeItem (Itens de Conta)")
    SQL = """
        SELECT cpvi.nr_sequencia, cpvi.nr_interno_conta, cpvi.nr_atendimento,
               cpvi.vl_lancamento_item, cpvi.nr_seq_propaci,
               pp.cd_procedimento, pp.cd_procedimento_tuss,
               pp.qt_procedimento, pp.dt_procedimento, pp.cd_medico_executor,
               ap.cd_pessoa_fisica
        FROM TASY.CONTA_PACIENTE_VALOR_ITEM cpvi
        JOIN TASY.CONTA_PACIENTE cp ON cp.nr_interno_conta = cpvi.nr_interno_conta
        LEFT JOIN TASY.ATENDIMENTO_PACIENTE ap ON ap.nr_atendimento = cpvi.nr_atendimento
        LEFT JOIN TASY.PROCEDIMENTO_PACIENTE pp ON pp.nr_sequencia = cpvi.nr_seq_propaci
        WHERE cp.cd_estabelecimento = :tenant
          AND cpvi.nr_seq_propaci IS NOT NULL
          AND ROWNUM <= :limit
        ORDER BY cpvi.nr_interno_conta DESC, cpvi.nr_sequencia DESC
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"ChargeItem — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "code": 0, "subject": 0, "encounter": 0,
          "occurrenceDateTime": 0, "quantity": 0, "priceOverride": 0}

    for row in rows:
        r = dict(zip(cols, row))
        codings = [{"system": "http://tasy.com/fhir/NamingSystem/procedimento",
                    "code": _str(r.get("cd_procedimento"))}]
        if r.get("cd_procedimento_tuss"):
            codings.append({"system": "http://www.ans.gov.br/fhir/NamingSystem/TUSS",
                             "code": _str(r["cd_procedimento_tuss"])})
        body = {
            "resourceType": "ChargeItem",
            "id": str(r["nr_sequencia"]),
            "status": "billed",
            "code": {"coding": codings},
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"},
            "context": {"reference": f"Encounter/{r['nr_atendimento']}"},
            "occurrenceDateTime": _date(r.get("dt_procedimento")),
            "quantity": {"value": float(r["qt_procedimento"] or 1)},
            "priceOverride": {"value": float(r["vl_lancamento_item"] or 0), "currency": "BRL"},
            "performer": [{"actor": {"reference": f"Practitioner/{r['cd_medico_executor']}"}}]
                          if r.get("cd_medico_executor") else None,
            "extension": [{"url": "http://tasy.com/fhir/StructureDefinition/accountId",
                            "valueInteger": int(r["nr_interno_conta"])}],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None}
        sent += 1
        if post_resource(fhir, "ChargeItem", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("code"):              fc["code"] += 1
            if body.get("subject"):           fc["subject"] += 1
            if body.get("context"):           fc["encounter"] += 1
            if body.get("occurrenceDateTime"): fc["occurrenceDateTime"] += 1
            if body.get("quantity"):          fc["quantity"] += 1
            if body.get("priceOverride"):     fc["priceOverride"] += 1

    print_report("ChargeItem", total, sent, ok_n, fc)


def seed_contract_pricing(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V11/V22 — ChargeItemDefinition (Conversão Proc/Convênio)")
    SQL = """
        SELECT cpc.nr_sequencia, cpc.cd_convenio, cpc.cd_procedimento,
               cpc.ie_origem_proced, cpc.cd_proc_convenio, cpc.ds_proc_convenio,
               cpc.tx_conversao_qtde, cpc.vl_proc_inicial, cpc.vl_proc_final,
               cpc.cd_plano, cpc.dt_inicio_vigencia, cpc.dt_vigencia_final,
               cpc.ie_situacao, cpc.ie_pacote
        FROM TASY.CONVERSAO_PROC_CONVENIO cpc
        WHERE cpc.ie_situacao = 'A'
          AND (cpc.dt_vigencia_final IS NULL OR cpc.dt_vigencia_final >= TRUNC(SYSDATE))
          AND (cpc.cd_estabelecimento IS NULL OR cpc.cd_estabelecimento = :tenant)
          AND ROWNUM <= :limit
        ORDER BY cpc.cd_convenio, cpc.cd_procedimento
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"ChargeItemDefinition (contrato) — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "code": 0, "effectivePeriod": 0, "propertyGroup": 0}

    for row in rows:
        r = dict(zip(cols, row))
        codings = [{"system": "http://tasy.com/fhir/NamingSystem/procedimento",
                    "code": _str(r.get("cd_procedimento"))}]
        if r.get("cd_proc_convenio"):
            codings.append({"system": "http://tasy.com/fhir/NamingSystem/proc-convenio",
                             "code": _str(r["cd_proc_convenio"]),
                             "display": _str(r.get("ds_proc_convenio"))})
        price_components = []
        if r.get("vl_proc_inicial"):
            price_components.append({
                "type": "informational",
                "code": {"coding": [{"code": "initial-price"}]},
                "amount": {"value": float(r["vl_proc_inicial"]), "currency": "BRL"},
            })
        if r.get("vl_proc_final"):
            price_components.append({
                "type": "base",
                "amount": {"value": float(r["vl_proc_final"]), "currency": "BRL"},
            })
        ext = [{"url": "http://tasy.com/fhir/StructureDefinition/convenio",
                "valueInteger": int(r["cd_convenio"])}]
        if r.get("tx_conversao_qtde"):
            ext.append({"url": "http://tasy.com/fhir/extension/txConversaoQtde",
                        "valueDecimal": float(r["tx_conversao_qtde"])})
        if r.get("ie_pacote"):
            ext.append({"url": "http://tasy.com/fhir/extension/isPacote",
                        "valueBoolean": _str(r["ie_pacote"]) == "S"})
        body = {
            "resourceType": "ChargeItemDefinition",
            "id": str(r["nr_sequencia"]),
            "url": f"http://tasy.com/fhir/ChargeItemDefinition/{r['nr_sequencia']}",
            "status": "active",
            "code": {"coding": codings, "text": _str(r.get("ds_proc_convenio"))},
            "effectivePeriod": {
                "start": _date(r.get("dt_inicio_vigencia")),
                "end":   _date(r.get("dt_vigencia_final")),
            },
            "propertyGroup": [{"priceComponent": price_components}] if price_components else [],
            "extension": ext,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "ChargeItemDefinition", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("code"):            fc["code"] += 1
            if body.get("effectivePeriod"): fc["effectivePeriod"] += 1
            if body.get("propertyGroup"):   fc["propertyGroup"] += 1

    print_report("ChargeItemDefinition", total, sent, ok_n, fc)


def seed_claims(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V12 — Claim (Contas / Guias TISS)")
    SQL = """
        SELECT cpg.nr_interno_conta, cpg.cd_autorizacao, cpg.ie_tipo_guia,
               cpg.vl_guia, cpg.vl_convenio, cpg.vl_participante,
               cpg.ie_situacao_guia, cpg.dt_acerto_conta,
               cpg.nr_protocolo_especial,
               cp.nr_atendimento, ap.cd_pessoa_fisica,
               ac.cd_convenio
        FROM TASY.CONTA_PACIENTE_GUIA cpg
        JOIN TASY.CONTA_PACIENTE cp ON cp.nr_interno_conta = cpg.nr_interno_conta
        JOIN TASY.ATENDIMENTO_PACIENTE ap ON ap.nr_atendimento = cp.nr_atendimento
        LEFT JOIN TASY.AUTORIZACAO_CONVENIO ac ON ac.cd_autorizacao = cpg.cd_autorizacao
        WHERE cp.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY cpg.nr_interno_conta DESC
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Claim — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "status": 0, "total": 0, "patient": 0,
          "insurer": 0, "encounter": 0, "identifier[auth]": 0}

    for row in rows:
        r = dict(zip(cols, row))
        claim_id = _fhir_id(r['nr_interno_conta'], r['cd_autorizacao'])
        extensions = [{"url": "http://tasy.com/fhir/StructureDefinition/accountId",
                       "valueInteger": int(r["nr_interno_conta"])}]
        if r.get("nr_protocolo_especial"):
            extensions.append({"url": "http://tasy.com/fhir/extension/protocoloEspecial",
                                "valueString": _str(r["nr_protocolo_especial"])})
        if r.get("vl_convenio"):
            extensions.append({"url": "http://tasy.com/fhir/StructureDefinition/approvedAmount",
                                "valueMoney": {"value": float(r["vl_convenio"]), "currency": "BRL"}})
        if r.get("vl_participante"):
            extensions.append({"url": "http://tasy.com/fhir/StructureDefinition/copay",
                                "valueMoney": {"value": float(r["vl_participante"]), "currency": "BRL"}})
        body = {
            "resourceType": "Claim",
            "id": claim_id,
            "status": "active",
            "type": {"coding": [{"system": "http://tasy.com/fhir/NamingSystem/tipoGuia",
                                   "code": _str(r.get("ie_tipo_guia")) or ""}]},
            "use": "claim",
            "patient": {"reference": f"Patient/{r['cd_pessoa_fisica']}"},
            "created": _date(r.get("dt_acerto_conta")) or datetime.now().isoformat(),
            "insurer": {"identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                        "value": str(r["cd_convenio"])}},
            "insurance": [{"sequence": 1, "focal": True,
                            "coverage": {"reference": f"Coverage/{r['cd_pessoa_fisica']}-{r['cd_convenio']}"}}],
            "identifier": [{"system": "http://tasy.com/fhir/identifier/autorizacao",
                             "value": _str(r.get("cd_autorizacao"))}],
            "total": {"value": float(r["vl_guia"] or 0), "currency": "BRL"},
            "extension": extensions,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        if r.get("nr_atendimento"):
            body["encounter"] = [{"reference": f"Encounter/{r['nr_atendimento']}"}]
        sent += 1
        if post_resource(fhir, "Claim", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("status"):    fc["status"] += 1
            if body.get("total"):     fc["total"] += 1
            if body.get("patient"):   fc["patient"] += 1
            if body.get("insurer"):   fc["insurer"] += 1
            if body.get("encounter"): fc["encounter"] += 1
            if body["identifier"][0].get("value"): fc["identifier[auth]"] += 1

    print_report("Claim", total, sent, ok_n, fc)


def seed_claim_responses_retorno(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V14 — ClaimResponse/retorno (Retorno do Convênio)")
    SQL = """
        SELECT cr.nr_sequencia, cr.cd_convenio, cr.cd_estabelecimento,
               cr.dt_retorno, cr.ie_status_retorno, cr.ds_lote_convenio,
               cr.dt_inicial, cr.dt_final, cr.dt_pagamento,
               cr.dt_limite_glosa, cr.vl_rateio_glosa, cr.ie_tipo_glosa
        FROM TASY.CONVENIO_RETORNO cr
        WHERE cr.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY cr.dt_retorno DESC
    """
    OUTCOME_MAP = {"A": "complete", "P": "partial", "G": "error", "F": "complete"}
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"ClaimResponse/retorno — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "outcome": 0, "insurer": 0, "created": 0,
          "identifier[lote]": 0, "total[denied]": 0}

    for row in rows:
        r = dict(zip(cols, row))
        status_val = _str(r.get("ie_status_retorno")) or ""
        extensions = []
        if r.get("dt_inicial"):
            extensions.append({"url": "http://tasy.com/fhir/extension/periodoInicial",
                                "valueDate": _date(r["dt_inicial"])})
        if r.get("dt_final"):
            extensions.append({"url": "http://tasy.com/fhir/extension/periodoFinal",
                                "valueDate": _date(r["dt_final"])})
        if r.get("ie_tipo_glosa"):
            extensions.append({"url": "http://tasy.com/fhir/extension/tipoGlosa",
                                "valueString": _str(r["ie_tipo_glosa"])})
        if r.get("dt_pagamento"):
            extensions.append({"url": "http://tasy.com/fhir/extension/paymentDate",
                                "valueDate": _date(r["dt_pagamento"])})
        if r.get("dt_limite_glosa"):
            extensions.append({"url": "http://tasy.com/fhir/extension/appealDeadline",
                                "valueDate": _date(r["dt_limite_glosa"])})
        totals = []
        if r.get("vl_rateio_glosa"):
            totals.append({"category": {"coding": [{"code": "denied"}]},
                            "amount": {"value": float(r["vl_rateio_glosa"]), "currency": "BRL"}})
        body = {
            "resourceType": "ClaimResponse",
            "id": f"ret-{r['nr_sequencia']}",
            "status": "active",
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type",
                                   "code": "institutional"}]},
            "use": "claim",
            "outcome": OUTCOME_MAP.get(status_val, "queued"),
            "created": _date(r.get("dt_retorno")) or datetime.now().isoformat(),
            "insurer": {"identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                        "value": str(r["cd_convenio"])}},
            "identifier": [{"system": "http://tasy.com/fhir/identifier/lote-retorno",
                             "value": _str(r.get("ds_lote_convenio"))}] if r.get("ds_lote_convenio") else [],
            "total": totals,
            "extension": extensions,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "ClaimResponse", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("outcome"):  fc["outcome"] += 1
            if body.get("insurer"):  fc["insurer"] += 1
            if body.get("created"):  fc["created"] += 1
            if body.get("identifier"): fc["identifier[lote]"] += 1
            if totals:               fc["total[denied]"] += 1

    print_report("ClaimResponse/retorno", total, sent, ok_n, fc)


def seed_payment_notices(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V16 — PaymentNotice (Liquidações de Títulos)")
    SQL = """
        SELECT trl.nr_titulo, trl.nr_sequencia,
               trl.dt_recebimento, trl.vl_recebido,
               trl.vl_descontos, trl.vl_juros, trl.vl_multa, trl.vl_glosa,
               trl.vl_recebido - trl.vl_descontos + trl.vl_juros + trl.vl_multa AS vl_liquido,
               trl.nr_documento, trl.nr_externo, trl.cd_banco,
               trl.dt_credito_banco, trl.nr_seq_retorno, trl.ie_acao,
               tr.nr_atendimento, tr.cd_convenio_conta, tr.cd_pessoa_fisica
        FROM TASY.TITULO_RECEBER_LIQ trl
        JOIN TASY.TITULO_RECEBER tr ON tr.nr_titulo = trl.nr_titulo
        JOIN TASY.ATENDIMENTO_PACIENTE ap ON ap.nr_atendimento = tr.nr_atendimento
        WHERE ap.cd_estabelecimento = :tenant
          AND tr.nr_atendimento IS NOT NULL
          AND ROWNUM <= :limit
        ORDER BY trl.dt_recebimento DESC
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"PaymentNotice — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "status": 0, "amount": 0, "paymentDate": 0,
          "request": 0, "identifier[nossoNumero]": 0}

    for row in rows:
        r = dict(zip(cols, row))
        extensions = []
        for ext_name, field in [("discount", "vl_descontos"), ("interest", "vl_juros"),
                                  ("penalty", "vl_multa"), ("glosaAmount", "vl_glosa")]:
            if r.get(field) is not None:
                extensions.append({"url": f"http://tasy.com/fhir/extension/{ext_name}",
                                    "valueMoney": {"value": float(r[field]), "currency": "BRL"}})
        if r.get("cd_banco"):
            extensions.append({"url": "http://tasy.com/fhir/extension/bankCode",
                                "valueInteger": int(r["cd_banco"])})
        if r.get("dt_credito_banco"):
            extensions.append({"url": "http://tasy.com/fhir/extension/creditDate",
                                "valueDate": _date(r["dt_credito_banco"])})
        if r.get("nr_atendimento"):
            extensions.append({"url": "http://tasy.com/fhir/extension/encounterId",
                                "valueInteger": int(r["nr_atendimento"])})
        if r.get("ie_acao"):
            extensions.append({"url": "http://tasy.com/fhir/extension/acaoType",
                                "valueString": _str(r["ie_acao"])})
        identifiers = []
        if r.get("nr_documento"):
            identifiers.append({"system": "http://tasy.com/fhir/identifier/nossoNumero",
                                  "value": _str(r["nr_documento"])})
        if r.get("nr_externo"):
            identifiers.append({"system": "http://tasy.com/fhir/identifier/seuNumero",
                                  "value": _str(r["nr_externo"])})
        body = {
            "resourceType": "PaymentNotice",
            "id": f"{r['nr_titulo']}-{r['nr_sequencia']}",
            "status": "active",
            "request": {"reference": f"Invoice/{r['nr_titulo']}"},
            "created": _date(r.get("dt_recebimento")) or datetime.now().isoformat(),
            "paymentDate": _date(r.get("dt_recebimento")),
            "payment": {"reference": f"PaymentReconciliation/rec-{r.get('nr_seq_retorno', r['nr_titulo'])}"}
                        if r.get("nr_seq_retorno") else None,
            "amount": {"value": float(r["vl_recebido"] or 0), "currency": "BRL"},
            "identifier": identifiers,
            "extension": extensions,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "PaymentNotice", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("status"):      fc["status"] += 1
            if body.get("amount"):      fc["amount"] += 1
            if body.get("paymentDate"): fc["paymentDate"] += 1
            if body.get("request"):     fc["request"] += 1
            if identifiers:             fc["identifier[nossoNumero]"] += 1

    print_report("PaymentNotice", total, sent, ok_n, fc)


def seed_invoices(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V17 — Invoice (Títulos a Receber)")
    SQL = """
        SELECT tr.nr_titulo, tr.nr_atendimento, tr.nr_interno_conta,
               tr.cd_convenio_conta, tr.cd_pessoa_fisica,
               tr.vl_titulo, tr.vl_saldo_titulo,
               tr.dt_vencimento, tr.dt_emissao, tr.ie_situacao, tr.ie_tipo_titulo,
               CASE
                 WHEN tr.ie_situacao = 'A' AND tr.dt_vencimento < TRUNC(SYSDATE)
                 THEN TRUNC(SYSDATE) - tr.dt_vencimento ELSE 0
               END AS dias_atraso,
               CASE
                 WHEN tr.dt_vencimento >= TRUNC(SYSDATE) THEN 'corrente'
                 WHEN TRUNC(SYSDATE) - tr.dt_vencimento <= 30  THEN '1-30'
                 WHEN TRUNC(SYSDATE) - tr.dt_vencimento <= 60  THEN '31-60'
                 WHEN TRUNC(SYSDATE) - tr.dt_vencimento <= 90  THEN '61-90'
                 ELSE '90+'
               END AS aging_bucket
        FROM TASY.TITULO_RECEBER tr
        JOIN TASY.ATENDIMENTO_PACIENTE ap ON ap.nr_atendimento = tr.nr_atendimento
        WHERE ap.cd_estabelecimento = :tenant
          AND tr.nr_atendimento IS NOT NULL
          AND ROWNUM <= :limit
        ORDER BY tr.dt_vencimento DESC
    """
    STATUS_MAP = {"A": "active", "P": "balanced", "C": "cancelled", "B": "cancelled"}
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Invoice — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "status": 0, "totalGross": 0, "totalNet": 0,
          "date": 0, "recipient": 0, "extension[aging]": 0}

    for row in rows:
        r = dict(zip(cols, row))
        body = {
            "resourceType": "Invoice",
            "id": str(r["nr_titulo"]),
            "status": STATUS_MAP.get(_str(r.get("ie_situacao")) or "", "issued"),
            "date": _date(r.get("dt_emissao")),
            "recipient": {"identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                          "value": str(r["cd_convenio_conta"])}} if r.get("cd_convenio_conta") else None,
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
            "totalGross": {"value": float(r["vl_titulo"] or 0), "currency": "BRL"},
            "totalNet":   {"value": float(r["vl_saldo_titulo"] or 0), "currency": "BRL"},
            "extension": [
                {"url": "http://tasy.com/fhir/extension/agingBucket",
                 "valueString": _str(r.get("aging_bucket"))},
                {"url": "http://tasy.com/fhir/extension/daysOverdue",
                 "valueInteger": int(r.get("dias_atraso") or 0)},
                {"url": "http://tasy.com/fhir/extension/dtVencimento",
                 "valueDate": _date(r.get("dt_vencimento"))} if r.get("dt_vencimento") else None,
                {"url": "http://tasy.com/fhir/extension/encounterId",
                 "valueInteger": int(r["nr_atendimento"])} if r.get("nr_atendimento") else None,
                {"url": "http://tasy.com/fhir/extension/nrInternoConta",
                 "valueInteger": int(r["nr_interno_conta"])} if r.get("nr_interno_conta") else None,
                {"url": "http://tasy.com/fhir/extension/tipoTitulo",
                 "valueString": _str(r["ie_tipo_titulo"])} if r.get("ie_tipo_titulo") else None,
            ],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None}
        sent += 1
        if post_resource(fhir, "Invoice", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("status"):     fc["status"] += 1
            if body.get("totalGross"): fc["totalGross"] += 1
            if body.get("totalNet"):   fc["totalNet"] += 1
            if body.get("date"):       fc["date"] += 1
            if body.get("recipient"):  fc["recipient"] += 1
            fc["extension[aging]"] += 1

    print_report("Invoice", total, sent, ok_n, fc)


def seed_tiss_guides(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V18 — Claim/TISS (Guias TISS geradas — TISS_GUIA)")
    SQL = """
        SELECT tg.nr_sequencia, tg.cd_ans, tg.cd_autorizacao, tg.cd_senha,
               tg.dt_validade_senha, tg.dt_emissao_guia,
               tg.nr_interno_conta, tg.nr_seq_protocolo, tg.nr_sequencia_autor,
               cp.nr_atendimento, ap.cd_pessoa_fisica
        FROM TASY.TISS_GUIA tg
        JOIN TASY.CONTA_PACIENTE cp ON cp.nr_interno_conta = tg.nr_interno_conta
        JOIN TASY.ATENDIMENTO_PACIENTE ap ON ap.nr_atendimento = cp.nr_atendimento
        WHERE cp.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY tg.dt_emissao_guia DESC
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Claim/TISS — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "insurer[ans]": 0, "preAuthRef": 0, "created": 0, "patient": 0}

    for row in rows:
        r = dict(zip(cols, row))
        extensions = []
        if r.get("cd_senha"):
            extensions.append({"url": "http://tasy.com/fhir/extension/senha",
                                "valueString": _str(r["cd_senha"])})
        if r.get("dt_validade_senha"):
            extensions.append({"url": "http://tasy.com/fhir/extension/senhaValidade",
                                "valueDate": _date(r["dt_validade_senha"])})
        if r.get("nr_sequencia_autor"):
            extensions.append({"url": "http://tasy.com/fhir/extension/nrSequenciaAutor",
                                "valueInteger": int(r["nr_sequencia_autor"])})
        if r.get("nr_interno_conta"):
            extensions.append({"url": "http://tasy.com/fhir/extension/nrInternoConta",
                                "valueInteger": int(r["nr_interno_conta"])})
        body = {
            "resourceType": "Claim",
            "id": f"tiss-{r['nr_sequencia']}",
            "status": "active",
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type",
                                   "code": "institutional"}]},
            "use": "claim",
            "patient": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
            "created": _date(r.get("dt_emissao_guia")) or datetime.now().isoformat(),
            "insurer": {"identifier": {"system": "http://tasy.com/fhir/identifier/ans",
                                        "value": _str(r.get("cd_ans"))}},
            "insurance": [{"sequence": 1, "focal": True,
                            "coverage": {"reference": f"Coverage/{r['cd_pessoa_fisica']}-{r['cd_convenio']}"}}]
                         if r.get("cd_convenio") else [],
            "preAuthRef": [_str(r.get("cd_autorizacao"))] if r.get("cd_autorizacao") else [],
            "extension": extensions,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "Claim", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("insurer"):    fc["insurer[ans]"] += 1
            if body.get("preAuthRef"): fc["preAuthRef"] += 1
            if body.get("created"):    fc["created"] += 1
            if body.get("patient"):    fc["patient"] += 1

    print_report("Claim/TISS", total, sent, ok_n, fc)


def seed_tasks(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V19 — Task (Protocolos de Envio TISS — PROTOCOLO_CONVENIO)")
    # DDL de PROTOCOLO_CONVENIO não confirmado — apenas PK nr_seq_protocolo é certa via FK.
    # Query esqueleto: falha graciosamente se colunas não existirem.
    # Tenta colunas mais completas primeiro; recua para versão mínima se falhar.
    SQL_FULL = """
        SELECT pc.nr_seq_protocolo, pc.cd_convenio, pc.nr_protocolo,
               pc.dt_envio, pc.ie_situacao
        FROM TASY.PROTOCOLO_CONVENIO pc
        WHERE ROWNUM <= :limit
        ORDER BY pc.nr_seq_protocolo DESC
    """
    SQL_MIN = """
        SELECT pc.nr_seq_protocolo, pc.cd_convenio
        FROM TASY.PROTOCOLO_CONVENIO pc
        WHERE ROWNUM <= :limit
        ORDER BY pc.nr_seq_protocolo DESC
    """
    cur = ora.cursor()
    for SQL in (SQL_FULL, SQL_MIN):
        try:
            cur.execute(SQL, limit=limit)
            break
        except Exception as e:
            warn(f"Task/PROTOCOLO_CONVENIO — tentativa falhou: {e}")
    else:
        warn("Confirme colunas: SELECT COLUMN_NAME FROM ALL_TAB_COLUMNS WHERE TABLE_NAME='PROTOCOLO_CONVENIO' AND OWNER='TASY'")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    TASK_STATUS = {"E": "in-progress", "F": "completed", "C": "cancelled"}
    sent = ok_n = 0
    fc = {"id": 0, "status": 0, "identifier": 0, "executionPeriod": 0}

    for row in rows:
        r = dict(zip(cols, row))
        body = {
            "resourceType": "Task",
            "id": str(r["nr_seq_protocolo"]),
            "status": TASK_STATUS.get(_str(r.get("ie_situacao")) or "", "requested"),
            "intent": "order",
            "identifier": [{"system": "http://tasy.com/fhir/identifier/protocolo-tiss",
                             "value": _str(r.get("nr_protocolo"))}] if r.get("nr_protocolo") else [],
            "executionPeriod": {"start": _date(r.get("dt_envio"))} if r.get("dt_envio") else None,
            "for": {"identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                    "value": str(r["cd_convenio"])}} if r.get("cd_convenio") else None,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "Task", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("status"):          fc["status"] += 1
            if body.get("identifier"):      fc["identifier"] += 1
            if body.get("executionPeriod"): fc["executionPeriod"] += 1

    print_report("Task", total, sent, ok_n, fc)


def seed_appeals(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V20 — ClaimResponse/appeal (Recursos de Glosa — TISS_RECURSO_GLOSA_PROT)")
    SQL = """
        SELECT rg.nr_sequencia, rg.nr_lote_rec_glosa, rg.nr_protocolo,
               rg.nr_seq_protocolo, rg.cd_convenio, rg.cd_prestador,
               rg.nm_prestador, rg.vl_total_recursado,
               rg.ie_status_integracao, rg.ie_enviado_operadora,
               rg.dt_envio_operadora, rg.dt_cancelamento
        FROM TASY.TISS_RECURSO_GLOSA_PROT rg
        WHERE ROWNUM <= :limit
        ORDER BY rg.dt_envio_operadora DESC NULLS LAST
    """
    OUTCOME_MAP = {"E": "queued", "F": "complete", "C": "error"}
    cur = ora.cursor()
    try:
        cur.execute(SQL, limit=limit)
    except Exception as e:
        warn(f"ClaimResponse/appeal — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "outcome": 0, "insurer": 0, "preAuthRef": 0, "total": 0}

    for row in rows:
        r = dict(zip(cols, row))
        status_val = _str(r.get("ie_status_integracao")) or ""
        appeal_ext = []
        if r.get("ie_enviado_operadora"):
            appeal_ext.append({"url": "http://tasy.com/fhir/extension/enviadoOperadora",
                                "valueString": _str(r["ie_enviado_operadora"])})
        if r.get("dt_cancelamento"):
            appeal_ext.append({"url": "http://tasy.com/fhir/extension/dtCancelamento",
                                "valueDate": _date(r["dt_cancelamento"])})
        body = {
            "resourceType": "ClaimResponse",
            "id": f"appeal-{r['nr_sequencia']}",
            "status": "active",
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type",
                                   "code": "institutional"}]},
            "use": "preauthorization",
            "outcome": OUTCOME_MAP.get(status_val, "queued"),
            "created": _date(r.get("dt_envio_operadora")) or datetime.now().isoformat(),
            "insurer": {"identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                        "value": str(r["cd_convenio"])}} if r.get("cd_convenio") else None,
            "requestor": {"identifier": {"system": "http://tasy.com/fhir/identifier/prestador",
                                          "value": _str(r["cd_prestador"])},
                           "display": _str(r.get("nm_prestador"))} if r.get("cd_prestador") else None,
            "identifier": [{"system": "http://tasy.com/fhir/identifier/protocolo-recurso",
                             "value": _str(r["nr_protocolo"])}] if r.get("nr_protocolo") else [],
            "preAuthRef": _str(r.get("nr_lote_rec_glosa")),
            "total": [{"category": {"coding": [{"code": "benefit"}]},
                        "amount": {"value": float(r["vl_total_recursado"]), "currency": "BRL"}}]
                     if r.get("vl_total_recursado") else [],
            "extension": appeal_ext if appeal_ext else None,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "ClaimResponse", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("outcome"):    fc["outcome"] += 1
            if body.get("insurer"):    fc["insurer"] += 1
            if body.get("preAuthRef"): fc["preAuthRef"] += 1
            if body.get("total"):      fc["total"] += 1

    print_report("ClaimResponse/appeal", total, sent, ok_n, fc)


def seed_payment_reconciliations(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("V23 — PaymentReconciliation (Reconciliação por Período)")
    SQL = """
        SELECT * FROM (
            SELECT TRUNC(trl.dt_recebimento, 'MM')  AS dt_periodo_ini,
                   LAST_DAY(trl.dt_recebimento)      AS dt_periodo_fim,
                   SUM(trl.vl_recebido)              AS vl_recebido,
                   SUM(trl.vl_descontos)             AS vl_descontos,
                   SUM(trl.vl_glosa)                 AS vl_glosado,
                   COUNT(*)                          AS qt_liquidacoes,
                   COUNT(DISTINCT trl.nr_titulo)     AS qt_titulos
            FROM TASY.TITULO_RECEBER_LIQ trl
            JOIN TASY.TITULO_RECEBER tr ON tr.nr_titulo = trl.nr_titulo
            JOIN TASY.ATENDIMENTO_PACIENTE ap ON ap.nr_atendimento = tr.nr_atendimento
            WHERE ap.cd_estabelecimento = :tenant
              AND tr.nr_atendimento IS NOT NULL
            GROUP BY TRUNC(trl.dt_recebimento, 'MM'), LAST_DAY(trl.dt_recebimento)
            ORDER BY dt_periodo_ini DESC
        ) WHERE ROWNUM <= :limit
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"PaymentReconciliation — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"id": 0, "status": 0, "period": 0, "paymentAmount": 0, "detail": 0}

    for row in rows:
        r = dict(zip(cols, row))
        period_id = _date(r.get("dt_periodo_ini", ""))
        rec_id = f"rec-{period_id.replace('-', '')[:6]}" if period_id else f"rec-{sent}"
        body = {
            "resourceType": "PaymentReconciliation",
            "id": rec_id,
            "status": "active",
            "period": {
                "start": _date(r.get("dt_periodo_ini")),
                "end":   _date(r.get("dt_periodo_fim")),
            },
            "created": datetime.now().isoformat(),
            "paymentAmount": {"value": float(r["vl_recebido"] or 0), "currency": "BRL"},
            "detail": [
                {"type": {"coding": [{"code": "payment"}]},
                 "amount": {"value": float(r["vl_recebido"] or 0), "currency": "BRL"}},
            ],
            "extension": [
                {"url": "http://tasy.com/fhir/extension/paymentCount",
                 "valueInteger": int(r.get("qt_liquidacoes") or 0)},
                {"url": "http://tasy.com/fhir/extension/invoiceCount",
                 "valueInteger": int(r.get("qt_titulos") or 0)},
                {"url": "http://tasy.com/fhir/extension/glosaAmount",
                 "valueMoney": {"value": float(r.get("vl_glosado") or 0), "currency": "BRL"}},
            ],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None}
        sent += 1
        if post_resource(fhir, "PaymentReconciliation", body, dry_run):
            ok_n += 1
            fc["id"] += 1
            if body.get("status"):        fc["status"] += 1
            if body.get("period"):        fc["period"] += 1
            if body.get("paymentAmount"): fc["paymentAmount"] += 1
            if body.get("detail"):        fc["detail"] += 1

    print_report("PaymentReconciliation", total, sent, ok_n, fc)


# ── Grupo 1 — Adapters existentes sem seed até agora ─────────────────────────

def seed_observations(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("OBS — Observation (Sinais Vitais — SINAL_VITAL)")
    # SINAL_VITAL não tem CD_ESTABELECIMENTO; filtra via JOIN com ATENDIMENTO_PACIENTE.
    SQL = """
        SELECT sv.nr_sinal_vital, sv.nr_atendimento,
               sv.tp_sinal, sv.vl_medida, sv.un_medida,
               sv.vl_sistolica, sv.vl_diastolica,
               sv.dt_registro, sv.nm_profissional,
               ap.cd_pessoa_fisica
        FROM sinal_vital sv
        JOIN atendimento_paciente ap ON ap.nr_atendimento = sv.nr_atendimento
        WHERE ap.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY sv.nr_sinal_vital DESC
    """
    LOINC = {
        "HR":     ("8867-4",  "/min",    "Heart rate"),
        "BP":     ("85354-9", "mm[Hg]",  "Blood pressure panel"),
        "BP_SYS": ("8480-6",  "mm[Hg]",  "Systolic blood pressure"),
        "BP_DIA": ("8462-4",  "mm[Hg]",  "Diastolic blood pressure"),
        "TEMP":   ("8310-5",  "Cel",     "Body temperature"),
        "SPO2":   ("2708-6",  "%",       "Oxygen saturation"),
        "RR":     ("9279-1",  "/min",    "Respiratory rate"),
        "WEIGHT": ("29463-7", "kg",      "Body weight"),
        "HEIGHT": ("8302-2",  "cm",      "Body height"),
        "PAIN":   ("72514-3", "{score}", "Pain severity"),
    }
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Observation/SINAL_VITAL — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    category = [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                               "code": "vital-signs", "display": "Vital Signs"}]}]
    sent = ok_n = 0
    fc = {"status": 0, "code[loinc]": 0, "subject": 0, "encounter": 0,
          "effectiveDateTime": 0, "value": 0, "performer": 0}

    for row in rows:
        r = dict(zip(cols, row))
        tp = (_str(r.get("tp_sinal")) or "").upper()
        loinc_code, loinc_unit, loinc_display = LOINC.get(tp, (tp or "unknown", "1", tp or "Unknown"))

        if tp in ("BP", "BP_SYS") and (r.get("vl_sistolica") or r.get("vl_diastolica")):
            components = []
            for cval, ccode, cdisplay in [
                (r.get("vl_sistolica"),  "8480-6", "Systolic blood pressure"),
                (r.get("vl_diastolica"), "8462-4", "Diastolic blood pressure"),
            ]:
                if cval is not None:
                    components.append({
                        "code": {"coding": [{"system": "http://loinc.org",
                                              "code": ccode, "display": cdisplay}]},
                        "valueQuantity": {"value": float(cval), "unit": "mm[Hg]",
                                           "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
                    })
            body = {
                "resourceType": "Observation",
                "id": str(r["nr_sinal_vital"]),
                "status": "final",
                "category": category,
                "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9",
                                      "display": "Blood pressure panel"}]},
                "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
                "encounter": {"reference": f"Encounter/{r['nr_atendimento']}"} if r.get("nr_atendimento") else None,
                "effectiveDateTime": _date(r.get("dt_registro")),
                "component": components,
                "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
            }
        else:
            vq = None
            if r.get("vl_medida") is not None:
                unit = loinc_unit or _str(r.get("un_medida")) or "1"
                vq = {"value": float(r["vl_medida"]), "unit": unit,
                      "system": "http://unitsofmeasure.org", "code": unit}
            body = {
                "resourceType": "Observation",
                "id": str(r["nr_sinal_vital"]),
                "status": "final",
                "category": category,
                "code": {"coding": [{"system": "http://loinc.org",
                                      "code": loinc_code, "display": loinc_display}]},
                "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
                "encounter": {"reference": f"Encounter/{r['nr_atendimento']}"} if r.get("nr_atendimento") else None,
                "effectiveDateTime": _date(r.get("dt_registro")),
                "valueQuantity": vq,
                "performer": [{"display": _str(r["nm_profissional"])}] if r.get("nm_profissional") else [],
                "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
            }

        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "Observation", body, dry_run):
            ok_n += 1
            if body.get("status"):                                fc["status"] += 1
            if body["code"]["coding"][0].get("code"):             fc["code[loinc]"] += 1
            if body.get("subject"):                               fc["subject"] += 1
            if body.get("encounter"):                             fc["encounter"] += 1
            if body.get("effectiveDateTime"):                     fc["effectiveDateTime"] += 1
            if body.get("valueQuantity") or body.get("component"): fc["value"] += 1
            if body.get("performer"):                             fc["performer"] += 1

    print_report("Observation", total, sent, ok_n, fc)


def seed_risk_assessments(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("RISK — RiskAssessment (Scores Clínicos — AVALIACAO_RISCO)")
    SQL = """
        SELECT ar.nr_avaliacao, ar.nr_atendimento,
               ar.cd_escala, ar.ds_escala, ar.vl_pontuacao,
               ar.ds_classificacao, ar.ie_risco,
               ar.dt_avaliacao, ar.cd_profissional,
               ap.cd_pessoa_fisica
        FROM avaliacao_risco ar
        JOIN atendimento_paciente ap ON ap.nr_atendimento = ar.nr_atendimento
        WHERE ap.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY ar.nr_avaliacao DESC
    """
    RISK_SEV = {"A": "high", "M": "moderate", "B": "low"}
    SNOMED = {
        "EWS": "1104051000000101", "NEWS": "450361006", "NEWS2": "450361006",
        "SOFA": "445420000", "QSOFA": "445420000",
        "BRADEN": "225338004", "MORSE": "225338004",
    }
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"RiskAssessment — query falhou: {e}")
        warn("Confirme: SELECT COLUMN_NAME FROM ALL_TAB_COLUMNS WHERE TABLE_NAME='AVALIACAO_RISCO' AND OWNER=USER")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "code": 0, "subject": 0, "encounter": 0,
          "occurrenceDateTime": 0, "prediction": 0}

    for row in rows:
        r = dict(zip(cols, row))
        escala = (_str(r.get("cd_escala")) or "").upper()
        codings = []
        if escala in SNOMED:
            codings.append({"system": "http://snomed.info/sct", "code": SNOMED[escala],
                             "display": _str(r.get("ds_escala")) or escala})
        codings.append({"system": "http://tasy.com/fhir/CodeSystem/escala-risco",
                        "code": escala or "UNKNOWN",
                        "display": _str(r.get("ds_escala")) or escala})

        score = r.get("vl_pontuacao")
        prediction = {}
        if r.get("ds_classificacao"):
            prediction["outcome"] = {"text": _str(r["ds_classificacao"])}
        if score is not None:
            prediction["extension"] = [{"url": "http://tasy.com/fhir/extension/score-value",
                                         "valueDecimal": float(score)}]

        risco = (_str(r.get("ie_risco")) or "").upper()
        extensions = []
        if risco:
            extensions.append({"url": "http://tasy.com/fhir/extension/nivel-risco",
                                "valueCode": RISK_SEV.get(risco, risco.lower())})
        if score is not None:
            extensions.append({"url": "http://tasy.com/fhir/extension/pontuacao",
                                "valueDecimal": float(score)})

        body = {
            "resourceType": "RiskAssessment",
            "id": str(r["nr_avaliacao"]),
            "status": "final",
            "code": {"coding": codings},
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
            "encounter": {"reference": f"Encounter/{r['nr_atendimento']}"} if r.get("nr_atendimento") else None,
            "occurrenceDateTime": _date(r.get("dt_avaliacao")),
            "prediction": [prediction] if prediction else [],
            "extension": extensions,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "RiskAssessment", body, dry_run):
            ok_n += 1
            if body.get("status"):             fc["status"] += 1
            if body.get("code"):               fc["code"] += 1
            if body.get("subject"):            fc["subject"] += 1
            if body.get("encounter"):          fc["encounter"] += 1
            if body.get("occurrenceDateTime"): fc["occurrenceDateTime"] += 1
            if body.get("prediction"):         fc["prediction"] += 1

    print_report("RiskAssessment", total, sent, ok_n, fc)


def seed_detected_issues(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("DI — DetectedIssue (Interações Medicamentosas — INTERACAO_MEDICAMENTOSA)")
    SQL = """
        SELECT im.nr_interacao,
               im.ie_tipo, im.ie_gravidade, im.ie_situacao,
               im.cd_medicamento_1, im.nm_medicamento_1, im.nr_prescricao_1,
               im.cd_medicamento_2, im.nm_medicamento_2, im.nr_prescricao_2,
               im.ds_interacao, im.ds_mitigacao, im.dt_deteccao,
               pm.nr_atendimento, ap.cd_pessoa_fisica
        FROM interacao_medicamentosa im
        JOIN prescr_medica pm ON pm.nr_prescricao = im.nr_prescricao_1
        JOIN atendimento_paciente ap ON ap.nr_atendimento = pm.nr_atendimento
        WHERE ap.cd_estabelecimento = :tenant
          AND im.ie_situacao != 'X'
          AND ROWNUM <= :limit
        ORDER BY im.nr_interacao DESC
    """
    TYPE_MAP = {
        "DD": ("DRG",     "Drug-Drug Interaction"),
        "DA": ("ALG",     "Drug-Allergy Interaction"),
        "DF": ("FOOD",    "Drug-Food Interaction"),
        "DT": ("DUPTHPY", "Duplicate Therapy"),
    }
    SEV_MAP    = {"A": "high", "M": "moderate", "B": "low"}
    STATUS_MAP = {"R": "registered", "P": "preliminary", "F": "final"}

    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"DetectedIssue — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "code": 0, "severity": 0, "patient": 0,
          "identifiedDateTime": 0, "implicated": 0, "detail": 0}

    for row in rows:
        r = dict(zip(cols, row))
        tipo   = (_str(r.get("ie_tipo"))      or "DD").upper()
        sev    = SEV_MAP.get((_str(r.get("ie_gravidade")) or "").upper(), "moderate")
        status = STATUS_MAP.get((_str(r.get("ie_situacao")) or "F").upper(), "final")
        act_code, act_display = TYPE_MAP.get(tipo, ("DRG", "Drug Interaction"))

        implicated = []
        if r.get("nr_prescricao_1"):
            implicated.append({"reference": f"MedicationRequest/{r['nr_prescricao_1']}-{r.get('cd_medicamento_1', 0)}"})
        if r.get("nr_prescricao_2"):
            implicated.append({"reference": f"MedicationRequest/{r['nr_prescricao_2']}-{r.get('cd_medicamento_2', 0)}"})

        detail_parts = [p for p in [
            _str(r.get("nm_medicamento_1")),
            _str(r.get("nm_medicamento_2")),
            _str(r.get("ds_interacao")),
        ] if p]

        body = {
            "resourceType": "DetectedIssue",
            "id": str(r["nr_interacao"]),
            "status": status,
            "code": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                                   "code": act_code, "display": act_display}]},
            "severity": sev,
            "patient": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
            "implicated": implicated,
            "identifiedDateTime": _date(r.get("dt_deteccao")),
            "detail": " | ".join(detail_parts) if detail_parts else None,
            "mitigation": [{"action": {"text": _str(r["ds_mitigacao"])}}] if r.get("ds_mitigacao") else [],
            "extension": [{"url": "http://tasy.com/fhir/extension/encounter",
                           "valueReference": {"reference": f"Encounter/{r['nr_atendimento']}"}}]
                         if r.get("nr_atendimento") else [],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "DetectedIssue", body, dry_run):
            ok_n += 1
            if body.get("status"):             fc["status"] += 1
            if body.get("code"):               fc["code"] += 1
            if body.get("severity"):           fc["severity"] += 1
            if body.get("patient"):            fc["patient"] += 1
            if body.get("identifiedDateTime"): fc["identifiedDateTime"] += 1
            if implicated:                     fc["implicated"] += 1
            if body.get("detail"):             fc["detail"] += 1

    print_report("DetectedIssue", total, sent, ok_n, fc)


def seed_medication_dispenses(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("DISP — MedicationDispense (Dispensação — DISPENSACAO)")
    SQL = """
        SELECT d.nr_dispensacao, d.nr_prescricao, d.nr_atendimento,
               d.nm_medicamento, d.cd_anvisa, d.cd_dcb,
               d.qt_dispensada, d.ds_unidade, d.nr_dias_fornecimento,
               d.dt_preparacao, d.dt_entrega, d.ie_situacao,
               d.ie_substituicao, d.ds_posologia, d.via_administracao,
               d.nr_crf, d.nm_farmaceutico,
               ap.cd_pessoa_fisica
        FROM dispensacao d
        JOIN atendimento_paciente ap ON ap.nr_atendimento = d.nr_atendimento
        WHERE ap.cd_estabelecimento = :tenant
          AND d.ie_situacao != 'X'
          AND ROWNUM <= :limit
        ORDER BY d.nr_dispensacao DESC
    """
    STATUS_MAP = {"P": "preparation", "E": "in-progress", "C": "completed", "R": "declined"}
    ROUTE_MAP  = {
        "VO": "26643006", "IV": "47625008", "IM": "78421000",
        "SC": "34206005", "SL": "37839007", "TOP": "6064005",
    }

    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"MedicationDispense/DISPENSACAO — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "medication": 0, "subject": 0, "context": 0,
          "performer": 0, "quantity": 0, "whenHandedOver": 0, "substitution": 0}

    for row in rows:
        r = dict(zip(cols, row))
        status = STATUS_MAP.get(_str(r.get("ie_situacao")) or "", "unknown")

        codings = []
        if r.get("cd_anvisa"):
            codings.append({"system": "http://www.anvisa.gov.br/medicamentos",
                             "code": _str(r["cd_anvisa"]), "display": _str(r.get("nm_medicamento"))})
        if r.get("cd_dcb"):
            codings.append({"system": "http://www.anvisa.gov.br/dcb", "code": _str(r["cd_dcb"])})
        codings.append({"system": "http://tasy.com/fhir/CodeSystem/material",
                        "display": _str(r.get("nm_medicamento"))})

        route = (_str(r.get("via_administracao")) or "").upper()
        dosage = {}
        if r.get("ds_posologia"):
            dosage["text"] = _str(r["ds_posologia"])
        if route:
            dosage["route"] = {"coding": [{"system": "http://snomed.info/sct",
                                             "code": ROUTE_MAP.get(route, ""),
                                             "display": route}], "text": route}

        body = {
            "resourceType": "MedicationDispense",
            "id": str(r["nr_dispensacao"]),
            "status": status,
            "medicationCodeableConcept": {"coding": codings,
                                           "text": _str(r.get("nm_medicamento"))},
            "subject": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
            "context": {"reference": f"Encounter/{r['nr_atendimento']}"} if r.get("nr_atendimento") else None,
            "performer": [{"actor": {"display": _str(r["nm_farmaceutico"])}}] if r.get("nm_farmaceutico") else [],
            "whenPrepared": _date(r.get("dt_preparacao")),
            "whenHandedOver": _date(r.get("dt_entrega")),
            "quantity": {"value": float(r["qt_dispensada"]),
                         "unit": _str(r.get("ds_unidade")) or "unidade"} if r.get("qt_dispensada") else None,
            "daysSupply": {"value": int(r["nr_dias_fornecimento"])} if r.get("nr_dias_fornecimento") else None,
            "dosageInstruction": [dosage] if dosage else [],
            "substitution": {"wasSubstituted": _bool(r.get("ie_substituicao"), "S")} if r.get("ie_substituicao") else None,
            "authorizingPrescription": [{"reference": f"MedicationRequest/{r['nr_prescricao']}-0"}]
                                        if r.get("nr_prescricao") else [],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "MedicationDispense", body, dry_run):
            ok_n += 1
            if body.get("status"):                   fc["status"] += 1
            if body.get("medicationCodeableConcept"): fc["medication"] += 1
            if body.get("subject"):                  fc["subject"] += 1
            if body.get("context"):                  fc["context"] += 1
            if body.get("performer"):                fc["performer"] += 1
            if body.get("quantity"):                 fc["quantity"] += 1
            if body.get("whenHandedOver"):           fc["whenHandedOver"] += 1
            if body.get("substitution"):             fc["substitution"] += 1

    print_report("MedicationDispense", total, sent, ok_n, fc)


def seed_care_teams(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("CT — CareTeam (Equipe Cirúrgica — EQUIPE_CIRURGICA)")
    SQL = """
        SELECT ec.nr_equipe, ec.nr_cirurgia, ec.cd_sala,
               ec.dt_cirurgia, ec.ie_situacao,
               ecp.nr_profissional, ecp.cd_funcao, ecp.ds_funcao,
               ap.cd_pessoa_fisica, ap.nr_atendimento
        FROM equipe_cirurgica ec
        JOIN equipe_cirurgica_prof ecp ON ecp.nr_equipe = ec.nr_equipe
        JOIN atendimento_paciente ap ON ap.nr_atendimento = ec.nr_cirurgia
        WHERE ap.cd_estabelecimento = :tenant
          AND ec.ie_situacao != 'C'
          AND ROWNUM <= :limit
        ORDER BY ec.nr_equipe DESC
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"CareTeam/EQUIPE_CIRURGICA — query falhou: {e}")
        warn("Confirme: SELECT TABLE_NAME FROM ALL_TABLES WHERE TABLE_NAME LIKE '%EQUIPE%' AND OWNER=USER")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    from collections import defaultdict
    teams: dict = defaultdict(lambda: {"participants": [], "meta": {}})
    for row in rows:
        r = dict(zip(cols, row))
        teams[r["nr_equipe"]]["meta"] = r
        if r.get("nr_profissional"):
            teams[r["nr_equipe"]]["participants"].append(r)

    sent = ok_n = 0
    fc = {"status": 0, "subject": 0, "encounter": 0, "participant": 0}

    for nr_equipe, data in teams.items():
        m = data["meta"]
        seen: set = set()
        participants = []
        for p in data["participants"]:
            pid = p.get("nr_profissional")
            if pid and pid not in seen:
                seen.add(pid)
                role = [{"coding": [{"system": "http://tasy.com/fhir/CodeSystem/funcao-equipe",
                                      "code": _str(p["cd_funcao"]),
                                      "display": _str(p.get("ds_funcao"))}]}] if p.get("cd_funcao") else []
                participants.append({"role": role, "member": {"reference": f"Practitioner/{pid}"}})

        body = {
            "resourceType": "CareTeam",
            "id": f"ct-{nr_equipe}",
            "status": "active",
            "name": f"Equipe Cirúrgica {nr_equipe}",
            "subject": {"reference": f"Patient/{m['cd_pessoa_fisica']}"} if m.get("cd_pessoa_fisica") else None,
            "encounter": {"reference": f"Encounter/{m['nr_atendimento']}"} if m.get("nr_atendimento") else None,
            "participant": participants,
            "extension": [{"url": "http://tasy.com/fhir/extension/sala",
                           "valueString": _str(m["cd_sala"])}] if m.get("cd_sala") else [],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "CareTeam", body, dry_run):
            ok_n += 1
            if body.get("status"):    fc["status"] += 1
            if body.get("subject"):   fc["subject"] += 1
            if body.get("encounter"): fc["encounter"] += 1
            if participants:          fc["participant"] += 1

    print_report("CareTeam", total, sent, ok_n, fc)


def seed_locations(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("LOC — Location (Setores de Atendimento — SETOR_ATENDIMENTO)")
    SQL = """
        SELECT s.cd_setor_atendimento, s.ds_setor, s.ie_situacao,
               s.cd_estabelecimento, s.ie_tipo_setor
        FROM setor_atendimento s
        WHERE s.cd_estabelecimento = :tenant
          AND s.ie_situacao = 'A'
          AND ROWNUM <= :limit
        ORDER BY s.cd_setor_atendimento
    """
    TYPE_MAP = {
        "UTI": ("ICU",  "Intensive Care Unit"),
        "CC":  ("OR",   "Operating Room"),
        "UE":  ("ER",   "Emergency Room"),
        "AM":  ("AMB",  "Ambulatory"),
        "INT": ("HOSP", "Hospital"),
    }
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Location/SETOR_ATENDIMENTO — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "name": 0, "type": 0, "identifier": 0}

    for row in rows:
        r = dict(zip(cols, row))
        tp = (_str(r.get("ie_tipo_setor")) or "").upper()
        type_code, type_display = TYPE_MAP.get(tp, ("HOSP", "Hospital"))

        body = {
            "resourceType": "Location",
            "id": f"loc-{r['cd_setor_atendimento']}",
            "identifier": [{"system": "http://tasy.com/fhir/identifier/setor",
                             "value": str(r["cd_setor_atendimento"])}],
            "status": "active",
            "name": _str(r.get("ds_setor")) or f"Setor {r['cd_setor_atendimento']}",
            "mode": "instance",
            "type": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                                   "code": type_code, "display": type_display}]}],
            "managingOrganization": {"identifier": {
                "system": "http://tasy.com/fhir/identifier/estabelecimento",
                "value": str(r["cd_estabelecimento"]),
            }} if r.get("cd_estabelecimento") else None,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None}
        sent += 1
        if post_resource(fhir, "Location", body, dry_run):
            ok_n += 1
            if body.get("status"):     fc["status"] += 1
            if body.get("name"):       fc["name"] += 1
            if body.get("type"):       fc["type"] += 1
            if body.get("identifier"): fc["identifier"] += 1

    print_report("Location", total, sent, ok_n, fc)


def seed_schedules(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("SCHED — Schedule (Agenda Cirúrgica — AGENDA_CIRURGIA)")
    SQL = """
        SELECT ac.nr_agenda, ac.cd_sala, ac.dt_agenda,
               ac.ie_status, ac.cd_estabelecimento
        FROM agenda_cirurgia ac
        WHERE ac.cd_estabelecimento = :tenant
          AND ROWNUM <= :limit
        ORDER BY ac.nr_agenda DESC
    """
    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Schedule/AGENDA_CIRURGIA — query falhou: {e}")
        warn("Confirme: SELECT TABLE_NAME FROM ALL_TABLES WHERE TABLE_NAME LIKE '%AGENDA%' AND OWNER=USER")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"active": 0, "actor": 0, "planningHorizon": 0}

    for row in rows:
        r = dict(zip(cols, row))
        st = (_str(r.get("ie_status")) or "A").upper()
        dt = _date(r.get("dt_agenda"))
        body = {
            "resourceType": "Schedule",
            "id": f"sched-{r['nr_agenda']}",
            "active": st not in ("F", "C", "X"),
            "actor": [{"reference": f"Location/loc-{r['cd_sala']}"}] if r.get("cd_sala") else [],
            "planningHorizon": {"start": dt, "end": dt} if dt else None,
            "comment": f"Agenda cirúrgica sala {r.get('cd_sala')} — {dt or 'sem data'}",
            "extension": [{"url": "http://tasy.com/fhir/extension/sala",
                           "valueString": _str(r["cd_sala"])}] if r.get("cd_sala") else [],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "Schedule", body, dry_run):
            ok_n += 1
            fc["active"] += 1
            if body.get("actor"):           fc["actor"] += 1
            if body.get("planningHorizon"): fc["planningHorizon"] += 1

    print_report("Schedule", total, sent, ok_n, fc)


def seed_slots(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("SLOT — Slot (Disponibilidade CC — AGENDA_CIRURGIA)")
    SQL = """
        SELECT ac.nr_agenda, ac.cd_sala, ac.dt_agenda,
               ac.hr_inicio, ac.hr_fim, ac.ie_status,
               ac.cd_estabelecimento
        FROM agenda_cirurgia ac
        WHERE ac.cd_estabelecimento = :tenant
          AND ac.hr_inicio IS NOT NULL
          AND ROWNUM <= :limit
        ORDER BY ac.nr_agenda DESC
    """
    STATUS_MAP = {"L": "free", "O": "busy", "B": "busy-unavailable", "M": "busy-unavailable"}

    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"Slot/AGENDA_CIRURGIA — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"schedule": 0, "status": 0, "start": 0}

    for row in rows:
        r = dict(zip(cols, row))
        st = (_str(r.get("ie_status")) or "L").upper()
        dt = _date(r.get("dt_agenda"))
        body = {
            "resourceType": "Slot",
            "id": f"slot-{r['nr_agenda']}",
            "schedule": {"reference": f"Schedule/sched-{r['nr_agenda']}"},
            "status": STATUS_MAP.get(st, "free"),
            "start": dt,
            "end": dt,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None}
        sent += 1
        if post_resource(fhir, "Slot", body, dry_run):
            ok_n += 1
            if body.get("schedule"): fc["schedule"] += 1
            if body.get("status"):   fc["status"] += 1
            if body.get("start"):    fc["start"] += 1

    print_report("Slot", total, sent, ok_n, fc)


def seed_supply_deliveries(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("SD — SupplyDelivery (Movimentação Farmácia — ESTOQUE_FARMACIA)")
    # ESTOQUE_FARMACIA não tem CD_ESTABELECIMENTO; filtra apenas por tipo de movimento.
    SQL = """
        SELECT ef.nr_movimento, ef.cd_medicamento, ef.cd_anvisa,
               ef.nm_medicamento, ef.qt_movimentada, ef.ds_unidade,
               ef.dt_movimento, ef.ie_tipo_movimento,
               ef.nr_lote, ef.dt_validade,
               ef.cd_fornecedor, ef.nm_fornecedor,
               ef.cd_farmacia_destino, ef.nm_farmacia_destino,
               ef.ie_situacao
        FROM estoque_farmacia ef
        WHERE ef.ie_tipo_movimento IN ('E', 'T')
          AND ef.ie_situacao != 'X'
          AND ROWNUM <= :limit
        ORDER BY ef.nr_movimento DESC
    """
    STATUS_MAP = {"E": "in-progress", "C": "completed", "X": "abandoned"}

    cur = ora.cursor()
    try:
        cur.execute(SQL, limit=limit)
    except Exception as e:
        warn(f"SupplyDelivery/ESTOQUE_FARMACIA — query falhou: {e}")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "suppliedItem": 0, "occurrenceDateTime": 0,
          "supplier": 0, "extension[lote]": 0}

    for row in rows:
        r = dict(zip(cols, row))
        codings = []
        if r.get("cd_anvisa"):
            codings.append({"system": "http://www.anvisa.gov.br/medicamentos",
                             "code": _str(r["cd_anvisa"]), "display": _str(r.get("nm_medicamento"))})
        codings.append({"system": "http://tasy.com/fhir/CodeSystem/material",
                        "code": _str(r.get("cd_medicamento")), "display": _str(r.get("nm_medicamento"))})

        extensions = []
        if r.get("nr_lote"):
            extensions.append({"url": "http://tasy.com/fhir/extension/lote",
                                "valueString": _str(r["nr_lote"])})
        if r.get("dt_validade"):
            extensions.append({"url": "http://tasy.com/fhir/extension/validade",
                                "valueDate": _date(r["dt_validade"])})

        body = {
            "resourceType": "SupplyDelivery",
            "id": str(r["nr_movimento"]),
            "status": STATUS_MAP.get(_str(r.get("ie_situacao")) or "", "completed"),
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/supply-item-type",
                                   "code": "medication"}]},
            "suppliedItem": {
                "quantity": {"value": float(r["qt_movimentada"] or 0),
                             "unit": _str(r.get("ds_unidade")) or "unidade"},
                "itemCodeableConcept": {"coding": codings,
                                         "text": _str(r.get("nm_medicamento"))},
            },
            "occurrenceDateTime": _date(r.get("dt_movimento")),
            "supplier": {"display": _str(r["nm_fornecedor"])} if r.get("nm_fornecedor") else None,
            "destination": {"display": _str(r["nm_farmacia_destino"])} if r.get("nm_farmacia_destino") else None,
            "extension": extensions,
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "SupplyDelivery", body, dry_run):
            ok_n += 1
            if body.get("status"):             fc["status"] += 1
            if body.get("suppliedItem"):       fc["suppliedItem"] += 1
            if body.get("occurrenceDateTime"): fc["occurrenceDateTime"] += 1
            if body.get("supplier"):           fc["supplier"] += 1
            if any(e["url"].endswith("lote") for e in extensions): fc["extension[lote]"] += 1

    print_report("SupplyDelivery", total, sent, ok_n, fc)


def seed_coverage_eligibility_requests(ora, fhir, limit: int, tenant: int, dry_run: bool):
    header("CER — CoverageEligibilityRequest (Pré-Autorizações — AUTORIZACAO)")
    # Tabela AUTORIZACAO (diferente de AUTORIZACAO_CONVENIO já usada em ClaimResponse).
    SQL = """
        SELECT a.nr_autorizacao, a.dt_autorizacao, a.cd_convenio,
               a.nr_atendimento, a.ie_status,
               a.dt_validade_inicio, a.dt_validade_fim,
               a.nr_guia_tiss, a.ds_justificativa,
               ap.cd_pessoa_fisica
        FROM autorizacao a
        JOIN atendimento_paciente ap ON ap.nr_atendimento = a.nr_atendimento
        WHERE ap.cd_estabelecimento = :tenant
          AND a.ie_status != 'E'
          AND ROWNUM <= :limit
        ORDER BY a.nr_autorizacao DESC
    """
    STATUS_MAP  = {"A": "active", "P": "active", "S": "active", "N": "cancelled", "R": "active"}
    PURPOSE_MAP = {"A": ["benefits"], "P": ["discovery"], "S": ["discovery"],
                   "N": ["benefits"], "R": ["benefits"]}

    cur = ora.cursor()
    try:
        cur.execute(SQL, tenant=tenant, limit=limit)
    except Exception as e:
        warn(f"CoverageEligibilityRequest/AUTORIZACAO — query falhou: {e}")
        warn("Confirme: SELECT COLUMN_NAME FROM ALL_TAB_COLUMNS WHERE TABLE_NAME='AUTORIZACAO' AND OWNER=USER")
        return
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    total = len(rows)
    info(f"Lidos no Oracle: {total}")

    sent = ok_n = 0
    fc = {"status": 0, "patient": 0, "insurer": 0, "created": 0,
          "insurance": 0, "identifier[guia]": 0}

    for row in rows:
        r = dict(zip(cols, row))
        ie_status = (_str(r.get("ie_status")) or "P").upper()

        insurance = []
        if r.get("cd_convenio"):
            insurance.append({
                "coverage": {"identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                             "value": str(r["cd_convenio"])}},
                "businessArrangement": _str(r.get("nr_guia_tiss")),
            })

        body = {
            "resourceType": "CoverageEligibilityRequest",
            "id": f"cer-{r['nr_autorizacao']}",
            "identifier": [{"system": "http://tasy.com/fhir/identifier/autorizacao",
                             "value": str(r["nr_autorizacao"])}],
            "status": STATUS_MAP.get(ie_status, "active"),
            "purpose": PURPOSE_MAP.get(ie_status, ["benefits"]),
            "patient": {"reference": f"Patient/{r['cd_pessoa_fisica']}"} if r.get("cd_pessoa_fisica") else None,
            "created": _date(r.get("dt_autorizacao")) or datetime.now().isoformat(),
            "insurer": {"identifier": {"system": "http://tasy.com/fhir/identifier/convenio",
                                        "value": str(r["cd_convenio"])}} if r.get("cd_convenio") else None,
            "insurance": insurance,
            "serviced": {"start": _date(r.get("dt_validade_inicio")),
                         "end":   _date(r.get("dt_validade_fim"))} if r.get("dt_validade_inicio") else None,
            "supportingInfo": [{"sequence": 1,
                                 "information": {"text": _str(r["ds_justificativa"])}}]
                               if r.get("ds_justificativa") else [],
            "extension": [{"url": "http://tasy.com/fhir/extension/encounter",
                           "valueReference": {"reference": f"Encounter/{r['nr_atendimento']}"}}]
                         if r.get("nr_atendimento") else [],
            "meta": {"tag": [{"system": "http://tasy.com/fhir/tenant", "code": "austa"}]},
        }
        body = {k: v for k, v in body.items() if v is not None and v != []}
        sent += 1
        if post_resource(fhir, "CoverageEligibilityRequest", body, dry_run):
            ok_n += 1
            if body.get("status"):    fc["status"] += 1
            if body.get("patient"):   fc["patient"] += 1
            if body.get("insurer"):   fc["insurer"] += 1
            if body.get("created"):   fc["created"] += 1
            if body.get("insurance"): fc["insurance"] += 1
            if body["identifier"][0].get("value"): fc["identifier[guia]"] += 1

    print_report("CoverageEligibilityRequest", total, sent, ok_n, fc)


# ── Catalogo map ──────────────────────────────────────────────────────────────

CATALOGS = {
    # Cadastros / Master data
    "organization":                   seed_organizations,
    "practitioner":                   seed_practitioners,
    "patient":                        seed_patients,
    # Clínico / Atendimento
    "encounter":                      seed_encounters,
    "coverage":                       seed_coverages,
    "procedure":                      seed_procedures,
    "condition":                      seed_conditions,
    "documentreference":              seed_document_references,
    "medicationrequest":              seed_medication_requests,
    "medicationadmin":                seed_medication_admin,
    "diagnosticreport":               seed_diagnostic_reports,
    # Grupo 1 — clínico avançado
    "observation":                    seed_observations,
    "riskassessment":                 seed_risk_assessments,
    "detectedissue":                  seed_detected_issues,
    "medicationdispense":             seed_medication_dispenses,
    # Grupo 1 — infraestrutura hospitalar
    "careteam":                       seed_care_teams,
    "location":                       seed_locations,
    "schedule":                       seed_schedules,
    "slot":                           seed_slots,
    # Grupo 1 — farmácia / suprimentos
    "supplydelivery":                 seed_supply_deliveries,
    # Autorização
    "claimresponse":                  seed_claim_responses,
    "coverageeligibilityrequest":     seed_coverage_eligibility_requests,
    # Faturamento
    "chargeitem":                     seed_charge_items,
    "contractpricing":                seed_contract_pricing,
    "claim":                          seed_claims,
    "tissguid":                       seed_tiss_guides,
    # Retorno / Financeiro
    "claimresponse_retorno":          seed_claim_responses_retorno,
    "appeal":                         seed_appeals,
    "paymentnotice":                  seed_payment_notices,
    "invoice":                        seed_invoices,
    "task":                           seed_tasks,
    "paymentreconciliation":          seed_payment_reconciliations,
}

ALL_CATALOGS_ORDER = [
    # Master data primeiro (dependências de referência)
    "organization", "practitioner", "patient",
    # Clínico base
    "encounter", "coverage", "procedure", "condition",
    "documentreference", "medicationrequest", "medicationadmin", "diagnosticreport",
    # Clínico avançado (Grupo 1)
    "observation", "riskassessment", "detectedissue", "medicationdispense",
    # Infraestrutura hospitalar (Grupo 1)
    "careteam", "location", "schedule", "slot",
    # Farmácia / suprimentos (Grupo 1)
    "supplydelivery",
    # Autorização
    "claimresponse", "coverageeligibilityrequest",
    # Faturamento
    "chargeitem", "contractpricing", "claim", "tissguid",
    # Retorno / Financeiro
    "claimresponse_retorno", "appeal",
    "paymentnotice", "invoice", "task", "paymentreconciliation",
]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed HAPI FHIR local com dados reais do Oracle Tasy")
    parser.add_argument("--url",     default=None,          help="URL do HAPI FHIR local (default: FHIR_BASE_URL do .env)")
    parser.add_argument("--env",     default="ignorar/hapifhir/.env", help="Caminho do .env")
    parser.add_argument("--limit",   type=int, default=None, help="Registros por catalogo (default: SEED_LIMIT do .env)")
    parser.add_argument("--tenant",  type=int, default=None, help="CD_ESTABELECIMENTO (default: SEED_TENANT do .env)")
    parser.add_argument("--catalog", default=None,
                        help=f"Catalogo(s) separados por virgula. Opcoes: {', '.join(ALL_CATALOGS_ORDER)}")
    parser.add_argument("--dry-run", action="store_true",
                        help="Conecta e conta registros no Oracle sem fazer POST no FHIR")
    args = parser.parse_args()

    # Carrega .env
    env_path = Path(args.env)
    if env_path.exists():
        load_dotenv(env_path)
        info(f".env carregado: {env_path.resolve()}")
    else:
        warn(f".env nao encontrado em {env_path} — usando variaveis de ambiente")

    fhir_url = args.url or os.getenv("FHIR_BASE_URL", "http://localhost:8082/fhir")
    limit    = args.limit  or int(os.getenv("SEED_LIMIT",  "100"))
    tenant   = args.tenant or int(os.getenv("SEED_TENANT", "4"))

    # Catalagos selecionados
    if args.catalog:
        selected = [c.strip().lower() for c in args.catalog.split(",")]
        unknown = [c for c in selected if c not in CATALOGS]
        if unknown:
            print(f"{RED}Catalogo(s) desconhecido(s): {unknown}{NC}")
            print(f"Opcoes validas: {', '.join(ALL_CATALOGS_ORDER)}")
            sys.exit(1)
    else:
        selected = ALL_CATALOGS_ORDER

    header(f"MAEZO — Seed FHIR from Tasy\n  FHIR: {fhir_url}\n  Limit: {limit} registros/catalogo  |  Tenant: {tenant}")

    if args.dry_run:
        warn("MODO DRY-RUN — nenhum dado sera enviado ao FHIR")

    # Conecta Oracle
    try:
        ora = connect_oracle()
        ok(f"Oracle conectado: {os.getenv('ORACLE_HOST')}:{os.getenv('ORACLE_PORT', '1521')}/{os.getenv('ORACLE_SERVICE')}")
    except Exception as e:
        print(f"{RED}Falha na conexao Oracle: {e}{NC}")
        print("Verifique as variaveis ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE, ORACLE_USER, ORACLE_PASSWORD no .env")
        sys.exit(1)

    # Conecta FHIR
    fhir = connect_fhir(fhir_url)
    try:
        r = fhir.get("/metadata")
        r.raise_for_status()
        ok(f"HAPI FHIR acessivel ({r.status_code})")
    except Exception as e:
        print(f"{RED}Falha na conexao FHIR: {e}{NC}")
        print(f"Verifique se o FHIR local esta rodando: docker compose -f docker-compose.local.yml --profile fhir up -d")
        sys.exit(1)

    # Executa seed
    for name in selected:
        CATALOGS[name](ora, fhir, limit, tenant, args.dry_run)

    ora.close()
    fhir.close()
    print(f"\n{GREEN}{BOLD}Seed concluido.{NC}\n")


if __name__ == "__main__":
    main()
