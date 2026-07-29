"""Canonical authorization action vocabulary."""

from __future__ import annotations

from enum import Enum


class FlowAction(str, Enum):
    """Actions authorized on a flow resource."""

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"
    EXECUTE = "execute"
    DEPLOY = "deploy"


class DeploymentAction(str, Enum):
    """Actions authorized on a deployment resource."""

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"
    EXECUTE = "execute"


class ProjectAction(str, Enum):
    """Actions authorized on a project (folder) resource."""

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"


class KnowledgeBaseAction(str, Enum):
    """Actions authorized on a knowledge base resource."""

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"
    INGEST = "ingest"


class VariableAction(str, Enum):
    """Actions authorized on a variable resource."""

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"


class FileAction(str, Enum):
    """Actions authorized on a user-file resource (v2 files)."""

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"


class ShareAction(str, Enum):
    """Actions authorized on an authz_share row."""

    READ = "read"
    CREATE = "create"
    DELETE = "delete"
    UPDATE = "update"


class ChannelAction(str, Enum):
    """Actions authorized on a channel connection and its child resources."""

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"
    EXECUTE = "execute"
    BIND = "bind"
    AUDIT = "audit"


class AuditAction(str, Enum):
    """Actions authorized on platform and resource audit streams."""

    READ = "read"
    EXPORT = "export"


class RbacAction(str, Enum):
    """Actions authorized on role definitions and scoped assignments."""

    READ = "read"
    MANAGE = "manage"
    ASSIGN = "assign"


class TeamAction(str, Enum):
    """Actions authorized on teams, memberships and team role grants."""

    READ = "read"
    CREATE = "create"
    WRITE = "write"
    DELETE = "delete"
    MANAGE = "manage"


class UserAction(str, Enum):
    """Actions authorized on the user directory and account administration."""

    READ = "read"
    CREATE = "create"
    WRITE = "write"
    DELETE = "delete"
    MANAGE = "manage"
