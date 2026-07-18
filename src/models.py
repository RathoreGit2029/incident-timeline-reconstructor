from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from src.constants import EventSource, EventType

@dataclass(frozen=True)
class IncidentKey:
    service: str
    alert_name: str

    def __post_init__(self):
        if not self.service or not isinstance(self.service, str):
            raise ValueError("IncidentKey: service must be a non-empty string.")
        if not self.alert_name or not isinstance(self.alert_name, str):
            raise ValueError("IncidentKey: alert_name must be a non-empty string.")

    def __str__(self) -> str:
        return f"{self.service}:{self.alert_name}"

@dataclass(frozen=True)
class ServiceNode:
    name: str
    dependencies: Tuple[str, ...] = field(default_factory=tuple)
    clock_skew_seconds: int = 0

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("ServiceNode: name must be a non-empty string.")
        if not isinstance(self.dependencies, (list, tuple)) or not all(isinstance(d, str) for d in self.dependencies):
            raise ValueError("ServiceNode: dependencies must be a collection of strings.")
        if not isinstance(self.clock_skew_seconds, int):
            raise ValueError("ServiceNode: clock_skew_seconds must be an integer.")
        
        # Enforce complete frozen immutability by casting to tuple
        object.__setattr__(self, "dependencies", tuple(self.dependencies))

@dataclass(frozen=True)
class RawEvent:
    event_id: str
    timestamp: str
    source: EventSource
    event_type: EventType
    service: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.event_id or not isinstance(self.event_id, str):
            raise ValueError("RawEvent: event_id must be a non-empty string.")
        if not self.timestamp or not isinstance(self.timestamp, str):
            raise ValueError("RawEvent: timestamp must be a non-empty string.")
        if not isinstance(self.source, EventSource):
            raise ValueError("RawEvent: source must be an EventSource Enum.")
        if not isinstance(self.event_type, EventType):
            raise ValueError("RawEvent: event_type must be an EventType Enum.")
        if not self.service or not isinstance(self.service, str):
            raise ValueError("RawEvent: service must be a non-empty string.")
        if not isinstance(self.metadata, dict):
            raise ValueError("RawEvent: metadata must be a dictionary.")
        
        # Enforce required metadata fields depending on event type
        self._validate_metadata()

    def _validate_metadata(self):
        if self.event_type in (EventType.ALERT_TRIGGERED, EventType.ALERT_RESOLVED):
            if "alert_name" not in self.metadata:
                raise ValueError(f"RawEvent: metadata must contain 'alert_name' for {self.event_type}.")
        elif self.event_type in (EventType.DEPLOY_STARTED, EventType.DEPLOY_COMPLETED, EventType.ROLLBACK_REQUESTED):
            if "version" not in self.metadata:
                raise ValueError(f"RawEvent: metadata must contain 'version' for {self.event_type}.")

@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    timestamp: datetime
    source: EventSource
    event_type: EventType
    service: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.event_id or not isinstance(self.event_id, str):
            raise ValueError("NormalizedEvent: event_id must be a non-empty string.")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("NormalizedEvent: timestamp must be a datetime instance.")
        if not isinstance(self.source, EventSource):
            raise ValueError("NormalizedEvent: source must be an EventSource Enum.")
        if not isinstance(self.event_type, EventType):
            raise ValueError("NormalizedEvent: event_type must be an EventType Enum.")
        if not self.service or not isinstance(self.service, str):
            raise ValueError("NormalizedEvent: service must be a non-empty string.")
        if not isinstance(self.metadata, dict):
            raise ValueError("NormalizedEvent: metadata must be a dictionary.")
        
        # Enforce required metadata fields depending on event type
        self._validate_metadata()

    def _validate_metadata(self):
        if self.event_type in (EventType.ALERT_TRIGGERED, EventType.ALERT_RESOLVED):
            if "alert_name" not in self.metadata:
                raise ValueError(f"NormalizedEvent: metadata must contain 'alert_name' for {self.event_type}.")
        elif self.event_type in (EventType.DEPLOY_STARTED, EventType.DEPLOY_COMPLETED, EventType.ROLLBACK_REQUESTED):
            if "version" not in self.metadata:
                raise ValueError(f"NormalizedEvent: metadata must contain 'version' for {self.event_type}.")

@dataclass(frozen=True)
class SLAValidation:
    incident_key: IncidentKey
    time_to_detect_seconds: Optional[int] = None
    time_to_ack_seconds: Optional[int] = None
    time_to_mitigate_seconds: Optional[int] = None
    ack_compliant: bool = False
    mitigate_compliant: bool = False

@dataclass(frozen=True)
class CausalityLink:
    action_event_id: str
    target_telemetry_event_id: str
    time_difference_seconds: int
    relationship: str
