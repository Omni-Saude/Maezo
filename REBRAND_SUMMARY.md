# MAEZO Platform Rebrand Summary
**Date:** February 11, 2026  
**Previous Name:** MAESTRO / AUSTA  
**New Name:** MAEZO (Master of Automation for Ecosystems & Orchestration)

## Brand Identity

### English
- **Name:** MAEZO
- **Tagline:** Master of Automation for Ecosystems & Orchestration
- **Definition:** MAEZO is the Master of Automation for Ecosystems & Orchestration - a single engine that automates and orchestrates healthcare ecosystems, connecting hospitals, payers, legacy systems and AI agents into continuous clinical and financial journeys with zero friction.

### Português
- **Nome:** MAEZO
- **Tagline:** Motor de Automação de Ecossistemas e Orquestração
- **Definição:** MAEZO é um motor único que automatiza e orquestra o ecossistema de saúde, conectando hospitais, operadoras, sistemas legados e agentes de IA em jornadas contínuas, clínicas e financeiras, com zero fricção.
- **Posicionamento:** O motor que conecta hospital, operadora e parceiros em jornadas orquestradas

### Domains
- **Primary:** maezo.ai
- **Brazil:** maezo.com.br

---

## Changes Applied

### 1. Documentation (✅ Completed)
- [x] `README.md` - Updated main landing page with new branding
- [x] `helm/README.md` - Infrastructure documentation
- [x] `docs/ADRs/*.md` - Architecture Decision Records
- [x] `docs/Pendencias para desenvolvedores/*.md` - Developer documentation

### 2. Configuration Files (✅ Completed)
- [x] `config/keycloak/austa-bpm-realm.json` → `maezo-bpm-realm.json` content updated
  - Realm: `austa-bpm` → `maezo-bpm`
  - Display name: `AUSTA BPM Platform` → `MAEZO BPM Platform`
  - Group: `austa-hospital` → `hospital-a`
- [x] `.env.example`
  - `CIBSEVEN_DEFAULT_TENANT=austa-hospital` → `hospital-a`
  - `KEYCLOAK_REALM=austa-bpm` → `maezo-bpm`
- [x] `docker-compose.yml` - Updated Keycloak realm path
- [x] `Dockerfile.cdc-bridge` - Updated labels and user/group names
  - Maintainer: `devops@austa.com.br` → `devops@maezo.ai`
  - User/group: `maestro` → `maezo`

### 3. Source Code (✅ Completed)
- [x] `healthcare_platform/shared/runtime/worker_runner.py`
  - Worker ID: `maestro-worker-*` → `maezo-worker-*`
  - Description: `Maestro CIB Seven Worker Runner` → `MAEZO CIB Seven Worker Runner`
- [x] `healthcare_platform/shared/webhooks/config.py`
  - Default tenant: `austa-hospital` → `hospital-a`
- [x] `healthcare_platform/shared/domain/enums/__init__.py`
  - Tenant code: `AUSTA` → `HOSPITAL_A`
- [x] `healthcare_platform/shared/multi_tenant/credentials.py`
  - Realm: `austa-bpm` → `maezo-bpm`
- [x] `healthcare_platform/revenue_cycle/workers/*.py`
  - Portal URLs: `portal.austa.com.br` → `portal.maezo.com.br`

### 4. Test Files (✅ Completed - 61 files)
- [x] All test fixtures: `tenant_austa` → `tenant_hospital_a`
- [x] All enum references: `TenantCode.AUSTA` → `TenantCode.HOSPITAL_A`
- [x] Updated across:
  - `healthcare_platform/platform_services/tests/`
  - `healthcare_platform/clinical_operations/tests/`
  - `healthcare_platform/revenue_cycle/tests/`
  - `healthcare_platform/patient_access/tests/`

### 5. Infrastructure (✅ Completed)
- [x] `helm/maestro/Chart.yaml`
  - Chart name: `maestro` → `maezo`
  - Description updated with MAEZO branding
- [x] `helm/maestro/values.yaml`
  - Domain: `maestro.austa.com.br` → `maezo.ai`
  - Images: `maestro-workers` → `maezo-workers`
  - Images: `maestro-cdc-bridge` → `maezo-cdc-bridge`
  - Images: `maestro-webhook-receiver` → `maezo-webhook-receiver`
  - Secrets: `maestro-db-credentials` → `maezo-db-credentials`
  - Secrets: `maestro-keycloak-credentials` → `maezo-keycloak-credentials`
  - Redis: `maestro-master` → `maezo-master`
  - Dashboards: `maestro-overview` → `maezo-overview`
  - Alerts: `#alerts-maestro` → `#alerts-maezo`
  - Service name: `maestro` → `maezo`
- [x] `helm/maestro/values-dev.yaml` - Updated header and references
- [x] `helm/maestro/values-staging.yaml` - Updated header and references
- [x] `helm/maestro/templates/cib-seven-deployment.yaml`
  - Keycloak realm: `austa-bpm` → `maezo-bpm`

### 6. File/Folder Renames (⏳ Pending - Requires manual action)
The following renames should be done via git to preserve history:

```bash
# Keycloak realm file
git mv config/keycloak/austa-bpm-realm.json config/keycloak/maezo-bpm-realm.json

# Helm chart directory
git mv helm/maestro helm/maezo
```

---

## Key Technical Notes

### Helm Template Functions
The Helm template helper functions in `helm/maestro/templates/_helpers.tpl` retain their original names (e.g., `maestro.name`, `maestro.fullname`) as these are internal function definitions referenced throughout templates. These function names are implementation details and don't affect external branding.

### Domain Strategy
- **Primary global domain:** `maezo.ai` (for international presence)
- **Brazil operations:** `maezo.com.br` (for local market)
- Portal URLs updated to `portal.maezo.com.br`

### Tenant Naming
- Previous reference tenant: `austa-hospital`
- New reference tenant: `hospital-a`
- Maintains multi-tenant structure with AMH units unchanged

### Docker Images
Repository paths updated:
- `ghcr.io/rodaquino-omni/maestro-*` → `ghcr.io/rodaquino-omni/maezo-*`

---

## Verification Checklist

Run these commands to verify the rebrand:

```bash
# Check for remaining MAESTRO references (should be minimal - only in internal templates)
grep -r "MAESTRO\|Maestro\|maestro" --exclude-dir=node_modules --exclude-dir=.git --exclude="REBRAND_SUMMARY.md" .

# Check for remaining AUSTA references
grep -r "AUSTA\|Austa\|austa" --exclude-dir=node_modules --exclude-dir=.git --exclude="REBRAND_SUMMARY.md" .

# Verify test files updated
grep -r "tenant_austa\|TenantCode.AUSTA" healthcare_platform/

# Verify Keycloak realm
cat config/keycloak/austa-bpm-realm.json | head -5
```

---

## Next Steps

1. **Execute Git Renames** (preserve history):
   ```bash
   git mv config/keycloak/austa-bpm-realm.json config/keycloak/maezo-bpm-realm.json
   git mv helm/maestro helm/maezo
   ```

2. **Update CI/CD Pipelines:**
   - Update image build tags: `maestro-*` → `maezo-*`
   - Update deployment namespaces: `maestro` → `maezo`
   - Update registry paths if needed

3. **Update External Services:**
   - Configure DNS for `maezo.ai` and `maezo.com.br`
   - Update SSL certificates
   - Configure CDN/Load balancers

4. **Communication:**
   - Update GitHub repository description
   - Update README badges and links
   - Notify team members of the rebrand
   - Update any external documentation or wikis

5. **Monitoring & Observability:**
   - Update Grafana dashboard titles
   - Update Prometheus alert labels
   - Update logging namespaces
   - Update Slack alert channels

---

## Impact Assessment

### Zero Impact (No code changes needed)
- BPM processes (BPMN/DMN files) - tenant-agnostic
- External Task API integration - uses generic patterns
- Database schema - no hardcoded strings
- FHIR resources - use standard profiles

### Low Impact (Configuration only)
- Keycloak realm and clients - one-time import
- Kubernetes namespaces - update helm values
- Environment variables - update .env files

### Medium Impact (Requires coordination)
- Container image names - update CI/CD
- Domain names - update DNS and certificates
- Monitoring dashboards - update labels

---

## Rollback Plan

If rollback is needed, revert commits in this order:

1. Git revert file/folder renames
2. Git revert configuration changes
3. Git revert code changes
4. Git revert documentation changes

All changes are in git history and can be safely reverted.

---

**Rebrand completed successfully! 🎉**
