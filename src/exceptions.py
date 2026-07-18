class ReconstructorError(Exception):
    """Base exception class for the Incident Timeline Reconstructor package."""
    pass

class ConfigError(ReconstructorError):
    """Raised when there is an issue loading or validating project configuration files."""
    pass

class TopologyError(ConfigError):
    """Raised when service node mappings are invalid, containing loops or orphan dependencies."""
    pass

class ValidationError(ReconstructorError):
    """Raised when an ingested raw event violates structure or validation constraints."""
    pass

class StateTransitionError(ReconstructorError):
    """Raised when the state engine detects an invalid transition pathway in the timeline."""
    pass
