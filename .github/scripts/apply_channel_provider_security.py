from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str, *, label: str) -> None:
    content = read(path)
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"Missing provider-security rollout target: {label}")
    write(path, content.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str, *, label: str) -> None:
    content = read(path)
    start_index = content.find(start)
    end_index = content.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"Missing provider-security rollout block: {label}")
    write(path, content[:start_index] + replacement + content[end_index:])


# Validate provider credentials before persistence and whenever an adapter is built.
CRUD = "src/backend/base/langflow/services/database/models/channel/crud.py"
replace_once(
    CRUD,
    "from langflow.channels.security.credentials import decrypt_channel_credentials, encrypt_channel_credentials\n",
    "from langflow.channels.security.credentials import decrypt_channel_credentials, encrypt_channel_credentials\n"
    "from langflow.channels.security.provider_credentials import validate_channel_provider_credentials\n",
    label="CRUD provider credential import",
)
replace_once(
    CRUD,
    '''async def create_channel_connection(
    session: AsyncSession,
    user_id: UUID,
    payload: ChannelConnectionCreate,
) -> ChannelConnection:
    values = payload.model_dump(exclude={"credentials", "service_user_id"})
''',
    '''async def create_channel_connection(
    session: AsyncSession,
    user_id: UUID,
    payload: ChannelConnectionCreate,
) -> ChannelConnection:
    validate_channel_provider_credentials(
        payload.channel_type,
        payload.connection_mode,
        payload.credentials,
    )
    values = payload.model_dump(exclude={"credentials", "service_user_id"})
''',
    label="connection create validation",
)
replace_between(
    CRUD,
    "async def update_channel_connection(\n",
    "async def delete_channel_connection(\n",
    '''async def update_channel_connection(
    session: AsyncSession,
    connection: ChannelConnection,
    payload: ChannelConnectionUpdate,
) -> ChannelConnection:
    existing_credentials = decrypt_channel_credentials(connection.credentials_encrypted)
    merged_credentials = dict(existing_credentials)
    if payload.credentials is not None:
        merged_credentials.update(payload.credentials)
    next_connection_mode = payload.connection_mode or connection.connection_mode
    validate_channel_provider_credentials(
        connection.channel_type,
        next_connection_mode,
        merged_credentials,
    )

    changes = payload.model_dump(exclude_unset=True, exclude={"credentials", "service_user_id"})
    for field, value in changes.items():
        setattr(connection, field, value)
    if payload.credentials is not None:
        connection.credentials_encrypted = encrypt_channel_credentials(merged_credentials)
    await ensure_channel_service_identity(session, connection)
    connection.updated_at = utc_now()
    session.add(connection)
    await session.flush()
    await session.refresh(connection)
    return connection


''',
    label="connection update validation",
)

FACTORY = "src/backend/base/langflow/channels/adapters/factory.py"
replace_once(
    FACTORY,
    "from langflow.channels.security.credentials import decrypt_channel_credentials\n",
    "from langflow.channels.security.credentials import decrypt_channel_credentials\n"
    "from langflow.channels.security.provider_credentials import validate_channel_provider_credentials\n",
    label="factory provider credential import",
)
replace_once(
    FACTORY,
    '''    credentials = decrypt_channel_credentials(connection.credentials_encrypted)
    channel = ChannelType(connection.channel_type)
''',
    '''    credentials = decrypt_channel_credentials(connection.credentials_encrypted)
    validate_channel_provider_credentials(
        connection.channel_type,
        connection.connection_mode,
        credentials,
    )
    channel = ChannelType(connection.channel_type)
''',
    label="factory runtime validation",
)

CHANNELS_API = "src/backend/base/langflow/api/v1/channels.py"
replace_once(
    CHANNELS_API,
    "from langflow.channels.adapters.telegram import TelegramChannelAdapter\n",
    "from langflow.channels.adapters.telegram import TelegramChannelAdapter\n"
    "from langflow.channels.security.provider_credentials import ChannelProviderCredentialError\n",
    label="API credential error import",
)
replace_once(
    CHANNELS_API,
    '''    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A channel connection with this name already exists",
        ) from exc
''',
    '''    except ChannelProviderCredentialError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A channel connection with this name already exists",
        ) from exc
''',
    label="connection create credential error",
)
# Apply the same error branch to the second connection mutation handler.
content = read(CHANNELS_API)
needle = '''    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A channel connection with this name already exists",
        ) from exc
'''
credential_branch = '''    except ChannelProviderCredentialError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A channel connection with this name already exists",
        ) from exc
'''
if content.count("except ChannelProviderCredentialError as exc:") < 2:
    index = content.find(needle, content.find("async def update_channel_connection_route"))
    if index < 0:
        raise RuntimeError("Missing connection update credential error marker")
    content = content[:index] + credential_branch + content[index + len(needle) :]
    write(CHANNELS_API, content)

# Telegram callback verification and UTF-16 entity offsets.
TELEGRAM = "src/backend/base/langflow/channels/adapters/telegram.py"
replace_once(
    TELEGRAM,
    '''    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        del payload
        if self.webhook_secret is None:
            return True
''',
    '''    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        del payload
        if self.webhook_secret is None:
            return False
''',
    label="Telegram fail-closed verification",
)
replace_once(
    TELEGRAM,
    '''    @staticmethod
    def _extract_mentions(message: dict[str, Any], text: str | None) -> list[str]:
''',
    '''    @staticmethod
    def _utf16_entity_text(text: str, offset: int, length: int) -> str:
        if offset < 0 or length <= 0:
            return ""
        encoded = text.encode("utf-16-le")
        start = offset * 2
        end = (offset + length) * 2
        if start >= len(encoded) or end > len(encoded):
            return ""
        try:
            return encoded[start:end].decode("utf-16-le")
        except UnicodeDecodeError:
            return ""

    @staticmethod
    def _extract_mentions(message: dict[str, Any], text: str | None) -> list[str]:
''',
    label="Telegram UTF-16 helper",
)
replace_once(
    TELEGRAM,
    "                mentions.append(text[offset : offset + length])\n",
    '''                mention = TelegramChannelAdapter._utf16_entity_text(text, offset, length)
                if mention:
                    mentions.append(mention.lstrip("@"))
''',
    label="Telegram UTF-16 mention extraction",
)
replace_once(
    TELEGRAM,
    '''        if self.webhook_secret:
            payload["secret_token"] = self.webhook_secret
        return bool(await self._request("setWebhook", payload=payload))
''',
    '''        if not self.webhook_secret:
            raise ValueError("Telegram webhook_secret is required before configuring a webhook")
        payload["secret_token"] = self.webhook_secret
        return bool(await self._request("setWebhook", payload=payload))
''',
    label="Telegram webhook secret requirement",
)

# Feishu unencrypted callbacks must always prove the configured verification token.
FEISHU = "src/backend/base/langflow/channels/adapters/feishu.py"
replace_once(
    FEISHU,
    '''        if body.get("encrypt"):
            return False
        if self.verification_token is None:
            return True
''',
    '''        if body.get("encrypt"):
            return False
        if self.verification_token is None:
            return False
''',
    label="Feishu fail-closed verification",
)

# Tighten signed callback time windows.
DINGTALK = "src/backend/base/langflow/channels/adapters/dingtalk.py"
replace_once(
    DINGTALK,
    "_DINGTALK_SIGNATURE_MAX_AGE_MS = 60 * 60 * 1000\n",
    "_DINGTALK_SIGNATURE_MAX_AGE_MS = 5 * 60 * 1000\n",
    label="DingTalk signature freshness",
)

WECOM = "src/backend/base/langflow/channels/adapters/wecom.py"
replace_once(
    WECOM,
    "\n\nclass WeComAPIError(RuntimeError):\n",
    "\n\n_WECOM_CALLBACK_MAX_AGE_SECONDS = 5 * 60\n\n\nclass WeComAPIError(RuntimeError):\n",
    label="WeCom freshness constant",
)
replace_once(
    WECOM,
    '''    def verify_url(
        self,
        *,
        signature: str,
        timestamp: str,
        nonce: str,
        echo: str,
    ) -> str:
        encrypted = unquote(echo)
''',
    '''    @staticmethod
    def _callback_timestamp_is_fresh(timestamp: str) -> bool:
        try:
            callback_time = int(timestamp)
        except (TypeError, ValueError):
            return False
        return abs(int(time.time()) - callback_time) <= _WECOM_CALLBACK_MAX_AGE_SECONDS

    def verify_url(
        self,
        *,
        signature: str,
        timestamp: str,
        nonce: str,
        echo: str,
    ) -> str:
        if not self._callback_timestamp_is_fresh(timestamp):
            raise PermissionError("Expired WeCom callback timestamp")
        encrypted = unquote(echo)
''',
    label="WeCom URL freshness",
)
replace_once(
    WECOM,
    '''        nonce = headers.get("x-wecom-nonce", "")
        return bool(
            encrypted
''',
    '''        nonce = headers.get("x-wecom-nonce", "")
        if not self._callback_timestamp_is_fresh(timestamp):
            return False
        return bool(
            encrypted
''',
    label="WeCom event freshness",
)

# Frontend requires security credentials during creation and validates Telegram token syntax.
FRONTEND = "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/ChannelConnectionDialog.tsx"
replace_once(
    FRONTEND,
    '''    if (!form.name.trim()) {
      setError(t("channels.errors.nameRequired"));
      return;
    }
    setError(null);
''',
    '''    if (!form.name.trim()) {
      setError(t("channels.errors.nameRequired"));
      return;
    }
    if (!isEditing && form.channelType === "telegram") {
      if (!/^[A-Za-z0-9_-]{16,256}$/.test(form.webhookSecret.trim())) {
        setError(
          copy(
            "Telegram Webhook 密钥必须为 16-256 位，只能包含字母、数字、下划线和短横线。",
          ),
        );
        return;
      }
    }
    if (!isEditing && form.channelType === "feishu" && !form.verificationToken.trim()) {
      setError(copy("飞书 Verification Token 为必填安全配置。"));
      return;
    }
    setError(null);
''',
    label="frontend provider credential validation",
)
replace_once(
    FRONTEND,
    '''                <Input
                  type="password"
                  value={form.webhookSecret}
''',
    '''                <Input
                  type="password"
                  required={!isEditing}
                  minLength={16}
                  maxLength={256}
                  pattern="[A-Za-z0-9_-]+"
                  value={form.webhookSecret}
''',
    label="Telegram secure secret input",
)
replace_once(
    FRONTEND,
    '''                <Input
                  type="password"
                  value={form.verificationToken}
''',
    '''                <Input
                  type="password"
                  required={!isEditing}
                  value={form.verificationToken}
''',
    label="Feishu required verification token",
)

# Existing WeCom adapter tests use old fixed timestamps; keep the callback valid
# while retaining deterministic signatures.
WECOM_TEST = "src/backend/tests/unit/channels/test_wecom.py"
replace_once(
    WECOM_TEST,
    "import hashlib\n",
    "import hashlib\nimport time\n",
    label="WeCom test time import",
)
replace_once(
    WECOM_TEST,
    '    timestamp = "1700000000"\n',
    "    timestamp = str(int(time.time()))\n",
    label="WeCom current callback timestamp",
)
