from typing import Dict, List, Optional, Tuple
from src.constants import EventType
from src.models import NormalizedEvent, IncidentKey, SLAValidation
from src.config import EngineRules

class SLACalculator:
    def __init__(self, rules: EngineRules):
        self.rules = rules

    def evaluate_sla(self, timeline: Tuple[NormalizedEvent, ...]) -> Tuple[SLAValidation, ...]:
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

        validations: List[SLAValidation] = []
        for key, events in incident_events.items():
            validations.append(self._calculate_incident_sla(key, events))

        return tuple(validations)

    def _calculate_incident_sla(self, key: IncidentKey, events: List[NormalizedEvent]) -> SLAValidation:
        # Timestamps of interest
        spike_time: Optional[NormalizedEvent] = None
        trigger_time: Optional[NormalizedEvent] = None
        ack_time: Optional[NormalizedEvent] = None
        healthy_time: Optional[NormalizedEvent] = None

        for event in events:
            if event.event_type == EventType.ERROR_RATE_SPIKE and not spike_time:
                spike_time = event
            elif event.event_type == EventType.ALERT_TRIGGERED and not trigger_time:
                trigger_time = event
            elif event.event_type == EventType.INCIDENT_ACKNOWLEDGED and not ack_time:
                # First acknowledgement gets priority
                ack_time = event
            elif event.event_type == EventType.HEALTHY and not healthy_time:
                healthy_time = event

        # SLA compliance calculations
        ttd: Optional[int] = None
        tta: Optional[int] = None
        ttm: Optional[int] = None

        # Time To Detect (TTD): Trigger - Spike (Default to 0 if alert has no telemetry spike)
        if trigger_time:
            if spike_time:
                delta = int((trigger_time.timestamp - spike_time.timestamp).total_seconds())
                ttd = max(0, delta)
            else:
                ttd = 0

        # Time To Acknowledge (TTA): Ack - Trigger
        if trigger_time and ack_time:
            delta = int((ack_time.timestamp - trigger_time.timestamp).total_seconds())
            tta = max(0, delta)

        # Time To Mitigate (TTM): Healthy - Trigger
        if trigger_time and healthy_time:
            delta = int((healthy_time.timestamp - trigger_time.timestamp).total_seconds())
            ttm = max(0, delta)

        # Compliance thresholds logic
        ack_compliant = False
        if tta is not None and tta <= self.rules.max_acknowledgement_seconds:
            ack_compliant = True

        mitigate_compliant = False
        if ttm is not None and ttm <= self.rules.max_mitigation_seconds:
            mitigate_compliant = True

        return SLAValidation(
            incident_key=key,
            time_to_detect_seconds=ttd,
            time_to_ack_seconds=tta,
            time_to_mitigate_seconds=ttm,
            ack_compliant=ack_compliant,
            mitigate_compliant=mitigate_compliant
        )
