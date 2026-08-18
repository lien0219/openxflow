"""Channel services package.

Services are loaded lazily so importing database models during API startup does
not pull runtime services back into partially initialized model modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langflow.channels.services.deduplication import ChannelEventDeduplicator
    from langflow.channels.services.gateway import ChannelGateway, ChannelHandler


def __getattr__(name: str) -> object:
    if name == "ChannelEventDeduplicator":
        from langflow.channels.services.deduplication import ChannelEventDeduplicator

        return ChannelEventDeduplicator
    if name in {"ChannelGateway", "ChannelHandler"}:
        from langflow.channels.services.gateway import ChannelGateway, ChannelHandler

        return {"ChannelGateway": ChannelGateway, "ChannelHandler": ChannelHandler}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ChannelEventDeduplicator", "ChannelGateway", "ChannelHandler"]
