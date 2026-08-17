# Domain exceptions (EntityNotFound, BusinessRuleViolation, etc.)


class ConfigurationError(Exception):
    """
    Raised when a required environment/settings value is missing or invalid
    at the point of use (e.g. DARWINBOX_DEFAULT_PASSWORD unset with no explicit
    password supplied, or DARWINBOX_DEFAULT_ROLE_CODE not resolving to an
    active role). Controllers map this to a 500-level response.
    """
