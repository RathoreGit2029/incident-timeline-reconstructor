# Architecture Decision Records (ADRs)

This document indexes the architectural design logs for the Incident Timeline Reconstructor.

---

## ADR-001: Immutable Data Models
- **Status**: Accepted
- **Motivation**: In-place mutations during processing passes make concurrent, multi-incident processing error-prone.
- **Trade-offs**: Incurs slight memory allocation overhead as new states instantiate new dataclasses, but guarantees state isolation and prevents bugs.

---

## ADR-002: Unidirectional Processing Pipeline
- **Status**: Accepted
- **Motivation**: Keeps components decoupled, facilitating isolated testing.
- **Trade-offs**: Forces strict conversion passes, but ensures clean division of concerns.

---

## ADR-003: Table-driven State Machine
- **Status**: Accepted
- **Reason**: Simplifies state path validation and prevents logic bugs when checking state transitions.
- **Consequences**: Changes to the transition lifecycle require updates to configuration tables rather than code refactoring.

---

## ADR-004: Indexed Causality Engine
- **Status**: Accepted
- **Reason**: Resolves causality triggers and mitigations using a single indexed view (`IncidentEventIndex`), preventing multiple timeline scans.
- **Consequences**: Creates a minor memory overhead, but improves runtimes.

---

## ADR-005: Stateless Presentation Layer
- **Status**: Accepted
- **Motivation**: Prevents presentation logic (JSON generation, sorting format overrides) from altering domain models.
- **Trade-offs**: Output parsing requires a dedicated formatter module (`reporter.py`), but guarantees domain data purity.
