# ADR-004: Debezium CDC for ERP Integration

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, Integration Lead

## Context

The platform must react to events in hospital ERPs (Philips Tasy on Oracle, MV Soul on PostgreSQL/Oracle) in near-real-time: new admissions, billing items, lab results, prescription changes. This is the primary trigger for starting BPM processes.

Three approaches evaluated:

| Approach | Latency | ERP Impact | Coverage |
|---|---|---|---|
| Polling-based | 30–60s | High (query load) | Full (any table) |
| ERP webhooks/APIs | <5s | Low | Partial (Tasy limited, MV inconsistent) |
| **CDC (transaction log)** | **1–3s** | **Near-zero** | **Full (any table)** |

Tasy provides limited REST APIs and no webhook mechanism for billing tables. Polling at 30s intervals creates significant load on the production Oracle database.

## Decision

We will use **Debezium 2.7** for Change Data Capture from both ERP databases.

- **Tasy (Oracle):** Oracle LogMiner connector captures changes from redo log
- **MV Soul (PostgreSQL):** PostgreSQL connector uses Write-Ahead Log (WAL) replication
- **Kafka topics:** `tasy.AUSTA.{TABLE_NAME}` and `mv.{TENANT}.{TABLE_NAME}`
- **Bridge service:** dedicated Python `cdc-to-bpm-bridge` consumes topics, transforms CDC events into process variables, starts process instances via CIB Seven REST API
- **Initial table whitelist:** `ATENDIMENTO`, `CONTA_MEDICA`, `ITEM_CONTA`, `PRESCRICAO`, `SINAL_VITAL` (Tasy); `ATENDIME`, `ITREG_FAT`, `REGISTRO_ALTA` (MV Soul). Expands incrementally.
- **Fallback:** polling-based integration available if Oracle LogMiner presents issues. Bridge service abstracts event source — workers and BPMN processes are unaware of origin.

## Consequences

**Positive:**

- Near-zero impact on ERP databases — CDC reads transaction logs, not application tables. Critical for production clinical systems.
- Sub-second event detection (1–3s vs 30–60s for polling). Enables time-sensitive workflows like sepsis detection.
- Complete audit trail — every change captured, including intermediate states.

**Negative:**

- Debezium Oracle connector requires supplemental logging enabled at database level. *Mitigation:* work with hospital IT early; overhead is well-documented and minimal.
- CDC captures raw row changes, not business events. Bridge must interpret column changes as meaningful events (e.g., `STATUS` change `'A'→'F'` = admission finalized). *Mitigation:* mapping externalized as config; Debezium detects schema changes.
- Initial snapshot can be large (millions of rows). *Mitigation:* plan first sync during maintenance window with appropriate Kafka retention.
