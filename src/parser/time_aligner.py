import re
from datetime import datetime, timezone, timedelta
from typing import Dict
from src.exceptions import ValidationError
from src.constants import EventSource, EventType
from src.models import RawEvent, NormalizedEvent, ServiceNode

# Regex patterns for validation
ISO_PATTERN = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:(Z)|([+-])(\d{2}):(\d{2}))?$"
)
EPOCH_PATTERN = re.compile(r"^\d+$")

class TimeAligner:
    def __init__(self, services: Dict[str, ServiceNode]):
        self._services = services

    def align_and_normalize(self, raw_event: RawEvent) -> NormalizedEvent:
        # Validate that service is registered
        if raw_event.service not in self._services:
            raise ValidationError(f"Event references unregistered service: '{raw_event.service}'")

        # Parse timestamp to UTC datetime
        dt = self.parse_timestamp(raw_event.timestamp)

        # Apply skew correction (aligned = raw + skew)
        node = self._services[raw_event.service]
        aligned_dt = dt + timedelta(seconds=node.clock_skew_seconds)

        return NormalizedEvent(
            event_id=raw_event.event_id,
            timestamp=aligned_dt,
            source=raw_event.source,
            event_type=raw_event.event_type,
            service=raw_event.service,
            metadata=raw_event.metadata
        )

    @staticmethod
    def parse_timestamp(ts: str) -> datetime:
        # Check for Unix Epoch (seconds)
        if EPOCH_PATTERN.match(ts):
            try:
                return datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except (ValueError, OverflowError) as e:
                raise ValidationError(f"Epoch timestamp out of range: {ts} ({e})")

        # Check for ISO8601 variations
        match = ISO_PATTERN.match(ts)
        if not match:
            raise ValidationError(f"Unsupported timestamp format: '{ts}'")

        year, month, day, hour, minute, second, fraction, z_marker, offset_sign, offset_h, offset_m = match.groups()

        # Parse basic components
        try:
            val_year = int(year)
            val_month = int(month)
            val_day = int(day)
            val_hour = int(hour)
            val_minute = int(minute)
            val_second = int(second)
            
            # Resolve microseconds if present
            microsecond = 0
            if fraction:
                # Truncate or pad to exactly 6 digits (microseconds)
                fraction = fraction[:6].ljust(6, "0")
                microsecond = int(fraction)

            dt = datetime(val_year, val_month, val_day, val_hour, val_minute, val_second, microsecond, tzinfo=timezone.utc)
        except ValueError as e:
            raise ValidationError(f"Invalid calendar date parameters in: '{ts}' ({e})")

        # Handle timezone offsets
        if z_marker == "Z" or (not z_marker and not offset_sign):
            # Already in UTC
            return dt
        else:
            # Shift offset to UTC
            hours = int(offset_h)
            minutes = int(offset_m)
            td = timedelta(hours=hours)
            if offset_sign == "-":
                # If negative offset, add it to find UTC
                dt = dt + td
            else:
                # If positive offset, subtract it to find UTC
                dt = dt - td
            return dt
