import sys
import argparse
import json
from pathlib import Path
from src.exceptions import ReconstructorError
from src.config import TopologyConfig, EngineRules
from src.parser.jsonl_parser import JsonlParser
from src.parser.time_aligner import TimeAligner
from src.engine import TimelineEngine
from src.state import IncidentStateMachine
from src.rules.sla import SLACalculator
from src.rules.causality import CausalityEngine
from src.reporter import IncidentReporter

def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="Incident Timeline Reconstructor CLI.")
    parser.add_argument("--config", required=True, help="Path to rules and topology config directory.")
    parser.add_argument("--input", required=True, nargs="+", help="Paths to raw transaction log JSONL files.")
    parser.add_argument("--output", help="Path to write JSON timeline report output file.")
    parser.add_argument("--pretty", action="store_true", help="Print human-readable details to stdout.")
    parser.add_argument("--version", action="version", version="0.1.0")
    return parser.parse_args(args_list)

def main(args_list=None) -> int:
    try:
        args = parse_args(args_list)
    except SystemExit as e:
        return e.code

    config_dir = Path(args.config)
    topology_path = config_dir / "topology.json"
    rules_path = config_dir / "rules.json"

    # 1. Load Configurations
    try:
        topology = TopologyConfig.load_from_file(topology_path)
        rules = EngineRules.load_from_file(rules_path)
    except ReconstructorError as e:
        sys.stderr.write(f"Configuration Loading Failed: {e}\n")
        return 1

    # 2. Ingest Logs
    raw_events = []
    parser = JsonlParser()
    for input_file in args.input:
        try:
            raw_events.extend(parser.parse_file(Path(input_file)))
        except ReconstructorError as e:
            sys.stderr.write(f"Ingestion Invalidation: {e}\n")
            return 1

    # 3. Normalize Events & Timestamps
    aligner = TimeAligner(topology.services)
    normalized_events = []
    for raw in raw_events:
        try:
            normalized_events.append(aligner.align_and_normalize(raw))
        except ReconstructorError as e:
            sys.stderr.write(f"Normalization Error: {e}\n")
            return 1

    # 4. Timeline Reconstruction
    engine = TimelineEngine(normalized_events)

    # 5. Incident State Machine Validation
    machine = IncidentStateMachine()
    transitions = machine.validate_timeline(engine.timeline)

    # 6. SLA Evaluation
    sla_calc = SLACalculator(rules)
    sla_results = sla_calc.evaluate_sla(engine.timeline)

    # 7. Causality Correlation
    causality_engine = CausalityEngine(rules)
    causality_results = causality_engine.analyze_causality(engine.timeline)

    # 8. Report Generation
    report_dict = IncidentReporter.generate_report_dict(
        timeline=engine.timeline,
        transitions=transitions,
        sla_results=sla_results,
        causality_results=causality_results
    )

    # Output Presentation
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report_dict, f, indent=2, sort_keys=True)
        except OSError as e:
            sys.stderr.write(f"Failed to write output file: {e}\n")
            return 1

    if args.pretty:
        print(IncidentReporter.generate_human_readable(report_dict))
    else:
        # Default behavior: print deterministic JSON report to stdout
        print(json.dumps(report_dict, indent=2, sort_keys=True))

    return 0

if __name__ == "__main__":
    sys.exit(main())
