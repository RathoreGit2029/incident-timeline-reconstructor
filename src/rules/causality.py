from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from src.constants import EventSource, EventType
from src.models import NormalizedEvent, IncidentKey, CausalityLink
from src.config import EngineRules

@dataclass(frozen=True)
class CausalityResult:
    incident_key: IncidentKey
    primary_cause: str  # e.g., "DEPLOYMENT", "ACTION", "UNKNOWN"
    confidence: str  # HIGH, MEDIUM, LOW, UNKNOWN
    reason: str
    correlation_window_used: int
    supporting_events: Tuple[str, ...] = field(default_factory=tuple)

class IncidentEventIndex:
    """Builds a single indexed lookup view of categorized events for an IncidentKey."""
    def __init__(self, events: List[NormalizedEvent]):
        self.trigger_event: Optional[NormalizedEvent] = None
        self.healthy_event: Optional[NormalizedEvent] = None
        self.deploy_events: List[NormalizedEvent] = []
        self.action_events: List[NormalizedEvent] = []

        for event in events:
            if event.event_type == EventType.ALERT_TRIGGERED and not self.trigger_event:
                self.trigger_event = event
            elif event.event_type == EventType.HEALTHY and not self.healthy_event:
                self.healthy_event = event
            elif event.source == EventSource.DEPLOY:
                self.deploy_events.append(event)
            elif event.source == EventSource.ACTION:
                self.action_events.append(event)

class CausalityEngine:
    def __init__(self, rules: EngineRules):
        self.rules = rules

    def analyze_causality(self, timeline: Tuple[NormalizedEvent, ...]) -> Tuple[CausalityResult, ...]:
        # Group events relevant to each incident key to isolate evaluations
        incident_events: Dict[IncidentKey, List[NormalizedEvent]] = {}
        for event in timeline:
            alert_name = event.metadata.get("alert_name")
            if not alert_name:
                continue
            key = IncidentKey(service=event.service, alert_name=alert_name)
            if key not in incident_events:
                incident_events[key] = []
            incident_events[key].append(event)

        results: List[CausalityResult] = []
        for key, events in incident_events.items():
            # Build single indexed view of events to prevent multiple timeline scans
            index = IncidentEventIndex(events)
            results.append(self._analyze_incident_causality(key, index))

        return tuple(results)

    def _analyze_incident_causality(self, key: IncidentKey, index: IncidentEventIndex) -> CausalityResult:
        trigger_event = index.trigger_event
        healthy_event = index.healthy_event

        if not trigger_event:
            return CausalityResult(
                incident_key=key,
                primary_cause="UNKNOWN",
                confidence="UNKNOWN",
                reason="No trigger alert event found in logs.",
                correlation_window_used=self.rules.causality_window_seconds
            )

        # Precedence Rule 1: Look for deployment events occurring BEFORE the trigger within causality window
        culprit_deploy: Optional[NormalizedEvent] = None
        for event in index.deploy_events:
            if event.timestamp < trigger_event.timestamp:
                delta = int((trigger_event.timestamp - event.timestamp).total_seconds())
                if delta <= self.rules.causality_window_seconds:
                    culprit_deploy = event
                    break  # Take earliest matching deploy in window

        # Precedence Rule 2: Check for manual interventions (restarts, rollbacks) leading to recovery
        mitigation_action: Optional[NormalizedEvent] = None
        if healthy_event:
            for event in index.action_events:
                if trigger_event.timestamp <= event.timestamp < healthy_event.timestamp:
                    delta = int((healthy_event.timestamp - event.timestamp).total_seconds())
                    if delta <= self.rules.causality_window_seconds:
                        mitigation_action = event
                        break  # Take first mitigation action leading to health

        # Synthesize results based on deterministic confidence
        if culprit_deploy and mitigation_action:
            return CausalityResult(
                incident_key=key,
                primary_cause="DEPLOYMENT",
                supporting_events=(culprit_deploy.event_id, mitigation_action.event_id),
                confidence="HIGH",
                reason=f"Incident likely triggered by deployment {culprit_deploy.event_id} and mitigated by action {mitigation_action.event_id}.",
                correlation_window_used=self.rules.causality_window_seconds
            )
        elif culprit_deploy:
            return CausalityResult(
                incident_key=key,
                primary_cause="DEPLOYMENT",
                supporting_events=(culprit_deploy.event_id,),
                confidence="MEDIUM",
                reason=f"Incident likely triggered by deployment {culprit_deploy.event_id}. No clear mitigation action identified.",
                correlation_window_used=self.rules.causality_window_seconds
            )
        elif mitigation_action:
            return CausalityResult(
                incident_key=key,
                primary_cause="ACTION",
                supporting_events=(mitigation_action.event_id,),
                confidence="MEDIUM",
                reason=f"Mitigated by action {mitigation_action.event_id}.",
                correlation_window_used=self.rules.causality_window_seconds
            )

        return CausalityResult(
            incident_key=key,
            primary_cause="UNKNOWN",
            confidence="LOW",
            reason="No clear deployment trigger or mitigation action identified within correlation windows.",
            correlation_window_used=self.rules.causality_window_seconds
        )
