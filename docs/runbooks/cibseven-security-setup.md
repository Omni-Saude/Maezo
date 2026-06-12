# CIB Seven — Setup de Segurança: Usuários, Grupos e Tenants

> **Quando executar:** na primeira configuração do ambiente (dev ou produção) ou ao adicionar
> um novo membro ao time.
> **Onde acessar:** `http://<ip>:<porta>/cibseven/app/admin/`

---

## Visão Geral do Modelo de Acesso

```
┌─────────────────────────────────────────────────────────┐
│                    USUÁRIOS HUMANOS                      │
│  angelo, ...outros membros do time                       │
│  Grupo: dev-admins → Cockpit + Admin (acesso total)      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   SERVICE ACCOUNTS                       │
│  worker_svc  → Grupo: workers   → External Tasks + DMN  │
│  deploy_svc  → Grupo: deployers → Deploy BPMN/DMN       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    CONTA ADMIN                           │
│  admin → superAdmin → senha trocada, uso emergencial     │
└─────────────────────────────────────────────────────────┘

❌  demo → DELETAR
```

### Por que separar?

| Problema sem separação | Com separação |
|------------------------|---------------|
| Credencial `admin/admin` nos workers — se vazar, acesso total | `worker_svc` só pode processar tasks |
| Impossível auditar "quem fez o quê" | Cada ação tem uma identidade rastreável |
| Rotação de senha do admin quebra os workers | Senhas independentes por função |

---

## Passo 1 — Trocar a Senha do Admin

> Faça isso **antes** de qualquer outra coisa.

1. Acesse `Admin` → `Users` → clique em `admin`
2. Clique em **Change Password**
3. Defina uma senha forte (mínimo 16 caracteres, alfanumérico + símbolos)
4. Guarde no gerenciador de senhas do time (Bitwarden, 1Password, etc.)

---

## Passo 2 — Deletar o Usuário `demo`

1. `Admin` → `Users` → localize `demo`
2. Clique no ícone de lixeira (Delete)
3. Confirme a exclusão

---

## Passo 3 — Criar os Grupos

Vá em `Admin` → `Groups` → **Create new group** para cada um:

| Group ID | Nome de exibição | Descrição |
|----------|-----------------|-----------|
| `dev-admins` | Dev Admins | Membros do time — acesso total |
| `workers` | Workers Service | Service account dos workers Python |
| `deployers` | Deployers | Service account do pipeline de deploy |

---

## Passo 4 — Criar os Service Accounts

Vá em `Admin` → `Users` → **Create new user**:

### `worker_svc`
| Campo | Valor |
|-------|-------|
| User ID | `worker_svc` |
| First name | `Worker` |
| Last name | `Service` |
| Email | (deixar em branco) |

Após criar: clique em **Set Password** → defina senha forte → **desmarque** "User must change password".

Depois: `Admin` → `Groups` → `workers` → **Add member** → `worker_svc`

### `deploy_svc`
| Campo | Valor |
|-------|-------|
| User ID | `deploy_svc` |
| First name | `Deploy` |
| Last name | `Service` |

Após criar: defina senha → adicione ao grupo `deployers`.

---

## Passo 5 — Criar Usuários Humanos

Para cada membro do time, repita em `Admin` → `Users` → **Create new user**:

| Campo | Valor |
|-------|-------|
| User ID | nome em minúsculo (ex: `angelo`) |
| First name / Last name | nome completo |
| Email | email corporativo |

Após criar: defina senha temporária e **marque** "User must change password on next login".

Adicione ao grupo `dev-admins`:
`Admin` → `Groups` → `dev-admins` → **Add member** → `<nome>`

---

## Passo 6 — Configurar Autorizações (Authorizations)

> `Admin` → `Authorizations`

### Para o grupo `workers` — permissões mínimas para processar tasks

| Resource Type | Resource ID | Permissions |
|--------------|-------------|-------------|
| Process Definition | `*` | READ |
| Process Instance | `*` | READ, UPDATE |
| Decision Definition | `*` | READ |
| External Task | `*` | READ, CREATE, UPDATE |
| Task | `*` | READ, UPDATE |

**Como adicionar:**
1. Selecione o Resource Type no dropdown
2. Resource ID: `*` (todos)
3. Marque as permissões
4. Identity Type: `Group` → ID: `workers`
5. Clique em **Add**

### Para o grupo `deployers` — permissões para deploy de BPMN/DMN

| Resource Type | Resource ID | Permissions |
|--------------|-------------|-------------|
| Deployment | `*` | CREATE, READ, DELETE |
| Process Definition | `*` | READ |
| Decision Definition | `*` | READ |

### Para o grupo `dev-admins` — acesso total

| Resource Type | Resource ID | Permissions |
|--------------|-------------|-------------|
| `*` (All) | `*` | ALL |

### Acesso às aplicações (Cockpit / Admin)

| Grupo | Application: cockpit | Application: admin | Application: tasklist |
|-------|----------------------|-------------------|----------------------|
| `dev-admins` | ✅ ALL | ✅ ALL | ✅ ALL |
| `deployers` | ✅ READ | ❌ | ❌ |
| `workers` | ❌ | ❌ | ❌ |

Para configurar: Resource Type = `Application` → Resource ID = `cockpit` / `admin` / `tasklist`.

---

## Passo 7 — Associar Usuários aos Tenants

Cada usuário precisa ser membro dos tenants para ver os processos daquele domínio.

`Admin` → `Tenants` → selecione cada tenant → aba **Members** → **Add member**:

| Tenant | Membros |
|--------|---------|
| `Maezo_rc` | `worker_svc`, `deploy_svc`, todos os humanos |
| `Maezo_co` | `worker_svc`, `deploy_svc`, todos os humanos |
| `Maezo_pa` | `worker_svc`, `deploy_svc`, todos os humanos |
| `Maezo_ps` | `worker_svc`, `deploy_svc`, todos os humanos |
| `Maezo_ce` | `worker_svc`, `deploy_svc`, todos os humanos |

> **Atenção:** o usuário `admin` é superAdmin e vê todos os tenants automaticamente,
> não precisa ser adicionado.

---

## Passo 8 — Atualizar Credenciais no Projeto

Após criar os service accounts, atualize os arquivos de ambiente:

### `.env.dev`
```bash
# Antes
CIB7_USER=admin
CIB7_PASSWORD=admin

# Depois
CIB7_USER=worker_svc
CIB7_PASSWORD=<senha_definida_no_passo_4>
```

### Deploy manual (CLI)
```bash
# Usar deploy_svc para publicar processos
python scripts/deploy/deploy_processes.py \
  --url http://<ip>:<porta>/engine-rest \
  --user deploy_svc \
  --password <senha_deploy_svc> \
  --domain revenue_cycle \
  --tenant-prefix Maezo
```

### Docker Swarm (produção)
```bash
# Atualizar o secret no Swarm
echo "<nova_senha_worker>" | docker secret create cib7_worker_password -

# No docker-compose.swarm.yml, separar as credenciais por função:
# CIB7_USER → worker_svc para containers de worker
# CIB7_USER → deploy_svc para o container de deploy/bootstrap
```

---

## Checklist Final de Verificação

```
[ ] Senha do admin trocada e guardada no gerenciador de senhas
[ ] Usuário demo deletado
[ ] Grupos dev-admins, workers, deployers criados
[ ] worker_svc criado + no grupo workers
[ ] deploy_svc criado + no grupo deployers
[ ] Usuários humanos criados + no grupo dev-admins
[ ] Autorizações configuradas para cada grupo
[ ] Todos os membros adicionados a todos os tenants Maezo_*
[ ] .env.dev atualizado com worker_svc
[ ] Login com worker_svc no Cockpit → deve ser NEGADO
[ ] Worker Python rodando com worker_svc → processa tasks normalmente
[ ] Login com usuário humano no Cockpit → funciona
```

---

## Troubleshooting

**Worker para de processar após troca de credenciais:**
- Verifique se `worker_svc` está no grupo `workers`
- Verifique se as autorizações de External Task estão corretas
- Verifique se `worker_svc` é membro dos tenants

**Usuário humano não vê processos do tenant Maezo_rc:**
- Adicione o usuário ao tenant em `Admin → Tenants → Maezo_rc → Members`

**"Forbidden" ao tentar fazer deploy com deploy_svc:**
- Verifique autorização `Deployment → CREATE` para o grupo `deployers`
