# Technical Roadmap

This document outlines planned capabilities and extensions for the Incident Timeline Reconstructor.

---

## Phase 1: Alternative Source Input Parsers
- **YAML Log Loader**: Implement parsing for YAML-formatted application alerts and deploys.
- **XML Event Loader**: Support legacy enterprise system XML event logs.
- **CSV Telemetry Parser**: Allow direct ingestion of system error csv files.

---

## Phase 2: Observability & Integrations
- **Prometheus Metrics Exporter**: Output incident compliance and SLA statistics to monitoring servers.
- **HTML Postmortem Report Generator**: Render reports to rich HTML files with embedded timeline visualizations.
- **Opentelemetry Hook Integration**: Integrate trace logs directly as timeline inputs.

---

## Phase 3: Processing Enhancements
- **Parallel File Ingestion**: Ingest multiple large JSONL files concurrently using Python's `multiprocessing` or `concurrent.futures`.
- **Plugin System**: Build support for custom causality rules loaded dynamically from external scripts.
