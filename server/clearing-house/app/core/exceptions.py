"""Domain exceptions.

Plain Python, no HTTP. The route layer decides which status code each one
becomes — see rest_api/routes/. Raising HTTPException here would make these
use cases unusable from a CLI, a background task or a test.
"""


class ClearingHouseError(Exception):
    """Base for everything this service raises deliberately."""


class IllegalStatusTransition(ClearingHouseError):
    """A status change the state machine forbids.

    The request was well formed; it conflicts with the contract's current
    state. The route turns this into 409 Conflict.
    """

    def __init__(self, jti: str, current: str, requested: str) -> None:
        self.jti = jti
        self.current = current
        self.requested = requested
        super().__init__(
            f"Contract {jti} is '{current}'; cannot change to '{requested}'"
        )
