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


class WrongNodeError(ContractGeneratorError):
    """A catalog item's host does not belong to this node."""


class MissingFieldError(ContractGeneratorError):
    """A field required by the catalog-field schema is missing from the request."""
