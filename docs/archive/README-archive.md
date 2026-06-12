# Archive Directory

**Date:** 2026-02-16
**Phase:** Phase 3 — Worker Batch Refactoring

## Archival Policy

This directory contains legacy v1 workers and BPMNs that were replaced during the Phase 3 v1→v2 migration. Files are preserved for:

- Historical reference and audit trail
- Rollback capability if v2 workers need debugging
- Code comparison between v1 and v2 patterns

## Structure

- `workers/` — 47 v1 workers + 8 associated test files (archived from revenue_cycle sub-packages)
- `bpmn/` — 4 legacy BPMN files replaced by centralized SP-RC files

## Do Not Delete

These files are intentionally preserved. Do not remove them without team lead approval.
