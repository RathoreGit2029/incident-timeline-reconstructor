import unittest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from src.exceptions import ConfigError, TopologyError, ValidationError
from src.config import TopologyConfig, EngineRules
from src.models import IncidentKey, RawEvent, ServiceNode, NormalizedEvent
from src.constants import EventSource, EventType, IncidentState
from src.parser.jsonl_parser import JsonlParser
from src.parser.time_aligner import TimeAligner
from src.engine import TimelineEngine
from src.state import IncidentStateMachine
from src.rules.sla import SLACalculator
from src.rules.causality import CausalityEngine
from src.cli import main as cli_main

class TestIncidentTimelineFoundation(unittest.TestCase):
    def test_incident_key_formatting(self):
        key = IncidentKey("gateway", "LatencySpike")
        self.assertEqual(str(key), "gateway:LatencySpike")

    def test_valid_topology_load(self):
        valid_data = {
            "services": [
                {"name": "gateway", "dependencies": ["auth"], "clock_skew_seconds": 0},
                {"name": "auth", "dependencies": [], "clock_skew_seconds": -5}
            ]
        }
        config = TopologyConfig.load_from_dict(valid_data)
        self.assertIn("gateway", config.services)
        self.assertEqual(config.services["auth"].clock_skew_seconds, -5)

    def test_duplicate_services(self):
        invalid_data = {
            "services": [
                {"name": "gateway", "dependencies": []},
                {"name": "gateway", "dependencies": []}
            ]
        }
        with self.assertRaises(TopologyError):
            TopologyConfig.load_from_dict(invalid_data)

    def test_orphan_dependency(self):
        invalid_data = {
            "services": [
                {"name": "gateway", "dependencies": ["unregistered_service"]}
            ]
        }
        with self.assertRaises(TopologyError):
            TopologyConfig.load_from_dict(invalid_data)

    def test_cyclic_dependency(self):
        invalid_data = {
            "services": [
                {"name": "svc_a", "dependencies": ["svc_b"]},
                {"name": "svc_b", "dependencies": ["svc_a"]}
            ]
        }
        with self.assertRaises(TopologyError):
            TopologyConfig.load_from_dict(invalid_data)

    def test_valid_rules_load(self):
        valid_rules = {
            "sla": {
                "max_acknowledgement_seconds": 900,
                "max_mitigation_seconds": 3600
            },
            "correlation": {
                "causality_window_seconds": 600,
                "debounce_window_seconds": 60
            }
        }
        rules = EngineRules.load_from_dict(valid_rules)
        self.assertEqual(rules.max_acknowledgement_seconds, 900)

    def test_negative_rules_validation(self):
        invalid_rules = {
            "sla": {
                "max_acknowledgement_seconds": -900,
                "max_mitigation_seconds": 3600
            },
            "correlation": {
                "causality_window_seconds": 600,
                "debounce_window_seconds": 60
            }
        }
        with self.assertRaises(ConfigError):
            EngineRules.load_from_dict(invalid_rules)


class TestIncidentTimelineIngestion(unittest.TestCase):
    def setUp(self):
        self.parser = JsonlParser()
        self.services = {
            "gateway": ServiceNode("gateway", clock_skew_seconds=0),
            "auth": ServiceNode("auth", clock_skew_seconds=-5)
        }
        self.aligner = TimeAligner(self.services)

    def test_valid_jsonl_parsing(self):
        content = (
            '{"event_id": "e1", "timestamp": "2026-07-18T05:00:00Z", "source": "ALERT", '
            '"event_type": "ALERT_TRIGGERED", "service": "gateway", "metadata": {"alert_name": "HighLatency"}}\n'
        )
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)

        try:
            events = self.parser.parse_file(temp_path)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_id, "e1")
            self.assertEqual(events[0].source, EventSource.ALERT)
        finally:
            temp_path.unlink()

    def test_malformed_json_parsing(self):
        content = '{"event_id": "e1", "timestamp": "2026-07-18T05:00:00Z", "source": "ALERT" \n'  # Missing closing braces
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)

        try:
            with self.assertRaises(ValidationError):
                self.parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_invalid_event_types_or_sources(self):
        content = (
            '{"event_id": "e1", "timestamp": "2026-07-18T05:00:00Z", "source": "INVALID_SRC", '
            '"event_type": "ALERT_TRIGGERED", "service": "gateway", "metadata": {"alert_name": "HighLatency"}}\n'
        )
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)

        try:
            with self.assertRaises(ValidationError):
                self.parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_missing_required_metadata(self):
        content = (
            '{"event_id": "e1", "timestamp": "2026-07-18T05:00:00Z", "source": "ALERT", '
            '"event_type": "ALERT_TRIGGERED", "service": "gateway", "metadata": {}}\n'  # Missing alert_name
        )
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)

        try:
            with self.assertRaises(ValidationError):
                self.parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_timezone_utc_timestamp(self):
        raw = RawEvent("e1", "2026-07-18T05:00:00Z", EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})
        norm = self.aligner.align_and_normalize(raw)
        self.assertEqual(norm.timestamp, datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc))

    def test_timezone_offset_timestamp(self):
        raw = RawEvent("e1", "2026-07-18T10:30:00+05:30", EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})
        norm = self.aligner.align_and_normalize(raw)
        # 10:30:00 +05:30 resolves to 05:00:00 UTC
        self.assertEqual(norm.timestamp, datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc))

    def test_unix_epoch_timestamp(self):
        raw = RawEvent("e1", "1784350800", EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})
        norm = self.aligner.align_and_normalize(raw)
        self.assertEqual(norm.timestamp, datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc))

    def test_clock_skew_correction(self):
        raw = RawEvent("e1", "2026-07-18T05:00:00Z", EventSource.ALERT, EventType.ALERT_TRIGGERED, "auth", {"alert_name": "HighLatency"})
        norm = self.aligner.align_and_normalize(raw)
        # auth service skew is -5 seconds, 05:00:00Z -> 04:59:55Z UTC
        self.assertEqual(norm.timestamp, datetime(2026, 7, 18, 4, 59, 55, tzinfo=timezone.utc))

    def test_unknown_service_validation(self):
        raw = RawEvent("e1", "2026-07-18T05:00:00Z", EventSource.ALERT, EventType.ALERT_TRIGGERED, "unregistered_svc", {"alert_name": "HighLatency"})
        with self.assertRaises(ValidationError):
            self.aligner.align_and_normalize(raw)

    def test_duplicate_event_ids(self):
        content = (
            '{"event_id": "e1", "timestamp": "2026-07-18T05:00:00Z", "source": "ALERT", '
            '"event_type": "ALERT_TRIGGERED", "service": "gateway", "metadata": {"alert_name": "HighLatency"}}\n'
            '{"event_id": "e1", "timestamp": "2026-07-18T05:01:00Z", "source": "ALERT", '
            '"event_type": "ALERT_TRIGGERED", "service": "gateway", "metadata": {"alert_name": "HighLatency"}}\n'
        )
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)

        try:
            with self.assertRaises(ValidationError):
                self.parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_invalid_timestamp_formats(self):
        with self.assertRaises(ValidationError):
            self.aligner.parse_timestamp("2026/07/18 05:00:00")


class TestIncidentTimelineReconstruction(unittest.TestCase):
    def test_chronological_sorting(self):
        dt1 = datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 7, 18, 5, 5, 0, tzinfo=timezone.utc)
        e1 = NormalizedEvent("e1", dt2, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})
        e2 = NormalizedEvent("e2", dt1, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})

        engine = TimelineEngine([e1, e2])
        self.assertEqual(engine.timeline[0].event_id, "e2")
        self.assertEqual(engine.timeline[1].event_id, "e1")

    def test_sorting_tie_breakers(self):
        dt = datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc)
        # Event e1 (source ALERT -> prio 1) vs e2 (source TELEMETRY -> prio 4)
        e1 = NormalizedEvent("e1", dt, EventSource.TELEMETRY, EventType.ERROR_RATE_SPIKE, "gateway")
        e2 = NormalizedEvent("e2", dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})

        engine = TimelineEngine([e1, e2])
        self.assertEqual(engine.timeline[0].event_id, "e2")
        self.assertEqual(engine.timeline[1].event_id, "e1")

    def test_event_id_tie_breaker(self):
        dt = datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc)
        # Same timestamp, source, and event type. Sorted alphabetically by event ID.
        e1 = NormalizedEvent("e_b", dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})
        e2 = NormalizedEvent("e_a", dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})

        engine = TimelineEngine([e1, e2])
        self.assertEqual(engine.timeline[0].event_id, "e_a")
        self.assertEqual(engine.timeline[1].event_id, "e_b")

    def test_grouping_by_incident_key(self):
        dt = datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc)
        e1 = NormalizedEvent("e1", dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})
        e2 = NormalizedEvent("e2", dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "auth", {"alert_name": "AuthFailure"})
        e3 = NormalizedEvent("e3", dt, EventSource.TELEMETRY, EventType.ERROR_RATE_SPIKE, "gateway")  # No alert_name

        engine = TimelineEngine([e1, e2, e3])
        groups = engine.group_by_incident()

        key1 = IncidentKey("gateway", "HighLatency")
        key2 = IncidentKey("auth", "AuthFailure")

        self.assertIn(key1, groups)
        self.assertIn(key2, groups)
        self.assertEqual(len(groups[key1]), 1)
        self.assertEqual(groups[key1][0].event_id, "e1")
        self.assertEqual(len(groups), 2)  # Event e3 does not have alert_name and is excluded from grouping keys


class TestIncidentStateMachine(unittest.TestCase):
    def setUp(self):
        self.machine = IncidentStateMachine()
        self.dt = datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc)

    def test_complete_valid_lifecycle(self):
        events = [
            NormalizedEvent("e1", self.dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e2", self.dt, EventSource.ACTION, EventType.INCIDENT_ACKNOWLEDGED, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e3", self.dt, EventSource.DEPLOY, EventType.DEPLOY_STARTED, "gateway", {"alert_name": "HighLatency", "version": "v1.0"}),
            NormalizedEvent("e4", self.dt, EventSource.TELEMETRY, EventType.HEALTHY, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e5", self.dt, EventSource.ALERT, EventType.ALERT_RESOLVED, "gateway", {"alert_name": "HighLatency"})
        ]
        results = self.machine.validate_timeline(tuple(events))
        # Ensure all steps validated successfully
        for res in results:
            self.assertTrue(res.is_valid, f"Failed on transition {res.from_state} -> {res.to_state}: {res.reason}")

    def test_illegal_transition_skip_ack(self):
        events = [
            NormalizedEvent("e1", self.dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e2", self.dt, EventSource.DEPLOY, EventType.DEPLOY_STARTED, "gateway", {"alert_name": "HighLatency", "version": "v1.0"})  # Skips Acknowledged
        ]
        results = self.machine.validate_timeline(tuple(events))
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].is_valid)
        self.assertFalse(results[1].is_valid)
        self.assertEqual(results[1].to_state, IncidentState.MITIGATION_RUNNING)

    def test_parallel_incidents_do_not_interfere(self):
        events = [
            # Incident A starts
            NormalizedEvent("e1", self.dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"}),
            # Incident B starts
            NormalizedEvent("e2", self.dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "auth", {"alert_name": "AuthFailure"}),
            # Incident A gets acknowledged
            NormalizedEvent("e3", self.dt, EventSource.ACTION, EventType.INCIDENT_ACKNOWLEDGED, "gateway", {"alert_name": "HighLatency"}),
            # Incident B skips Acknowledged and deploys (invalid transition)
            NormalizedEvent("e4", self.dt, EventSource.DEPLOY, EventType.DEPLOY_STARTED, "auth", {"alert_name": "AuthFailure", "version": "v1.0"})
        ]
        results = self.machine.validate_timeline(tuple(events))
        # Verify e3 (Ack for Incident A) is valid
        self.assertTrue(results[2].is_valid)
        # Verify e4 (Deploy for Incident B) is invalid
        self.assertFalse(results[3].is_valid)


class TestIncidentSLACalculations(unittest.TestCase):
    def setUp(self):
        self.rules = EngineRules(
            max_ack_sec=900,
            max_mitigate_sec=3600,
            causality_window_sec=600,
            debounce_window_sec=60
        )
        self.calculator = SLACalculator(self.rules)
        self.dt = datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc)

    def test_sla_compliance_pass(self):
        events = [
            NormalizedEvent("e1", self.dt, EventSource.TELEMETRY, EventType.ERROR_RATE_SPIKE, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e2", self.dt + timedelta(seconds=60), EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e3", self.dt + timedelta(seconds=120), EventSource.ACTION, EventType.INCIDENT_ACKNOWLEDGED, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e4", self.dt + timedelta(seconds=600), EventSource.TELEMETRY, EventType.HEALTHY, "gateway", {"alert_name": "HighLatency"})
        ]
        validations = self.calculator.evaluate_sla(tuple(events))
        self.assertEqual(len(validations), 1)
        val = validations[0]
        self.assertEqual(val.time_to_detect_seconds, 60)
        self.assertEqual(val.time_to_ack_seconds, 60)
        self.assertEqual(val.time_to_mitigate_seconds, 540)
        self.assertTrue(val.ack_compliant)
        self.assertTrue(val.mitigate_compliant)

    def test_sla_acknowledgement_compliance_fail(self):
        events = [
            NormalizedEvent("e1", self.dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e2", self.dt + timedelta(seconds=1000), EventSource.ACTION, EventType.INCIDENT_ACKNOWLEDGED, "gateway", {"alert_name": "HighLatency"})
        ]
        validations = self.calculator.evaluate_sla(tuple(events))
        val = validations[0]
        self.assertEqual(val.time_to_ack_seconds, 1000)
        self.assertFalse(val.ack_compliant)

    def test_missing_ack_incident(self):
        events = [
            NormalizedEvent("e1", self.dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})
        ]
        validations = self.calculator.evaluate_sla(tuple(events))
        val = validations[0]
        self.assertIsNone(val.time_to_ack_seconds)
        self.assertFalse(val.ack_compliant)


class TestIncidentCausalityEngine(unittest.TestCase):
    def setUp(self):
        self.rules = EngineRules(
            max_ack_sec=900,
            max_mitigate_sec=3600,
            causality_window_sec=600,
            debounce_window_sec=60
        )
        self.engine = CausalityEngine(self.rules)
        self.dt = datetime(2026, 7, 18, 5, 0, 0, tzinfo=timezone.utc)

    def test_deployment_causes_alert(self):
        events = [
            NormalizedEvent("e1", self.dt - timedelta(seconds=120), EventSource.DEPLOY, EventType.DEPLOY_STARTED, "gateway", {"alert_name": "HighLatency", "version": "v1.0"}),
            NormalizedEvent("e2", self.dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e3", self.dt + timedelta(seconds=120), EventSource.ACTION, EventType.SERVICE_RESTARTED, "gateway", {"alert_name": "HighLatency"}),
            NormalizedEvent("e4", self.dt + timedelta(seconds=240), EventSource.TELEMETRY, EventType.HEALTHY, "gateway", {"alert_name": "HighLatency"})
        ]
        results = self.engine.analyze_causality(tuple(events))
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.primary_cause, "DEPLOYMENT")
        self.assertEqual(res.confidence, "HIGH")
        self.assertIn("e1", res.supporting_events)
        self.assertIn("e3", res.supporting_events)

    def test_deployment_unrelated_outside_window(self):
        events = [
            # Deploy happens 1 hour before trigger (limit is 10 minutes)
            NormalizedEvent("e1", self.dt - timedelta(seconds=3600), EventSource.DEPLOY, EventType.DEPLOY_STARTED, "gateway", {"alert_name": "HighLatency", "version": "v1.0"}),
            NormalizedEvent("e2", self.dt, EventSource.ALERT, EventType.ALERT_TRIGGERED, "gateway", {"alert_name": "HighLatency"})
        ]
        results = self.engine.analyze_causality(tuple(events))
        res = results[0]
        self.assertEqual(res.primary_cause, "UNKNOWN")
        self.assertEqual(res.confidence, "LOW")


class TestIncidentCommandLineInterface(unittest.TestCase):
    def test_cli_execution_with_valid_files(self):
        base_dir = Path("/app") if Path("/app").exists() else Path(__file__).parent.parent
        config_dir = str(base_dir / "config")
        alerts_file = str(base_dir / "fixtures/alerts.jsonl")
        actions_file = str(base_dir / "fixtures/actions.jsonl")
        
        args = [
            "--config", config_dir,
            "--input", alerts_file, actions_file
        ]
        exit_code = cli_main(args)
        self.assertEqual(exit_code, 0)

    def test_cli_missing_config_fails(self):
        args = ["--config", "/nonexistent/path", "--input", "/nonexistent/logs.jsonl"]
        exit_code = cli_main(args)
        self.assertEqual(exit_code, 1)

if __name__ == "__main__":
    unittest.main()
