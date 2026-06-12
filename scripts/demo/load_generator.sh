#!/usr/bin/env bash
# load_generator.sh — Deploys demo BPMN and starts process instances in loop
#
# Usage:
#   bash scripts/demo/load_generator.sh [--instances N] [--interval SECS] [--engine URL]
#
# Defaults: 50 instances, 3s interval, http://localhost:8081/engine-rest
set -euo pipefail

INSTANCES=${INSTANCES:-50}
INTERVAL=${INTERVAL:-3}
ENGINE=${CIBSEVEN_ENGINE_URL:-http://localhost:8081/engine-rest}
BPMN_FILE="scripts/demo/SP-RC-006_DEMO.bpmn"
PROCESS_KEY="SP_RC_006_DEMO_Billing"

# Parse CLI args
while [[ $# -gt 0 ]]; do
    case $1 in
        --instances) INSTANCES="$2"; shift 2;;
        --interval)  INTERVAL="$2"; shift 2;;
        --engine)    ENGINE="$2"; shift 2;;
        *) echo "Unknown arg: $1"; exit 1;;
    esac
done

echo "============================================="
echo "MAEZO Demo Load Generator"
echo "============================================="
echo "Engine:    $ENGINE"
echo "BPMN:      $BPMN_FILE"
echo "Instances: $INSTANCES"
echo "Interval:  ${INTERVAL}s"
echo ""

# 1. Wait for engine to be ready
echo "Waiting for CIB7 engine..."
for i in $(seq 1 30); do
    if curl -sf "$ENGINE/engine" > /dev/null 2>&1; then
        echo "  Engine is UP"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  ERROR: Engine not reachable at $ENGINE"
        exit 1
    fi
    sleep 2
done

# 2. Deploy BPMN
echo ""
echo "Deploying BPMN process..."
DEPLOY_RESULT=$(curl -sf -w "\n%{http_code}" \
    -F "deployment-name=demo-billing-v1" \
    -F "enable-duplicate-filtering=false" \
    -F "deploy-changed-only=false" \
    -F "deployment-source=load-generator" \
    -F "data=@${BPMN_FILE}" \
    "$ENGINE/deployment/create" 2>&1) || true

HTTP_CODE=$(echo "$DEPLOY_RESULT" | tail -1)
BODY=$(echo "$DEPLOY_RESULT" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    DEPLOY_ID=$(echo "$BODY" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "unknown")
    echo "  Deployed: $DEPLOY_ID"
else
    echo "  Deploy response (HTTP $HTTP_CODE):"
    echo "  $BODY"
    echo ""
    echo "  Trying anyway — process may already be deployed."
fi

# 3. Verify process definition exists
echo ""
echo "Checking process definition..."
DEF_RESULT=$(curl -sf "$ENGINE/process-definition/key/$PROCESS_KEY" 2>&1) || true
if echo "$DEF_RESULT" | grep -q '"id"'; then
    DEF_ID=$(echo "$DEF_RESULT" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "unknown")
    echo "  Process definition: $DEF_ID"
else
    echo "  ERROR: Process definition not found for key=$PROCESS_KEY"
    echo "  Response: $DEF_RESULT"
    exit 1
fi

# 4. Start process instances
echo ""
echo "Starting $INSTANCES process instances (interval: ${INTERVAL}s)..."
echo "  Press Ctrl+C to stop early"
echo ""

STARTED=0
FAILED=0

for i in $(seq 1 "$INSTANCES"); do
    # Random business key for each instance
    BIZ_KEY="DEMO-FAT-$(date +%H%M%S)-$(printf '%04d' $i)"

    RESULT=$(curl -sf -w "\n%{http_code}" \
        -H "Content-Type: application/json" \
        -d "{
            \"businessKey\": \"$BIZ_KEY\",
            \"variables\": {
                \"encounterId\": {\"value\": \"ENC-$(shuf -i 1000-9999 -n 1)\", \"type\": \"String\"},
                \"patientId\":   {\"value\": \"PAT-$(shuf -i 10000-99999 -n 1)\", \"type\": \"String\"},
                \"payerId\":     {\"value\": \"OPER-$(shuf -i 1-5 -n 1)\", \"type\": \"String\"},
                \"procedures\":  {\"value\": \"[\\\"PROC-$(shuf -i 100-999 -n 1)\\\",\\\"PROC-$(shuf -i 100-999 -n 1)\\\"]\", \"type\": \"String\"},
                \"contractId\":  {\"value\": \"CTR-$(shuf -i 1-20 -n 1)\", \"type\": \"String\"}
            }
        }" \
        "$ENGINE/process-definition/key/$PROCESS_KEY/start" 2>&1) || true

    CODE=$(echo "$RESULT" | tail -1)
    if [ "$CODE" = "200" ]; then
        STARTED=$((STARTED + 1))
        INST_ID=$(echo "$RESULT" | head -n -1 | python -c "import sys,json; print(json.load(sys.stdin)['id'][:8])" 2>/dev/null || echo "?")
        echo "  [$i/$INSTANCES] Started $BIZ_KEY (instance: $INST_ID...)"
    else
        FAILED=$((FAILED + 1))
        echo "  [$i/$INSTANCES] FAILED $BIZ_KEY (HTTP $CODE)"
    fi

    # Sleep between instances (except last)
    if [ "$i" -lt "$INSTANCES" ]; then
        sleep "$INTERVAL"
    fi
done

echo ""
echo "============================================="
echo "Done. Started: $STARTED  Failed: $FAILED"
echo "============================================="
echo ""
echo "Each instance creates 6 external tasks for billing workers:"
echo "  billing.validate_claim"
echo "  billing.calculate_charges"
echo "  billing.apply_contract_rules"
echo "  billing-generate-tiss-xml"
echo "  billing-validate-tiss-schema"
echo "  billing.submit_to_payer"
echo ""
echo "Check Grafana at http://localhost:3000 (admin/admin)"
