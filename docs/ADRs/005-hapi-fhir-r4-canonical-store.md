# ADR-005: HAPI FHIR R4 7.4.0 as Canonical Data Store

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, Integration Lead, Clinical Informatics

## Context

The platform integrates two different ERPs (Tasy and MV Soul) with different data models, terminologies, and API patterns. Workers need a unified view of patient, coverage, encounter, and observation data regardless of which ERP originated it.

ANS (Agência Nacional de Saúde Suplementar) increasingly mandates FHIR R4 for interoperability in Brazilian healthcare.

Two versions were considered: HAPI FHIR v6 (referenced in DOCX architecture document) and HAPI FHIR v7.4.0 (referenced in MD technical document). Version 7.x introduced significant improvements in search performance, bulk operations, and R4B support.

## Decision

We will deploy **HAPI FHIR R4 7.4.0** (JPA Server) as the canonical data store for clinical and administrative data. This resolves the version discrepancy between the two architecture documents in favor of v7.4.0.

- **Core FHIR resources:** Patient, Coverage, Encounter, Observation, Claim, ClaimResponse, Practitioner, Organization, Location
- **Custom profiles:** AUSTA-specific StructureDefinitions constrain resources to platform needs
- **Single source of truth:** workers query FHIR (not ERPs directly) for patient demographics, coverage, clinical observations
- **ERP adapters** translate ERP data into FHIR resources and write to FHIR server
- **Storage:** PostgreSQL 16 (separate database within shared cluster)

## Consequences

**Positive:**

- Workers are ERP-agnostic. Eligibility worker queries FHIR `Coverage` resources regardless of whether patient is in Tasy or MV. Dramatically simplifies worker code.
- Regulatory alignment with ANS FHIR mandates. Positions AUSTA ahead of compliance deadlines.
- v7.4.0 brings 30–40% search performance improvement over v6, bulk export, better R4B compatibility.

**Negative:**

- FHIR is verbose (2–5KB per Patient resource). At scale requires careful indexing and search parameter tuning. *Mitigation:* HAPI FHIR JPA configurable indexes, Redis caching for frequent lookups.
- Maintaining FHIR ↔ ERP sync requires reliable adapters. Any mismatch = data inconsistency. *Mitigation:* bidirectional reconciliation checks, discrepancies flagged as process incidents.
