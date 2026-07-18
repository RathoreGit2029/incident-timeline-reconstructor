import json
from pathlib import Path
from typing import List, Set
from src.exceptions import ValidationError
from src.constants import EventSource, EventType
from src.models import RawEvent
from src.parser.base import BaseParser

class JsonlParser(BaseParser):
    def parse_file(self, path: Path) -> List[RawEvent]:
        raw_events: List[RawEvent] = []
        parsed_ids: Set[str] = set()
        if not path.exists():
            raise ValidationError(f"File not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        raise ValidationError(f"Malformed JSON at line {line_idx} in {path.name}: {e}")

                    # Validate envelope structure
                    for field_name in ("event_id", "timestamp", "source", "event_type", "service"):
                        if field_name not in data:
                            raise ValidationError(f"Missing required field '{field_name}' at line {line_idx} in {path.name}")

                    event_id = data["event_id"]
                    if event_id in parsed_ids:
                        raise ValidationError(f"Duplicate event ID '{event_id}' found at line {line_idx} in {path.name}")
                    parsed_ids.add(event_id)

                    # Map sources and types to Enums
                    try:
                        source_enum = EventSource(data["source"])
                    except ValueError:
                        raise ValidationError(f"Invalid event source '{data['source']}' at line {line_idx}")

                    try:
                        type_enum = EventType(data["event_type"])
                    except ValueError:
                        raise ValidationError(f"Invalid event type '{data['event_type']}' at line {line_idx}")

                    metadata = data.get("metadata", {})

                    try:
                        raw_event = RawEvent(
                            event_id=event_id,
                            timestamp=data["timestamp"],
                            source=source_enum,
                            event_type=type_enum,
                            service=data["service"],
                            metadata=metadata
                        )
                        raw_events.append(raw_event)
                    except ValueError as e:
                        raise ValidationError(f"Event validation failed at line {line_idx}: {e}")

        except OSError as e:
            raise ValidationError(f"Error reading file {path.name}: {e}")

        return raw_events
