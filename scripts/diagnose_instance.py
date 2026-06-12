#!/usr/bin/env python3
"""
Diagnóstico completo de uma instância de processo no CIB Seven.

Mostra:
  - Estado geral do processo
  - Cada atividade executada com tempo de duração
  - External tasks e seus status (completadas, falhadas, pendentes)
  - Incidents (erros) ativos e resolvidos
  - Variáveis do processo
  - Jobs pendentes (timers, async)

Uso:
  python3 scripts/diagnose_instance.py <instance_id>
  python3 scripts/diagnose_instance.py <instance_id> --port 8080
  python3 scripts/diagnose_instance.py --last   # pega a última instância SP_RC_002
"""
import argparse
import json
import sys
from datetime import datetime

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_dt(s):
    """Parse ISO datetime do CIB Seven (suporta +0000, -0300, Z, etc.)."""
    if not s:
        return None
    import re
    # Remove timezone offset (e.g. +0000, -0300, Z)
    s = re.sub(r'[+-]\d{4}$', '', s).replace("Z", "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def duration_str(start, end):
    """Retorna string de duração entre dois datetimes."""
    if not start or not end:
        return "—"
    delta = end - start
    total_s = delta.total_seconds()
    if total_s < 1:
        return f"{int(total_s * 1000)}ms"
    if total_s < 60:
        return f"{total_s:.1f}s"
    if total_s < 3600:
        return f"{int(total_s // 60)}m {int(total_s % 60)}s"
    return f"{int(total_s // 3600)}h {int((total_s % 3600) // 60)}m"


def get(client, path, params=None):
    r = client.get(path, params=params or {})
    if r.status_code == 200:
        return r.json()
    return None


def diagnose(client, instance_id):
    print(f"\n{'='*75}")
    print(f"  DIAGNÓSTICO — {instance_id}")
    print(f"{'='*75}")

    # ── 1. Estado do processo ───────────────────────────────────────────────
    hist = get(client, "/history/process-instance", {"processInstanceId": instance_id})
    if not hist:
        print(f"\n  ERRO: Instância {instance_id} não encontrada.")
        return
    proc = hist[0]
    state = proc.get("state", "?")
    start_time = parse_dt(proc.get("startTime"))
    end_time = parse_dt(proc.get("endTime"))
    bkey = proc.get("businessKey", "—")
    definition = proc.get("processDefinitionId", "?")

    print(f"\n  Estado       : {state}")
    print(f"  Definição    : {definition}")
    print(f"  Business Key : {bkey}")
    print(f"  Início       : {proc.get('startTime', '?')}")
    print(f"  Fim          : {proc.get('endTime', '—')}")
    print(f"  Duração total: {duration_str(start_time, end_time)}")

    # ── 2. Atividades executadas (histórico) ─────────────────────────────────
    activities = get(client, "/history/activity-instance", {
        "processInstanceId": instance_id,
        "sortBy": "startTime",
        "sortOrder": "asc",
    })
    if activities:
        print(f"\n{'─'*75}")
        print(f"  ATIVIDADES ({len(activities)})")
        print(f"{'─'*75}")
        print(f"  {'#':<3} {'Tipo':<18} {'Nome':<30} {'Duração':<10} {'Status'}")
        print(f"  {'─'*3} {'─'*18} {'─'*30} {'─'*10} {'─'*10}")
        for i, act in enumerate(activities, 1):
            act_type = act.get("activityType", "?")
            act_name = act.get("activityName") or act.get("activityId", "?")
            act_start = parse_dt(act.get("startTime"))
            act_end = parse_dt(act.get("endTime"))
            dur = duration_str(act_start, act_end)
            canceled = act.get("canceled", False)
            ended = act_end is not None

            if canceled:
                status = "CANCELADA"
            elif ended:
                status = "OK"
            else:
                status = ">>> EM ANDAMENTO <<<"

            # Truncar nome se necessário
            name_display = (act_name[:28] + "..") if len(act_name) > 30 else act_name
            print(f"  {i:<3} {act_type:<18} {name_display:<30} {dur:<10} {status}")

        # Mostrar onde está travado
        active_acts = [a for a in activities if not a.get("endTime") and not a.get("canceled")]
        if active_acts:
            print(f"\n  >>> PROCESSO TRAVADO EM:")
            for a in active_acts:
                act_name = a.get("activityName") or a.get("activityId", "?")
                act_type = a.get("activityType", "?")
                act_id = a.get("activityId", "?")
                print(f"      - [{act_type}] {act_name} (id: {act_id})")

    # ── 3. External Tasks (histórico) ────────────────────────────────────────
    ext_logs = get(client, "/history/external-task-log", {
        "processInstanceId": instance_id,
        "sortBy": "timestamp",
        "sortOrder": "asc",
    })
    if ext_logs:
        print(f"\n{'─'*75}")
        print(f"  EXTERNAL TASKS LOG ({len(ext_logs)})")
        print(f"{'─'*75}")
        for log in ext_logs:
            topic = log.get("topicName", "?")
            worker = log.get("workerId", "?")
            timestamp = log.get("timestamp", "?")
            # Flags de estado
            creation = log.get("creationLog", False)
            success = log.get("successLog", False)
            failure = log.get("failureLog", False)
            deletion = log.get("deletionLog", False)

            if success:
                icon = "OK"
            elif failure:
                icon = "FALHA"
            elif deletion:
                icon = "DELETADA"
            elif creation:
                icon = "CRIADA"
            else:
                icon = "?"

            print(f"  [{icon:<7}] {topic:<40} worker={worker}  {timestamp}")

            if failure:
                err_msg = log.get("errorMessage", "")
                if err_msg:
                    print(f"           erro: {err_msg[:120]}")

    # External tasks pendentes (não histórico)
    ext_pending = get(client, "/external-task", {
        "processInstanceId": instance_id,
    })
    if ext_pending:
        print(f"\n  EXTERNAL TASKS PENDENTES ({len(ext_pending)}):")
        for t in ext_pending:
            topic = t.get("topicName", "?")
            locked = t.get("workerId")
            retries = t.get("retries")
            err = t.get("errorMessage", "")
            lock_str = f"locked by {locked}" if locked else "não lockada"
            print(f"    - {topic:<40} retries={retries}  {lock_str}")
            if err:
                print(f"      erro: {err[:150]}")

    # ── 4. Incidents ─────────────────────────────────────────────────────────
    incidents = get(client, "/incident", {"processInstanceId": instance_id})
    hist_incidents = get(client, "/history/incident", {"processInstanceId": instance_id})

    all_incidents = []
    if incidents:
        for inc in incidents:
            inc["_resolved"] = False
            all_incidents.append(inc)
    if hist_incidents:
        active_ids = {i.get("id") for i in (incidents or [])}
        for inc in hist_incidents:
            if inc.get("id") not in active_ids:
                inc["_resolved"] = True
                all_incidents.append(inc)

    if all_incidents:
        print(f"\n{'─'*75}")
        print(f"  INCIDENTS ({len(all_incidents)})")
        print(f"{'─'*75}")
        for inc in all_incidents:
            resolved = inc.get("_resolved", False)
            icon = "RESOLVIDO" if resolved else ">>> ATIVO <<<"
            inc_type = inc.get("incidentType", "?")
            msg = inc.get("incidentMessage") or inc.get("message") or "sem mensagem"
            activity = inc.get("activityId", "?")
            timestamp = inc.get("incidentTimestamp") or inc.get("createTime", "?")
            print(f"\n  [{icon}] {inc_type}")
            print(f"    Atividade : {activity}")
            print(f"    Quando    : {timestamp}")
            print(f"    Mensagem  : {msg[:300]}")
    elif state == "ACTIVE":
        print(f"\n  Sem incidents registrados.")

    # ── 5. Jobs pendentes (timers, async) ────────────────────────────────────
    jobs = get(client, "/job", {"processInstanceId": instance_id})
    if jobs:
        print(f"\n{'─'*75}")
        print(f"  JOBS PENDENTES ({len(jobs)})")
        print(f"{'─'*75}")
        for job in jobs:
            job_type = job.get("jobDefinitionId", "?")
            due = job.get("duedate", "—")
            retries = job.get("retries", "?")
            suspended = job.get("suspended", False)
            exc_msg = job.get("exceptionMessage", "")
            print(f"  - tipo={job_type}  due={due}  retries={retries}  suspended={suspended}")
            if exc_msg:
                print(f"    exception: {exc_msg[:200]}")

    # ── 6. Variáveis do processo ─────────────────────────────────────────────
    variables = get(client, "/history/variable-instance", {
        "processInstanceId": instance_id,
    })
    if variables:
        print(f"\n{'─'*75}")
        print(f"  VARIÁVEIS ({len(variables)})")
        print(f"{'─'*75}")
        for var in sorted(variables, key=lambda v: v.get("name", "")):
            name = var.get("name", "?")
            value = var.get("value")
            vtype = var.get("type", "?")
            # Truncar valores longos
            val_str = str(value)
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            print(f"  {name:<35} ({vtype:<7}) = {val_str}")

    print(f"\n{'='*75}")
    print(f"  Cockpit: http://localhost:8085/camunda/app/cockpit/default/#/process-instance/{instance_id}")
    print(f"{'='*75}\n")


def find_last_instance(client, process_key="SP_RC_002_Pre_Service"):
    """Encontra a última instância do processo."""
    hist = get(client, "/history/process-instance", {
        "processDefinitionKey": process_key,
        "sortBy": "startTime",
        "sortOrder": "desc",
        "maxResults": 1,
    })
    if hist:
        return hist[0]["id"]
    return None


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico de instância CIB Seven")
    parser.add_argument("instance_id", nargs="?", help="ID da instância")
    parser.add_argument("--last", action="store_true", help="Usar última instância SP_RC_002")
    parser.add_argument("--process-key", default="SP_RC_002_Pre_Service", help="Process key para --last")
    parser.add_argument("--port", type=int, default=8085, help="Porta do CIB Seven")
    parser.add_argument("--host", default="localhost", help="Host do CIB Seven")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()

    if not args.instance_id and not args.last:
        print("Uso: python3 scripts/diagnose_instance.py <instance_id>")
        print("     python3 scripts/diagnose_instance.py --last")
        sys.exit(1)

    client = httpx.Client(
        base_url=f"http://{args.host}:{args.port}/engine-rest",
        auth=(args.user, args.password),
        timeout=15.0,
    )

    if args.last:
        instance_id = find_last_instance(client, args.process_key)
        if not instance_id:
            print(f"Nenhuma instância encontrada para {args.process_key}")
            sys.exit(1)
        print(f"Última instância: {instance_id}")
    else:
        instance_id = args.instance_id

    diagnose(client, instance_id)
    client.close()


if __name__ == "__main__":
    main()
