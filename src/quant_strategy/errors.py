"""Public exceptions raised by configuration, data and adapter contracts."""


class ConfigurationError(ValueError):
    """A setting is unknown, inconsistent or outside its supported range."""


class DataContractError(ValueError):
    """Input data violates the time, index or feature contract."""


class UnsupportedCapabilityError(NotImplementedError):
    """A backend cannot perform the requested operation."""
