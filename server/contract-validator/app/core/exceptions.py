"""Domain exceptions for the Validator."""


class ContractValidatorError(Exception):
    """Base class for Validator errors."""


class JWKSError(ContractValidatorError):
    """JWKS endpoint of the issuing node is unreachable or malformed."""


class ClearingHouseError(ContractValidatorError):
    """Clearing House is unreachable when looking up jti status."""
