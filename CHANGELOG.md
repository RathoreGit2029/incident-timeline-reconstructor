# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-07-18

### Added
- **Core Models**: Implemented immutable dataclasses for Events, SLA, and Causality results.
- **Config Loader**: Coded topology graph and rule configuration validations (identifying loops and orphan references).
- **Ingestion**: Stream parser checking duplicate event IDs.
- **Normalization**: Standardized Unix Epoch and ISO8601 timestamps to UTC and corrected clock skew offsets.
- **Timeline Engine**: Implemented deterministic multi-key sorting.
- **State Machine**: Enforces incident transition lifecycle rules.
- **SLA Evaluation**: Calculates Time-to-Detect (TTD), Time-to-Acknowledge (TTA), and Time-to-Mitigate (TTM).
- **Causality Engine**: Correlates triggers and mitigations using the `IncidentEventIndex`.
- **Reporter & CLI**: Added stateless JSON rendering and E2E orchestration CLI options.
- **Tests**: Placed structural tests for all validation layers in `tests/test_suite.py`.
