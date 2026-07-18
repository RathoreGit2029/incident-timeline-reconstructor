import json
from typing import Dict, List, Tuple, Any
from src.models import NormalizedEvent, SLAValidation
from src.state import TransitionResult
from src.rules.causality import CausalityResult

class IncidentReporter:
    @staticmethod
    def generate_report_dict(
        timeline: Tuple[NormalizedEvent, ...],
        transitions: Tuple[TransitionResult, ...],
        sla_results: Tuple[SLAValidation, ...],
        causality_results: Tuple[CausalityResult, ...]
    ) -> Dict[str, Any]:
        # Pre-index SLA and Causality results by IncidentKey for fast, stateless mapping lookup
        sla_map = {res.incident_key: res for res in sla_results}
        causality_map = {res.incident_key: res for res in causality_results}

        # Index state violations and final state from transition logs
        state_violations: Dict[str, List[str]] = {}
        final_states: Dict[str, str] = {}
        for trans in transitions:
            key_str = str(trans.incident_key)
            if not trans.is_valid:
                if key_str not in state_violations:
                    state_violations[key_str] = []
                state_violations[key_str].append(trans.reason or "State validation transition failure")
            final_states[key_str] = trans.to_state.value

        # Group events by incident key to determine timeline summary bounds
        incident_events: Dict[str, List[NormalizedEvent]] = {}
        for event in timeline:
            alert_name = event.metadata.get("alert_name")
            if not alert_name:
                continue
            key_str = f"{event.service}:{alert_name}"
            if key_str not in incident_events:
                incident_events[key_str] = []
            incident_events[key_str].append(event)

        incidents_report = {}
        for key_str, events in incident_events.items():
            service, alert_name = key_str.split(":", 1)
            
            # Find SLA and Causality entries
            target_key = next((k for k in sla_map if str(k) == key_str), None)
            sla_val = sla_map.get(target_key) if target_key else None
            causality_val = causality_map.get(target_key) if target_key else None

            incidents_report[key_str] = {
                "incident_identifier": key_str,
                "service": service,
                "alert_name": alert_name,
                "event_count": len(events),
                "final_state": final_states.get(key_str, "Unknown"),
                "has_state_violations": len(state_violations.get(key_str, [])) > 0,
                "state_violations": state_violations.get(key_str, []),
                "sla": {
                    "time_to_detect_seconds": sla_val.time_to_detect_seconds if sla_val else None,
                    "time_to_acknowledge_seconds": sla_val.time_to_ack_seconds if sla_val else None,
                    "time_to_mitigate_seconds": sla_val.time_to_mitigate_seconds if sla_val else None,
                    "ack_compliant": sla_val.ack_compliant if sla_val else False,
                    "mitigate_compliant": sla_val.mitigate_compliant if sla_val else False
                },
                "causality": {
                    "primary_cause": causality_val.primary_cause if causality_val else "UNKNOWN",
                    "confidence": causality_val.confidence if causality_val else "UNKNOWN",
                    "reason": causality_val.reason if causality_val else "No causality data.",
                    "supporting_events": list(causality_val.supporting_events) if causality_val else []
                }
            }

        # Format timeline listing details
        timeline_list = []
        for event in timeline:
            timeline_list.append({
                "event_id": event.event_id,
                "adjusted_timestamp": event.timestamp.isoformat() + "Z",
                "source": event.source.value,
                "event_type": event.event_type.value,
                "service": event.service
            })

        return {
            "summary": {
                "total_events": len(timeline),
                "total_incidents": len(incidents_report),
                "has_any_violations": any(inc["has_state_violations"] for inc in incidents_report.values())
            },
            "incidents": incidents_report,
            "timeline": timeline_list
        }

    @classmethod
    def generate_human_readable(cls, report_dict: Dict[str, Any]) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("INCIDENT TIMELINE RECONSTRUCTION REPORT")
        lines.append("=" * 60)
        lines.append(f"Total Log Events Processed: {report_dict['summary']['total_events']}")
        lines.append(f"Total Incidents Identified: {report_dict['summary']['total_incidents']}")
        lines.append("-" * 60)

        for key, inc in report_dict["incidents"].items():
            lines.append(f"Incident: {inc['incident_identifier']}")
            lines.append(f"  Service: {inc['service']}")
            lines.append(f"  Alert Name: {inc['alert_name']}")
            lines.append(f"  Final State: {inc['final_state']}")
            lines.append(f"  State Violations: {', '.join(inc['state_violations']) if inc['state_violations'] else 'None'}")
            lines.append("  SLA Metrics:")
            lines.append(f"    TTD: {inc['sla']['time_to_detect_seconds']}s")
            lines.append(f"    TTA: {inc['sla']['time_to_acknowledge_seconds']}s (Compliant: {inc['sla']['ack_compliant']})")
            lines.append(f"    TTM: {inc['sla']['time_to_mitigate_seconds']}s (Compliant: {inc['sla']['mitigate_compliant']})")
            lines.append("  Causality:")
            lines.append(f"    Primary Cause: {inc['causality']['primary_cause']} ({inc['causality']['confidence']} Confidence)")
            lines.append(f"    Reason: {inc['causality']['reason']}")
            lines.append("-" * 60)

        return "\n".join(lines)
