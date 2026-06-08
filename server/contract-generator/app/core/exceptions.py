"""Domain exceptions raised by use-cases. The REST layer maps them to HTTP errors."""


class ContractGeneratorError(Exception):
    """Base class for all Generator errors."""


class TooManyItemsError(ContractGeneratorError):
    """Request bundles more items than the Generator allows in one contract."""


class SigningError(ContractGeneratorError):
    """Failed to obtain or use the signing key."""


class ClearingHouseError(ContractGeneratorError):
    """Clearing House refused or was unreachable when registering the contract."""


class SelfVerificationError(ContractGeneratorError):
    """The freshly minted token failed primary verification."""
