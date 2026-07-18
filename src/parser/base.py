from abc import ABC, abstractmethod
from pathlib import Path
from typing import List
from src.models import RawEvent

class BaseParser(ABC):
    @abstractmethod
    def parse_file(self, path: Path) -> List[RawEvent]:
        """Reads a file and returns a list of raw transaction event records."""
        pass
