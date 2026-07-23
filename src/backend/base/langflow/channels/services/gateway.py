from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from uuid import UUID

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelType
