"""Teste de integração MAEZO → RPA Unimed (Nível 1 — sem CIB Seven real).

Usa o RpaClient do MAEZO para chamar a API do RPA hos_austa em execução local.
O callback de resultado é recebido pelo stub_cibseven (porta 9000).

Pré-requisitos:
    No projeto hos_austa_autorizacaopre:
        docker compose -f docker-compose.yml -f docker-compose.stub.yml up --build

Uso:
    cd C:\\ProjetosPython\\Hospital\\Healthcare-Orchest-main
    python scripts/test_rpa_call.py <nr_sequencia> <nr_atendimento> [cd_estabelecimento]

Exemplos:
    python scripts/test_rpa_call.py 341470 329152
    python scripts/test_rpa_call.py 341470 329152 4
"""
from __future__ import annotations

import os
import sys
import time
import uuid

# Garante que src/ está no PYTHONPATH ao rodar direto pelo terminal
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import httpx

from healthcare_platform.shared.integrations.rpa_client import (
    RpaAuthorizationRequest,
    RpaClient,
    RpaJobAccepted,
)
from healthcare_platform.shared.integrations.base import IntegrationSettings

# ── Configuração ──────────────────────────────────────────────────────────────

RPA_URL   = os.environ.get("RPA_UNIMED_URL",   "http://host.docker.internal:8000")
STUB_URL  = os.environ.get("RPA_STUB_URL",     "http://localhost:9000")
TIMEOUT_S = int(os.environ.get("RPA_CALLBACK_TIMEOUT", "300"))  # 5 min


# ── Helpers ───────────────────────────────────────────────────────────────────

def aguardar_servico(url: str, nome: str, tentativas: int = 20) -> None:
    print(f"⏳ Aguardando {nome} ({url}/health)...")
    for _ in range(tentativas):
        try:
            r = httpx.get(f"{url}/health", timeout=3)
            if r.status_code == 200:
                print(f"✅ {nome} está no ar.")
                return
        except Exception:
            pass
        time.sleep(3)
    print(f"❌ {nome} não respondeu. Verifique se o Docker está rodando.")
    sys.exit(1)


def limpar_callbacks() -> None:
    httpx.delete(f"{STUB_URL}/callbacks", timeout=5)
    print("🧹 Callbacks anteriores limpos.")


def chamar_rpa(nr_sequencia: int, nr_atendimento: int, cd_estabelecimento: int) -> RpaJobAccepted:
    from healthcare_platform.shared.integrations.rpa_client import (
        RpaCobertura,
        RpaPrestador,
        RpaAtendimento,
        RpaProcedimento,
    )

    process_instance_id = f"teste-homolog-{nr_sequencia}"

    request = RpaAuthorizationRequest(
        process_instance_id=process_instance_id,
        tenant_id="austa",
        rpa_type="autorizacao_pa",
        message_name="rpa_authorization_result",
        cobertura=RpaCobertura(
            carteirinha="00301507000072309",
            cd_convenio=1,
            ds_convenio="Unimed",
        ),
        prestador=RpaPrestador(
            cd_prestador="110020",
            nr_crm="135677",
        ),
        atendimento=RpaAtendimento(
            nr_atendimento=nr_atendimento,
            nr_sequencia=nr_sequencia,
            cd_estabelecimento=cd_estabelecimento,
            dt_entrada="2024-01-01",
            ds_carater_atendimento="Urgência/Emergência",
            ie_consulta_emergencia="S",
            ie_tipo_consulta="Primeira consulta",
            ie_tipo_atendimento="Consulta",
            ie_regime_atendimento="Pronto Socorro",
            tp_acidente="Não acidente",
        ),
        procedimentos=[
            RpaProcedimento(code="0", display="", quantity=1, category=""),
        ],
        diagnoses=[""],
    )

    client = RpaClient(
        settings=IntegrationSettings(base_url=RPA_URL, timeout_seconds=15)
    )

    print(f"\n📤 Chamando RPA via RpaClient (payload FHIR-inspired)...")
    print(f"   RPA URL           : {RPA_URL}/api/v1/authorize")
    print(f"   nr_sequencia      : {nr_sequencia}")
    print(f"   nr_atendimento    : {nr_atendimento}")
    print(f"   cd_estabelecimento: {cd_estabelecimento}")
    print(f"   carteirinha       : {request.cobertura.carteirinha}")
    print(f"   convenio          : {request.cobertura.ds_convenio}")
    print(f"   process_instance  : {process_instance_id}")

    job = client.request_authorization(request)

    print(f"✅ RPA aceitou — rpa_execution_id: {job.rpa_execution_id}")
    return job, process_instance_id


def aguardar_callback(process_instance_id: str) -> dict | None:
    print(f"\n⏳ Aguardando callback do RPA (timeout: {TIMEOUT_S}s)...")
    inicio = time.time()

    while time.time() - inicio < TIMEOUT_S:
        try:
            r = httpx.get(f"{STUB_URL}/callbacks/ultimo", timeout=5)
            data = r.json()
            if data.get("process_instance_id") == process_instance_id:
                return data
        except Exception:
            pass

        decorrido = int(time.time() - inicio)
        print(f"   ... {decorrido}s — aguardando RPA processar no portal Unimed")
        time.sleep(10)

    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    nr_sequencia       = int(sys.argv[1])
    nr_atendimento     = int(sys.argv[2])
    cd_estabelecimento = int(sys.argv[3]) if len(sys.argv) > 3 else 4

    # 1. Verifica serviços
    aguardar_servico(RPA_URL,  "RPA API (hos_austa)")
    aguardar_servico(STUB_URL, "Stub CIB Seven")

    # 2. Limpa callbacks anteriores
    limpar_callbacks()

    # 3. Chama o RPA via RpaClient
    job, process_instance_id = chamar_rpa(nr_sequencia, nr_atendimento, cd_estabelecimento)

    # 4. Aguarda o callback
    callback = aguardar_callback(process_instance_id)

    # 5. Resultado
    sep = "=" * 60
    print(f"\n{sep}")
    if callback:
        v = callback.get("variables", {})
        status = v.get("resultado", "?")
        emoji = {"2": "✅ APROVADO", "6": "🔄 EM ANÁLISE", "7": "❌ NEGADO"}.get(
            status, f"⚠️  STATUS {status}"
        )
        print(f"🎉 CALLBACK RECEBIDO — {emoji}")
        print(f"   message_name      : {callback.get('message_name')}")
        print(f"   process_instance  : {callback.get('process_instance_id')}")
        print(f"   resultado (TASY)  : {v.get('resultado')}")
        print(f"   mensagem          : {v.get('mensagem')}")
        print(f"   cod_guia          : {v.get('cod_guia')}")
        print(f"   cod_requisicao    : {v.get('cod_requisicao')}")
        print(f"   recebido em       : {callback.get('received_at')}")
    else:
        print("❌ Timeout: callback não chegou no tempo esperado.")
        print(f"   Verifique os logs: docker compose logs -f rpa")
        print(f"   Ver VNC:          http://localhost:7900")
    print(sep)


if __name__ == "__main__":
    main()
