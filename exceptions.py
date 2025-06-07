class SmartcarError(Exception):
    """Base exception for Smartcar operations."""

    pass


class TokenError(SmartcarError):
    """Exception raised for token-related errors."""

    pass


class VehicleError(SmartcarError):
    """Exception raised for vehicle-related errors."""

    pass


class ChargingError(SmartcarError):
    """Exception raised for charging-related errors."""

    pass
