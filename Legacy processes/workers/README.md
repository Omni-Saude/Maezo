# Legacy Camunda8 Workers

**Status:** Reference Implementation  
**Purpose:** Source code from previous Camunda8 implementation for migration to CIB7  
**Last Updated:** February 2026

## Overview

This directory contains the complete Python worker implementation from the previous Camunda8 (Zeebe) project. These workers are **working production code** that need **minor adjustments** (approximately <10% refactoring) to work with CIB7.

## Structure

```
workers/
├── camunda8-implementation/    # Original working code
│   ├── revenue-cycle/          # Billing, coding, glosa, collection
│   ├── clinical/               # Clinical alerts and documentation
│   └── shared/                 # Common utilities and base classes
└── migration-notes/            # Migration guidance
    ├── MIGRATION_GUIDE.md      # Step-by-step migration process
    ├── refactor-checklist.md   # What needs updating per worker
    └── api-mapping.md          # Camunda8 → CIB7 API changes
```

## Key Differences: Camunda8 → CIB7

| Aspect | Camunda8 (Zeebe) | CIB7 |
|--------|------------------|------|
| **Protocol** | gRPC | REST (HTTP long-polling) |
| **Client Library** | `pyzeebe` | `camunda-external-task-client-python3` v4.5.0 |
| **Task Fetching** | `@job(task_type="...")` decorator | `fetchAndLock()` with topic |
| **Task Completion** | `job.set_success()` | `complete()` with variables |
| **Error Handling** | `job.set_failure()`, `job.throw_error()` | `handleFailure()`, `handleBpmnError()` |
| **Variables** | Direct dict access | Typed variables object |
| **Authentication** | OAuth2 (Camunda Cloud) | Optional (Basic Auth, OAuth2, or none) |

## Migration Approach

1. **Keep business logic intact** — The core algorithms, FHIR transformations, TISS generation, and ML models should not change
2. **Replace client layer** — Swap `pyzeebe` imports with `camunda-external-task-client-python3`
3. **Update decorators** — Replace `@job()` with explicit `fetchAndLock()` calls
4. **Adjust error handling** — Map Zeebe error codes to BPMN error codes
5. **Add tenant markers** — Include `tenantId` in all API calls (see ADR-002)
6. **Update configuration** — Change from Zeebe gateway endpoint to CIB7 REST endpoint

## Why This Code is Valuable

✅ **Proven business logic** — Already tested in production  
✅ **Real-world patterns** — Shows actual healthcare workflows  
✅ **Error handling** — Contains learned failure scenarios  
✅ **Integration points** — Shows FHIR, ERP, and external API patterns  
✅ **Performance tuning** — Contains optimization lessons  

## Usage for AI Training

The intelligence system will learn:
- How External Task workers are structured
- Business logic patterns for healthcare revenue cycle
- Error handling strategies
- Integration patterns with FHIR, TISS, ANS standards
- Multi-step orchestration patterns
- Logging and observability patterns

## Next Steps

1. **Copy your Camunda8 workers** into `camunda8-implementation/` folders
2. **Review migration-notes/** to understand refactoring needs
3. **Run intelligence system retrain** to learn from real code
4. **Use AI to generate CIB7 versions** based on learned patterns

---

**Note:** This code is for reference and learning. New implementations should follow ADR-003 patterns and use `camunda-external-task-client-python3` v4.5.0.
