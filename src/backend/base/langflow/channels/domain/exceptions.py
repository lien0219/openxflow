class ChannelError(Exception):
    """Base error for communication-channel operations."""


class ChannelConfigurationError(ChannelError):
    """Raised when a provider connection is missing required configuration."""


class ChannelVerificationError(ChannelError):
    """Raised when an incoming provider event fails authentication."""


class DuplicateChannelEventError(ChannelError):
    """Raised when an already-processed provider event is received again."""


class ChannelBindingError(ChannelError):
    """Base error for channel-account binding operations."""


class ChannelBindingCodeInvalidError(ChannelBindingError):
    """Raised when a binding code is malformed, unknown, or already consumed."""


class ChannelBindingCodeExpiredError(ChannelBindingError):
    """Raised when a binding code is valid but no longer active."""


class ChannelIdentityConflictError(ChannelBindingError):
    """Raised when an external account is already bound to a different user."""
