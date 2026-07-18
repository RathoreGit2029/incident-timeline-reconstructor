from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from src.constants import IncidentState, EventType
from src.exceptions import StateTransitionError
from src.models import NormalizedEvent, IncidentKey

@dataclass(frozen=True)
class TransitionResult:
    incident_key: IncidentKey
    from_state: IncidentState
    to_state: IncidentState
    event_type: EventType
    event_id: str
    timestamp: datetime
    is_valid: bool
    reason: Optional[str] = None

# Defines legal transitions (from_state -> set of allowed to_states)
LEGAL_TRANSITIONS: Dict[IncidentState, Tuple[IncidentState, ...]] = {
    IncidentState.NORMAL: (IncidentState.ALERT_TRIGGERED,),
    IncidentState.ALERT_TRIGGERED: (IncidentState.ACKNOWLEDGED,),
    IncidentState.ACKNOWLEDGED: (IncidentState.MITIGATION_RUNNING,),
    IncidentState.MITIGATION_RUNNING: (IncidentState.RECOVERED,),
    IncidentState.RECOVERED: (IncidentState.RESOLVED,),
    IncidentState.RESOLVED: (IncidentState.NORMAL, IncidentState.ALERT_TRIGGERED)
}

# Maps EventType to the target IncidentState it triggers
EVENT_TO_STATE_MAPPING: Dict[EventType, IncidentState] = {
    EventType.ALERT_TRIGGERED: IncidentState.ALERT_TRIGGERED,
    EventType.ERROR_RATE_SPIKE: IncidentState.ALERT_TRIGGERED,
    EventType.INCIDENT_ACKNOWLEDGED: IncidentState.ACKNOWLEDGED,
    EventType.DEPLOY_STARTED: IncidentState.MITIGATION_RUNNING,
    EventType.ROLLBACK_REQUESTED: IncidentState.MITIGATION_RUNNING,
    EventType.SERVICE_RESTARTED: IncidentState.MITIGATION_RUNNING,
    EventType.HEALTHY: IncidentState.RECOVERED,
    EventType.ALERT_RESOLVED: IncidentState.RESOLVED
}

class IncidentStateMachine:
    def __init__(self):
        # Maps IncidentKey to its current IncidentState
        self._states: Dict[IncidentKey, IncidentState] = {}

    def get_state(self, key: IncidentKey) -> IncidentState:
        return self._states.get(key, IncidentState.NORMAL)

    def validate_timeline(self, timeline: Tuple[NormalizedEvent, ...]) -> Tuple[TransitionResult, ...]:
        results: List[TransitionResult] = []
        
        # Reset tracking state for this execution pass
        self._states.clear()

        for event in timeline:
            alert_name = event.metadata.get("alert_name")
            if not alert_name:
                # Standalone event, skip state tracking
                continue

            key = IncidentKey(service=event.service, alert_name=alert_name)
            current_state = self.get_state(key)

            # Map the event type to its logical target state
            target_state = EVENT_TO_STATE_MAPPING.get(event.event_type)
            if not target_state:
                continue

            # If target state matches current state, skip duplicate transition logs
            if target_state == current_state:
                continue

            # Special transition back to normal: Alert resolution returns state to normal
            if target_state == IncidentState.RESOLVED:
                # Transitioning to resolved is valid if we're currently recovered
                is_valid = current_state in LEGAL_TRANSITIONS and IncidentState.RESOLVED in LEGAL_TRANSITIONS[current_state]
                resolved_transition = TransitionResult(
                    incident_key=key,
                    from_state=current_state,
                    to_state=IncidentState.RESOLVED,
                    event_type=event.event_type,
                    event_id=event.event_id,
                    timestamp=event.timestamp,
                    is_valid=is_valid,
                    reason=None if is_valid else f"Illegal transition from {current_state} to RESOLVED"
                )
                results.append(resolved_transition)
                if is_valid:
                    self._states[key] = IncidentState.RESOLVED
                    
                    # Resolved state automatically completes cycles by transitioning back to normal
                    normal_transition = TransitionResult(
                        incident_key=key,
                        from_state=IncidentState.RESOLVED,
                        to_state=IncidentState.NORMAL,
                        event_type=event.event_type,
                        event_id=event.event_id,
                        timestamp=event.timestamp,
                        is_valid=True,
                        reason="Automatic cleanup cycle to NORMAL"
                    )
                    results.append(normal_transition)
                    self._states[key] = IncidentState.NORMAL
                continue

            # General state transition checks
            allowed_transitions = LEGAL_TRANSITIONS.get(current_state, ())
            is_valid = target_state in allowed_transitions
            
            result = TransitionResult(
                incident_key=key,
                from_state=current_state,
                to_state=target_state,
                event_type=event.event_type,
                event_id=event.event_id,
                timestamp=event.timestamp,
                is_valid=is_valid,
                reason=None if is_valid else f"Illegal transition from {current_state} to {target_state}"
            )
            results.append(result)

            if is_valid:
                self._states[key] = target_state

        return tuple(results)
