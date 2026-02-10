# Revenue Cycle TASY Integration (GAP-03 Fix)

> Implemented: 2026-02-10 | Fixes GAP-03 from TASY_GAP_ANALYSIS.md

## Summary

Integrated Revenue Cycle workers with real TASY billing APIs, replacing mock/hardcoded responses. Previously only 2/181 billing endpoints were used (`get_billing_account`, `get_billing_items`). This change adds 5 new billing API methods and 3 domain-specific adapters.

## Changes Overview

### 1. TasyApiClient - New Billing Methods

**File**: `healthcare_platform/shared/integrations/tasy_api_client.py`

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| `post_billing_sync` | POST | `/api/v1/billing/sync` | Sync billing data to ERP |
| `get_payments` | GET | `/api/v1/billing/payments` | Fetch payment records by date range |
| `get_receivables` | GET | `/api/v1/billing/receivables` | Fetch receivable/título records |
| `post_pix_payment` | POST | `/api/v1/billing/pix/payments` | Create PIX payment transaction |
| `get_pix_status` | GET | `/api/v1/billing/pix/payments/{id}/status` | Check PIX payment status |

All methods added to `TasyApiClientProtocol`, `TasyApiClient`, and `StubTasyApiClient`.

### 2. New Adapters (Tasy-to-FHIR)

| Adapter | File | FHIR Resource | TASY Tables | Operations |
|---------|------|---------------|-------------|------------|
| `TasyPricingAdapter` | `pricing_adapter.py` | ChargeItemDefinition | TABELA_PRECO | 36 combinations (6 types x 6 editions: Brasindice/SIMPRO) |
| `TasyPaymentAdapter` | `payment_adapter.py` | PaymentReconciliation | PAGAMENTO | 9 PIX endpoints (initiation, confirmation, refund, status, reconciliation, receipt, e2e lookup, batch, settlement) |
| `TasyInsuranceAuthAdapter` | `insurance_auth_adapter.py` | ClaimResponse | AUTORIZACAO | 9 auth endpoints (submit, status, details, renew, cancel, appeal, batch, audit, attachment) |

### 3. Fixed Workers

#### `export_to_erp_worker.py`
- **Before**: `_sync_to_tasy()` returned mock `f"TASY-{uuid4()}"`
- **After**: Calls `TasyApiClient.post_billing_sync()` with real billing data
- Accepts `tasy_api_client` via dependency injection
- Validates `account_id` presence before sync

#### `reconcile_daily_worker.py`
- **Before**: Hardcoded `total_received = Money.brl(47500.50)`, `payment_count = 45`
- **After**: Fetches real data via `TasyApiClient.get_payments()` and `get_receivables()`
- Calculates `total_received` from sum of `VL_PAGAMENTO`
- Determines matched/unmatched from `IE_CONCILIADO` flag
- Falls back to task_variables when no API client (testing)

### 4. CDC Fallback Poller Update

**File**: `healthcare_platform/shared/integrations/cdc_fallback_poller.py`

Added 2 new tables to `DEFAULT_TABLE_CONFIGS`:

| Table | Priority | Interval | Kafka Topic |
|-------|----------|----------|-------------|
| PAGAMENTO | HIGH | 120s | tasy.AUSTA.PAGAMENTO |
| AUTORIZACAO | HIGH | 180s | tasy.AUSTA.AUTORIZACAO |

### 5. Tests

**File**: `tests/revenue_cycle/test_tasy_billing_integration.py`

- `TestTasyApiClientBillingMethods` - 6 tests for new StubTasyApiClient billing methods
- `TestExportToERPWorkerIntegration` - 2 tests (real API call, missing client error)
- `TestReconcileDailyWorkerIntegration` - 1 test (payment fetching + reconciliation)
- `TestCDCFallbackPollerTables` - 8 tests (PAGAMENTO/AUTORIZACAO config validation)

## Billing Endpoint Coverage (After Fix)

```
Before:  2 / 181 endpoints (1.1%)
After:   7 / 181 endpoints (3.9%)  +5 new methods
Adapters: 3 new (pricing, payment, insurance_auth)
CDC tables: +2 (PAGAMENTO, AUTORIZACAO)
```

## Remaining GAP-03 Work

- Additional billing endpoints (174 remaining) for full coverage
- MV Soul integration (still mocked in `_sync_to_mv_soul`)
- TISS XML generation for ANS submission
- Batch billing operations
- Glosa/denial management API integration
