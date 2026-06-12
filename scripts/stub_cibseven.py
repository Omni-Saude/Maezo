"""Stub do CIB Seven Engine REST para testes de integração com RPA.

Simula o endpoint POST /engine-rest/message que o RPA chama ao terminar
a autorização. Armazena os callbacks em memória para inspeção.

Endpoints:
    POST   /engine-rest/message   — recebe callback do RPA
    GET    /callbacks              — lista todos os callbacks recebidos
    GET    /callbacks/ultimo       — retorna o último callback
    DELETE /callbacks              — limpa todos os callbacks
    GET    /health                 — health check

Uso:
    python scripts/stub_cibseven.py [porta]
    python scripts/stub_cibseven.py 9000
"""
from __future__ import annotations

import sys
from datetime import datetime

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Stub CIB Seven", version="1.0.0")

# Armazena callbacks em memória
callbacks: list[dict] = []


@app.post("/engine-rest/message")
async def receive_message(body: dict):
    """Recebe o callback do RPA (mesmo contrato do CIB Seven real)."""
    # Extrai dados do formato CIB Seven:
    # {
    #   "messageName": "...",
    #   "processInstanceId": "...",
    #   "processVariables": { "var": {"value": "x", "type": "String"} }
    # }
    message_name = body.get("messageName", "")
    process_instance_id = body.get("processInstanceId", "")

    # Simplifica processVariables para leitura fácil
    raw_vars = body.get("processVariables", {})
    variables = {k: v.get("value") if isinstance(v, dict) else v for k, v in raw_vars.items()}

    entry = {
        "message_name": message_name,
        "process_instance_id": process_instance_id,
        "variables": variables,
        "raw": body,
        "received_at": datetime.now().isoformat(),
    }
    callbacks.append(entry)

    print(f"\n{'='*60}")
    print(f"CALLBACK RECEBIDO")
    print(f"  message_name      : {message_name}")
    print(f"  process_instance  : {process_instance_id}")
    print(f"  variables         : {variables}")
    print(f"  received_at       : {entry['received_at']}")
    print(f"{'='*60}\n")

    return {"status": "ok", "message": "Callback recebido pelo stub"}


@app.get("/callbacks")
async def list_callbacks():
    return callbacks


@app.get("/callbacks/ultimo")
async def last_callback():
    if not callbacks:
        return {}
    return callbacks[-1]


@app.delete("/callbacks")
async def clear_callbacks():
    callbacks.clear()
    return {"status": "ok", "message": "Callbacks limpos"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "stub-cibseven", "callbacks_count": len(callbacks)}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    print(f"\nStub CIB Seven rodando em http://localhost:{port}")
    print(f"  POST   /engine-rest/message  — recebe callback do RPA")
    print(f"  GET    /callbacks             — lista callbacks")
    print(f"  GET    /callbacks/ultimo      — ultimo callback")
    print(f"  DELETE /callbacks             — limpa callbacks")
    print(f"  GET    /health               — health check\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
