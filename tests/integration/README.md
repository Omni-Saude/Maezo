# Integration Tests

Comprehensive integration test suite for the Healthcare Orchestration Platform, validating BPMN process deployments, DMN decision tables, and worker connectivity against a running CIB7 engine.

## Directory Structure

```
tests/integration/
├── README.md                          # This file
├── conftest.py                        # Shared pytest configuration
├── bpmn/                              # BPMN process integration tests
│   ├── conftest.py                    # CIB7 fixtures (cib7_url, cib7_client, bpmn_files, worker_topics)
│   ├── test_deployment.py             # Validate all BPMN files deploy to CIB7
│   ├── test_namespace_compliance.py   # ADR-019 R1: Namespace naming rules
│   ├── test_topic_connectivity.py     # ADR-019 R7: Topic availability
│   ├── test_process_instantiation.py  # Process instantiation smoke tests
│   └── __init__.py
├── test_revenue_dmn_integration.py    # Revenue cycle DMN tables
├── test_clinical_dmn_integration.py   # Clinical operations DMN tables
├── test_platform_services_dmn_integration.py  # Platform services DMN tables
├── test_patient_access_dmn_integration.py     # Patient access DMN tables
├── patient_access/                    # Domain-specific integration tests
├── clinical_operations/               # (as domains expand)
└── revenue_cycle/                     # (as domains expand)
```

## Prerequisites

- **Docker** (20.10+) with Docker Compose (1.29+)
- **Python** 3.11+
- **pytest** 7.0+ with plugins: `pytest-requests`, `pytest-timeout`
- **requests** 2.28+

Install Python dependencies:

```bash
pip install -r requirements-dev.txt
```

## Running Locally

### 1. Start CIB7 Engine (Background)

```bash
docker compose -f docker-compose.test.yml up -d cib7
```

Wait 15-20 seconds for the engine REST endpoint to be available (health check at `http://localhost:8080/engine-rest/version`).

Verify readiness:

```bash
curl -s http://localhost:8080/engine-rest/version | jq .
```

### 2. Run All Integration Tests

```bash
pytest tests/integration/bpmn/ -v --tb=short
```

Expected output:
```
test_deployment.py::TestDeployAllBpmnFiles::test_deploy_all_bpmn_files PASSED
test_namespace_compliance.py::TestNamespaceCompliance::test_all_bpmn_comply_with_adr019 PASSED
test_topic_connectivity.py::TestTopicConnectivity::test_all_topics_available PASSED
test_process_instantiation.py::TestProcessInstantiation::test_instantiate_processes PASSED
```

### 3. Teardown

```bash
docker compose -f docker-compose.test.yml down --volumes
```

Remove orphaned containers/topics if necessary:

```bash
docker system prune -f
```

## Running Specific Modules

**Deployment tests only:**
```bash
pytest tests/integration/bpmn/test_deployment.py -v
```

**Namespace compliance (ADR-019 R1):**
```bash
pytest tests/integration/bpmn/test_namespace_compliance.py -v
```

**Topic connectivity (ADR-019 R7):**
```bash
pytest tests/integration/bpmn/test_topic_connectivity.py -v
```

**Process instantiation:**
```bash
pytest tests/integration/bpmn/test_process_instantiation.py -v
```

**DMN tests only:**
```bash
pytest tests/integration/test_*_dmn_integration.py -v
```

**Single domain (e.g., patient access):**
```bash
pytest tests/integration/patient_access/ -v
```

## CI/CD Integration

Integration tests run automatically on **all PRs** that modify:

- `healthcare_platform/**/*.bpmn` (Process definitions)
- `healthcare_platform/**/workers/*.py` (External task workers)
- `tests/integration/**` (Integration tests themselves)

**GitHub Actions Workflow:**

The CI/CD pipeline (`github/workflows/integration-tests.yml`) performs:

1. Start CIB7 engine in Docker
2. Run `pytest tests/integration/bpmn/ -v --junit-xml=results.xml`
3. Upload results and coverage reports
4. Tear down engine on pass or fail

See `.github/workflows/bpmn-validation.yml` for detailed configuration.

## Test Coverage Table

| Coverage Area | Test Module | Focus | ADR |
|---|---|---|---|
| **Deployment** | `test_deployment.py` | HTTP 200 on deployment endpoint | ADR-001 |
| **Namespace Compliance** | `test_namespace_compliance.py` | Process IDs follow naming convention | ADR-019 R1 |
| **Topic Connectivity** | `test_topic_connectivity.py` | All BPMN topics registered with workers | ADR-019 R7 |
| **Process Instantiation** | `test_process_instantiation.py` | Processes start without error | ADR-016 |
| **DMN Integration** | `test_*_dmn_integration.py` | DMN rule execution and output | ADR-007 |
| **Worker Integration** | Domain-specific tests | Worker invocation and callbacks | ADR-003 |

## Fixtures Reference

**Location:** `tests/integration/bpmn/conftest.py`

### `cib7_url`

- **Scope:** Session
- **Returns:** `str`
- **Usage:** Base URL for CIB7 REST API
- **Default:** `http://localhost:8080/engine-rest`
- **Override:** Set `CIB7_URL` environment variable

```python
def test_example(cib7_url):
    assert "engine-rest" in cib7_url
```

### `cib7_client`

- **Scope:** Session
- **Returns:** `requests.Session` with automatic retries
- **Usage:** HTTP client for CIB7 engine
- **Behavior:** Waits up to 30 seconds for engine availability; retries on 5xx errors

```python
def test_deployment(cib7_client, cib7_url):
    resp = cib7_client.post(f"{cib7_url}/deployment/create", files={...})
```

### `bpmn_files`

- **Scope:** Session
- **Returns:** `List[Path]` of all `.bpmn` files
- **Behavior:** Excludes archive directories (names starting with `.`)
- **Count:** ~25-30 files across healthcare_platform

```python
def test_all_bpmn(bpmn_files):
    assert len(bpmn_files) > 0
```

### `worker_topics`

- **Scope:** Session
- **Returns:** `Dict[str, str]` mapping topic → worker file path
- **Behavior:** Parses `TOPIC = "..."` from all `*worker*.py` files
- **Count:** ~40-50 topics across all workers

```python
def test_topic_exists(worker_topics):
    assert "claim_submission" in worker_topics
```

## Troubleshooting

### Connection Error: `Connection refused on http://localhost:8080/engine-rest`

**Cause:** CIB7 engine not started or not ready.

**Solution:**

1. Check container status:
   ```bash
   docker ps | grep cib7
   ```

2. View logs:
   ```bash
   docker compose -f docker-compose.test.yml logs cib7
   ```

3. Wait 30 seconds and retry:
   ```bash
   sleep 30
   curl -s http://localhost:8080/engine-rest/version
   ```

### HTTP 500: Deployment Failed

**Cause:** BPMN syntax error or missing worker topic.

**Solution:**

1. Validate BPMN XML:
   ```bash
   xmllint --schema camunda.xsd your_process.bpmn
   ```

2. Check worker topic availability:
   ```python
   from tests.integration.bpmn.conftest import _extract_topics_from_file
   topics = _extract_topics_from_file(Path("worker.py"))
   print(topics)
   ```

3. Review test output for specific error message.

### Orphaned Docker Topics (Kafka)

**Symptom:** Tests pass but old topics remain after teardown.

**Solution:**

```bash
docker compose -f docker-compose.test.yml down --volumes --remove-orphans
docker system prune -f --volumes
```

### Test Timeout

**Cause:** Engine slow to respond or network latency.

**Solution:**

Increase pytest timeout (default 300s):

```bash
pytest tests/integration/bpmn/ --timeout=600
```

Or set in `pytest.ini`:

```ini
[pytest]
timeout = 600
```

## Related ADRs

- **ADR-001:** CIB7 as BPM Engine (deployment target)
- **ADR-016:** Topic Naming Convention (test validation)
- **ADR-019:** BPMN Compliance Mandatory (R1 namespace, R7 topic connectivity)
- **ADR-003:** Python External Task Workers (worker integration)
- **ADR-007:** DMN Federation & Tenant Overrides (DMN test coverage)

## Examples

### Deploy and Test a Single Process

```bash
# Start engine
docker compose -f docker-compose.test.yml up -d cib7
sleep 20

# Run deployment test
pytest tests/integration/bpmn/test_deployment.py::TestDeployAllBpmnFiles -v

# Teardown
docker compose -f docker-compose.test.yml down --volumes
```

### Run Tests with Coverage Report

```bash
pytest tests/integration/bpmn/ --cov=healthcare_platform --cov-report=html
open htmlcov/index.html
```

### Local Development with Engine Running

```bash
# Terminal 1: Start engine (stays running)
docker compose -f docker-compose.test.yml up cib7

# Terminal 2: Run tests repeatedly
pytest tests/integration/bpmn/ -v --tb=short --disable-warnings -x
```

## Support

For questions or issues:

1. Check logs: `docker compose -f docker-compose.test.yml logs cib7`
2. Review test output: `pytest -vv --tb=long`
3. Consult related ADRs (see "Related ADRs" above)
4. Open an issue on GitHub with logs and test output
