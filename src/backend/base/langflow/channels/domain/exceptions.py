class ChannelError(Exception):
    """Base error for communication-channel operations."""


class ChannelConfigurationError(ChannelError):
    """Raised when a provider connection is missing required configuration."""


class ChannelVerificationError(ChannelError):
    """Raised when an incoming provider event fails authentication."""


class DuplicateChannelEventError(ChannelError):
    """Raised when an already-processed provider event is received again."""
