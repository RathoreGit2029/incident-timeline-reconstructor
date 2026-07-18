from typing import List, Dict, Tuple
from src.constants import EventSource, EventType
from src.models import NormalizedEvent, IncidentKey

# Deterministic ordering priority mappings
# Source Priority (lower numbers indicate higher sorting priority)
# Alerts are sorted first (triggers/resolutions establish bounds).
# Deployments/Actions follow (restarts/rollbacks).
# Telemetry events are evaluated last.
SOURCE_PRIORITY: Dict[EventSource, int] = {
    EventSource.ALERT: 1,
    EventSource.DEPLOY: 2,
    EventSource.ACTION: 3,
    EventSource.TELEMETRY: 4
}

# Event Type Priority (lower numbers indicate higher sorting priority)
# Serves as a tie-breaker when sources are identical.
EVENT_TYPE_PRIORITY: Dict[EventType, int] = {
    EventType.ALERT_TRIGGERED: 1,
    EventType.INCIDENT_ACKNOWLEDGED: 2,
    EventType.ERROR_RATE_SPIKE: 3,
    EventType.ROLLBACK_REQUESTED: 4,
    EventType.DEPLOY_STARTED: 5,
    EventType.DEPLOY_COMPLETED: 6,
    EventType.SERVICE_RESTARTED: 7,
    EventType.HEALTHY: 8,
    EventType.ALERT_RESOLVED: 9
}

class TimelineEngine:
    def __init__(self, events: List[NormalizedEvent]):
        self._raw_events = list(events)
        self._timeline: Tuple[NormalizedEvent, ...] = self._reconstruct_timeline()

    @property
    def timeline(self) -> Tuple[NormalizedEvent, ...]:
        """Returns the canonical, immutable reconstructed timeline."""
        return self._timeline

    def _reconstruct_timeline(self) -> Tuple[NormalizedEvent, ...]:
        # Perform deterministic multi-key sorting:
        # 1. Adjusted UTC timestamp (ascending)
        # 2. Source Priority (ascending)
        # 3. Event Type Priority (ascending)
        # 4. Event ID (alphabetical ascending)
        sorted_events = sorted(
            self._raw_events,
            key=lambda e: (
                e.timestamp,
                SOURCE_PRIORITY.get(e.source, 99),
                EVENT_TYPE_PRIORITY.get(e.event_type, 99),
                e.event_id
            )
        )
        return tuple(sorted_events)

    def group_by_incident(self) -> Dict[IncidentKey, Tuple[NormalizedEvent, ...]]:
        """
        Groups timeline events by their IncidentKey.
        Only events having alert_name in metadata are eligible for key extraction.
        Events without an IncidentKey are excluded from the mapping.
        """
        groups: Dict[IncidentKey, List[NormalizedEvent]] = {}
        for event in self._timeline:
            alert_name = event.metadata.get("alert_name")
            if alert_name:
                key = IncidentKey(service=event.service, alert_name=alert_name)
                if key not in groups:
                    groups[key] = []
                groups[key].append(event)
        
        # Convert values to immutable tuples
        return {k: tuple(v) for k, v in groups.items()}
