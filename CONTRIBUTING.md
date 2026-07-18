# Contributing Guidelines

This document specifies repository development guidelines, layering structures, and coding standards.

---

## 1. Development Principles
- **Unidirectional Dependencies**: Upper layers depend on lower layers. Lower layers must have **zero imports** or awareness of upper layers.
- **Strict Immutability**: All domain models and transition results are frozen. Mutating objects in-place is disallowed.
- **Standard Library Only**: Third-party packages (e.g. `pandas`, `jsonschema`) are disallowed.

---

## 2. Layering Architecture

```
[ CLI ] -> [ Reporter ] -> [ Causality ] -> [ SLA ] -> [ State Machine ] -> [ Timeline Engine ] -> [ Parser ] -> [ Models ]
```

---

## 3. Extension Protocols

### How to Add a Parser
1. Create a class implementing the `BaseParser` interface defined in `src/parser/base.py`.
2. Implement the `parse_file(self, path: Path) -> List[RawEvent]` method.
3. Import and instantiate the new parser in `src/cli.py`.

### How to Add SLA Rules
1. Add new metric threshold configurations to `config/rules.json` and validate them in `src/config.py`.
2. Extend the `SLAValidation` model class in `src/models.py`.
3. Add the logic to the `SLACalculator._calculate_incident_sla()` method in `src/rules/sla.py`.

### How to Add Causality Rules
1. Add rule configurations to `config/rules.json`.
2. Extend `CausalityResult` in `src/rules/causality.py`.
3. Implement matching routines in `CausalityEngine._analyze_incident_causality()`.

---

## 4. Definition of Done (DoD)
- Code is fully typed with type-hints.
- Test coverage for new paths is implemented in `tests/test_suite.py`.
- No mutable collections are left open (convert lists to tuples inside `__post_init__`).
- Execution is completely deterministic (no random states, local environment time offsets are adjusted).
- Passes the test suite successfully.
