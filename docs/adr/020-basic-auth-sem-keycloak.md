# ADR-020 — Basic Auth para Workers (sem Keycloak)

**Status:** Accepted
**Data:** 2026-02-27
**Supersede:** ADR-008 (Keycloak OAuth2 Workers) — arquivado em `docs/archive/`

---

## Contexto

A arquitetura original (ADR-008) usava Keycloak como Identity Provider para autenticação dos workers via OAuth2 `client_credentials`. Cada worker tinha um `CLIENT_ID` e `CLIENT_SECRET` separados, e o Keycloak emitia tokens JWT que o CIB Seven validava.

**Problema:** Keycloak adicionou complexidade operacional significativa:
- Container adicional (~512 MB RAM)
- Realm configuration (14 service clients, 4 tenant groups, scopes)
- Token refresh lifecycle nos workers
- Ponto adicional de falha (workers bloqueiam se Keycloak cair)

**Descoberta:** Ao examinar o código dos workers (`shared/runtime/worker_runner.py`), identificou-se que a autenticação já era implementada como `auth_basic`, apenas usando os campos `KEYCLOAK_CLIENT_ID` e `KEYCLOAK_CLIENT_SECRET` como username/password. O protocolo OAuth2 não estava sendo usado — era Basic Auth renomeado.

---

## Decisão

**Remover Keycloak. Usar HTTP Basic Auth diretamente no CIB Seven.**

- Workers autenticam com `CIB7_USER` + `CIB7_PASSWORD` via Basic Auth
- CIB Seven habilita Spring Security Basic Auth (já suportado nativamente)
- Multi-tenancy mantido via path `/tenant-id/{id}` (sem necessidade de JWT claims)
- Um único par de credenciais por serviço (não por worker)

---

## Implementação

### worker_runner.py

```python
# ANTES (ADR-008 — Keycloak):
kc_client_id = os.getenv("KEYCLOAK_CLIENT_ID")
kc_client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")
if kc_client_id and kc_client_secret:
    config["auth_basic"] = {"username": kc_client_id, "password": kc_client_secret}

# DEPOIS (ADR-020 — Basic Auth):
cib7_user = os.getenv("CIB7_USER")
cib7_password = os.getenv("CIB7_PASSWORD")
if cib7_user and cib7_password:
    config["auth_basic"] = {"username": cib7_user, "password": cib7_password}
```

### docker-compose.swarm.yml

```yaml
# CIB Seven — habilitar Basic Auth
cib7:
  environment:
    CIBSEVEN_BPM_ADMIN_USER: ${CIB7_USER}
    CIBSEVEN_BPM_ADMIN_PASSWORD_FILE: /run/secrets/cib7_admin_password
    # Removido: KEYCLOAK_URL, OIDC_*, JWT_*
```

### .env.example

```bash
# REMOVIDO: KEYCLOAK_URL, KEYCLOAK_REALM, WORKER_*_CLIENT_ID, WORKER_*_CLIENT_SECRET
# ADICIONADO:
CIB7_USER=admin
CIB7_PASSWORD=changeme_in_production
```

---

## Consequências

### Positivas
- Remove 1 container (Keycloak ~512 MB RAM)
- Remove 14 service clients, realm JSON, client secrets individuais
- Workers mais simples e resilientes (sem token refresh)
- Menos pontos de falha
- Configuração de zero para funcionar: apenas 2 variáveis de ambiente

### Negativas/Mitigações
- **Sem granularidade de permissões por worker:** mitigado com um usuário por serviço (`worker-rc`, `worker-co`, etc.) no nível da aplicação CIB Seven
- **Sem revogação de token em tempo real:** mitigado com senhas via Docker Swarm Secrets (rotação gerenciada)
- **Sem SSO para UI humana:** Cockpit/Tasklist do CIB Seven usa credenciais de admin separadas — não afeta workers

### Não afetado
- Multi-tenancy: path-based `/tenant-id/{id}` funciona sem Keycloak
- Segurança em trânsito: TLS via Traefik (Let's Encrypt) mantida
- LGPD: isolamento por tenant não depende do Keycloak
