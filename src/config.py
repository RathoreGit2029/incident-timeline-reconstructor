import json
from pathlib import Path
from typing import Dict, List, Set, Any
from src.exceptions import ConfigError, TopologyError
from src.models import ServiceNode

class TopologyConfig:
    def __init__(self, services: Dict[str, ServiceNode]):
        self._services = dict(services)

    @property
    def services(self) -> Dict[str, ServiceNode]:
        return self._services

    @classmethod
    def load_from_dict(cls, data: Dict[str, Any]) -> "TopologyConfig":
        if "services" not in data:
            raise ConfigError("Topology configuration missing 'services' key.")
        
        services_list = data["services"]
        if not isinstance(services_list, list):
            raise ConfigError("'services' must be a list in topology configuration.")

        services: Dict[str, ServiceNode] = {}
        for idx, svc_data in enumerate(services_list):
            if not isinstance(svc_data, dict):
                raise ConfigError(f"Service entry at index {idx} is not a dictionary.")
            
            name = svc_data.get("name")
            if not name:
                raise ConfigError(f"Service entry at index {idx} is missing a name.")
            if name in services:
                raise TopologyError(f"Duplicate service name '{name}' found in topology configuration.")

            dependencies = svc_data.get("dependencies", [])
            skew = svc_data.get("clock_skew_seconds", 0)

            try:
                node = ServiceNode(name=name, dependencies=dependencies, clock_skew_seconds=skew)
                services[name] = node
            except ValueError as e:
                raise ConfigError(f"Invalid service node attributes for '{name}': {e}")

        # Validate dependency connections and cycle detection
        cls._validate_topology(services)
        return cls(services)

    @classmethod
    def load_from_file(cls, path: Path) -> "TopologyConfig":
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.load_from_dict(data)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Topology JSON file is malformed: {e}")
        except FileNotFoundError:
            raise ConfigError(f"Topology configuration file not found at {path}")

    @classmethod
    def _validate_topology(cls, services: Dict[str, ServiceNode]) -> None:
        # Check for orphan dependencies
        for name, node in services.items():
            for dep in node.dependencies:
                if dep not in services:
                    raise TopologyError(
                        f"Orphan dependency: Service '{name}' depends on '{dep}', which is not defined."
                    )

        # Detect cycles using depth-first search
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(node_name: str) -> None:
            visited.add(node_name)
            rec_stack.add(node_name)

            for neighbor in services[node_name].dependencies:
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    raise TopologyError(f"Cyclic dependency detected: cycle contains '{node_name}' -> '{neighbor}'.")

            rec_stack.remove(node_name)

        for name in services:
            if name not in visited:
                dfs(name)


class EngineRules:
    def __init__(self, max_ack_sec: int, max_mitigate_sec: int, causality_window_sec: int, debounce_window_sec: int):
        self.max_acknowledgement_seconds = max_ack_sec
        self.max_mitigation_seconds = max_mitigate_sec
        self.causality_window_seconds = causality_window_sec
        self.debounce_window_seconds = debounce_window_sec

    @classmethod
    def load_from_dict(cls, data: Dict[str, Any]) -> "EngineRules":
        sla_data = data.get("sla", {})
        corr_data = data.get("correlation", {})

        if not isinstance(sla_data, dict) or not isinstance(corr_data, dict):
            raise ConfigError("Config structures 'sla' and 'correlation' must be dictionaries.")

        max_ack = sla_data.get("max_acknowledgement_seconds")
        max_mit = sla_data.get("max_mitigation_seconds")
        causality = corr_data.get("causality_window_seconds")
        debounce = corr_data.get("debounce_window_seconds")

        for key, val in [
            ("max_acknowledgement_seconds", max_ack),
            ("max_mitigation_seconds", max_mit),
            ("causality_window_seconds", causality),
            ("debounce_window_seconds", debounce)
        ]:
            if val is None:
                raise ConfigError(f"Required rules configuration parameter '{key}' is missing.")
            if not isinstance(val, int) or val < 0:
                raise ConfigError(f"Config rules parameter '{key}' must be a non-negative integer.")

        return cls(
            max_ack_sec=max_ack,
            max_mitigate_sec=max_mit,
            causality_window_sec=causality,
            debounce_window_sec=debounce
        )

    @classmethod
    def load_from_file(cls, path: Path) -> "EngineRules":
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.load_from_dict(data)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Rules JSON file is malformed: {e}")
        except FileNotFoundError:
            raise ConfigError(f"Rules configuration file not found at {path}")
