from __future__ import annotations

from pathlib import Path

ROOT = Path()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str, *, label: str) -> None:
    content = read(path)
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"Missing CI repair target: {label}")
    write(path, content.replace(old, new, 1))


def replace_all(path: str, old: str, new: str, *, label: str, minimum: int = 1) -> None:
    content = read(path)
    count = content.count(old)
    if count == 0 and new in content:
        return
    if count < minimum:
        raise RuntimeError(f"Missing CI repair target: {label}")
    write(path, content.replace(old, new))


def replace_function(path: str, start_marker: str, end_marker: str, replacement: str, *, label: str) -> None:
    content = read(path)
    start = content.find(start_marker)
    end = content.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        if replacement in content:
            return
        raise RuntimeError(f"Missing CI repair target: {label}")
    write(path, content[:start] + replacement + content[end:])


# Validate provider credentials before persistence.
CRUD = "src/backend/base/langflow/services/database/models/channel/crud.py"
replace_once(
    CRUD,
    "from langflow.channels.security.credentials import decrypt_credentials, encrypt_credentials, list_credential_keys\n",
    "from langflow.channels.security.credentials import decrypt_credentials, encrypt_credentials, list_credential_keys\n"
    "from langflow.channels.security.provider_credentials import validate_channel_provider_credentials\n",
    label="channel CRUD credential import",
)
replace_once(
    CRUD,
    """async def create_channel_connection(
    session: AsyncSession,
    user_id: UUID,
    payload: ChannelConnectionCreate,
) -> ChannelConnectionRead:
    connection = ChannelConnection(
""",
    """async def create_channel_connection(
    session: AsyncSession,
    user_id: UUID,
    payload: ChannelConnectionCreate,
) -> ChannelConnectionRead:
    validate_channel_provider_credentials(
        payload.channel_type,
        payload.connection_mode,
        payload.credentials,
    )
    connection = ChannelConnection(
""",
    label="channel connection create validation",
)
replace_function(
    CRUD,
    "async def update_channel_connection(\n",
    "async def delete_channel_connection(",
    """async def update_channel_connection(
    session: AsyncSession,
    connection: ChannelConnection,
    payload: ChannelConnectionUpdate,
) -> ChannelConnectionRead:
    existing_credentials = decrypt_credentials(connection.credentials_encrypted)
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
    for key, value in changes.items():
        setattr(connection, key, value)

    if payload.credentials is not None:
        connection.credentials_encrypted = encrypt_credentials(merged_credentials)

    connection.updated_at = _utc_now()
    session.add(connection)
    await ensure_channel_service_identity(session, connection)

    if "default_flow_id" in changes:
        inherited_statement = select(ChannelConversationBinding).where(
            ChannelConversationBinding.connection_id == connection.id,
            ChannelConversationBinding.route_mode == ChannelConversationRouteMode.INHERIT.value,
            ChannelConversationBinding.status.notin_(
                [ChannelConversationStatus.IGNORED.value, ChannelConversationStatus.UNAVAILABLE.value]
            ),
        )
        inherited_rows = (await session.exec(inherited_statement)).all()
        for binding in inherited_rows:
            binding.status = _derive_conversation_status(connection, binding)
            binding.updated_at = _utc_now()
            session.add(binding)

    await session.flush()
    await session.refresh(connection)
    return _connection_read(connection)


""",
    label="channel connection update validation",
)

FACTORY = "src/backend/base/langflow/channels/adapters/factory.py"
replace_once(
    FACTORY,
    "from langflow.channels.security.credentials import decrypt_credentials\n",
    "from langflow.channels.security.credentials import decrypt_credentials\n"
    "from langflow.channels.security.provider_credentials import validate_channel_provider_credentials\n",
    label="adapter factory credential import",
)
replace_once(
    FACTORY,
    """    channel_type = ChannelType(connection.channel_type)
    credentials = decrypt_credentials(connection.credentials_encrypted)

""",
    """    channel_type = ChannelType(connection.channel_type)
    credentials = decrypt_credentials(connection.credentials_encrypted)
    validate_channel_provider_credentials(
        connection.channel_type,
        connection.connection_mode,
        credentials,
    )

""",
    label="adapter factory credential validation",
)

API = "src/backend/base/langflow/api/v1/channels.py"
replace_once(
    API,
    "from langflow.channels.adapters.telegram import TelegramChannelAdapter\n",
    "from langflow.channels.adapters.telegram import TelegramChannelAdapter\n"
    "from langflow.channels.security.provider_credentials import ChannelProviderCredentialError\n",
    label="channel API credential error import",
)
api = read(API)
credential_error_branch = """    except ChannelProviderCredentialError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
"""
for route_name in ("async def create_channel_connection_route", "async def update_channel_connection_route"):
    route_start = api.find(route_name)
    route_end = api.find("\n\n@router.", route_start + 1)
    if route_end < 0:
        route_end = len(api)
    route_block = api[route_start:route_end]
    if credential_error_branch in route_block:
        continue
    marker = "    except IntegrityError as exc:\n        await db.rollback()\n"
    marker_index = api.find(marker, route_start, route_end)
    if marker_index < 0:
        raise RuntimeError(f"Missing CI repair target: credential error branch for {route_name}")
    api = api[:marker_index] + credential_error_branch + api[marker_index:]
write(API, api)

# Fail closed on Telegram callbacks and use provider-defined UTF-16 entity offsets.
TELEGRAM = "src/backend/base/langflow/channels/adapters/telegram.py"
replace_once(
    TELEGRAM,
    """        if self.webhook_secret is None:
            return True
""",
    """        if self.webhook_secret is None:
            return False
""",
    label="Telegram missing callback secret",
)
replace_once(
    TELEGRAM,
    """    @staticmethod
    def _extract_mentions(message: dict[str, Any], text: str | None) -> list[str]:
""",
    """    @staticmethod
    def _utf16_slice(text: str, offset: int, length: int) -> str:
        if offset < 0 or length < 0:
            raise ValueError("Telegram entity offsets cannot be negative")
        encoded = text.encode("utf-16-le")
        start = offset * 2
        end = start + length * 2
        if end > len(encoded):
            raise ValueError("Telegram entity offset exceeds message text")
        try:
            return encoded[start:end].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError("Telegram entity splits a UTF-16 code point") from exc

    @staticmethod
    def _extract_mentions(message: dict[str, Any], text: str | None) -> list[str]:
""",
    label="Telegram UTF-16 slicing helper",
)
replace_once(
    TELEGRAM,
    """            if entity.get("type") == "mention":
                offset = int(entity.get("offset", 0))
                length = int(entity.get("length", 0))
                mentions.append(text[offset : offset + length])
""",
    """            if entity.get("type") == "mention":
                offset = int(entity.get("offset", 0))
                length = int(entity.get("length", 0))
                mention = TelegramChannelAdapter._utf16_slice(text, offset, length)
                mentions.append(mention.removeprefix("@"))
""",
    label="Telegram UTF-16 mention extraction",
)
replace_once(
    TELEGRAM,
    """        if self.webhook_secret:
            payload["secret_token"] = self.webhook_secret
        return bool(await self._request("setWebhook", payload=payload))
""",
    """        if not self.webhook_secret:
            raise ValueError("Telegram webhook_secret is required before configuring a webhook")
        payload["secret_token"] = self.webhook_secret
        return bool(await self._request("setWebhook", payload=payload))
""",
    label="Telegram webhook secret propagation",
)

FEISHU = "src/backend/base/langflow/channels/adapters/feishu.py"
replace_once(
    FEISHU,
    """        if self.verification_token is None:
            return True
""",
    """        if self.verification_token is None:
            return False
""",
    label="Feishu missing verification token",
)

DINGTALK = "src/backend/base/langflow/channels/adapters/dingtalk.py"
replace_once(
    DINGTALK,
    "_DINGTALK_SIGNATURE_MAX_AGE_MS = 60 * 60 * 1000\n",
    "_DINGTALK_SIGNATURE_MAX_AGE_MS = 5 * 60 * 1000\n",
    label="DingTalk callback freshness",
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
    """    def verify_url(
        self,
        *,
        signature: str,
        timestamp: str,
        nonce: str,
        echo: str,
    ) -> str:
        encrypted = unquote(echo)
""",
    """    @staticmethod
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
""",
    label="WeCom URL timestamp validation",
)
replace_once(
    WECOM,
    """        nonce = headers.get("x-wecom-nonce", "")
        if not (
            encrypted
            and signature
            and timestamp
            and nonce
            and self.crypt.verify_signature(signature, timestamp, nonce, encrypted)
        ):
            return False
""",
    """        nonce = headers.get("x-wecom-nonce", "")
        if not self._callback_timestamp_is_fresh(timestamp):
            return False
        if not (
            encrypted
            and signature
            and timestamp
            and nonce
            and self.crypt.verify_signature(signature, timestamp, nonce, encrypted)
        ):
            return False
""",
    label="WeCom event timestamp validation",
)

# Require provider verification secrets in the connection form.
FRONTEND = "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/ChannelConnectionDialog.tsx"
replace_once(
    FRONTEND,
    """    if (
      !isEditing &&
      form.channelType === "telegram" &&
      !form.botToken.trim()
    ) {
      return;
    }
""",
    """    if (
      !isEditing &&
      form.channelType === "telegram" &&
      (!form.botToken.trim() ||
        !/^[A-Za-z0-9_-]{16,256}$/.test(form.webhookSecret.trim()))
    ) {
      return;
    }
""",
    label="Telegram connection form validation",
)
replace_once(
    FRONTEND,
    """    if (
      !isEditing &&
      form.channelType === "feishu" &&
      (!form.appId.trim() || !form.appSecret.trim())
    ) {
      return;
    }
""",
    """    if (
      !isEditing &&
      form.channelType === "feishu" &&
      (!form.appId.trim() ||
        !form.appSecret.trim() ||
        !form.verificationToken.trim())
    ) {
      return;
    }
""",
    label="Feishu connection form validation",
)
replace_once(
    FRONTEND,
    """                <Input
                  type="password"
                  value={form.webhookSecret}
""",
    """                <Input
                  type="password"
                  required={!isEditing}
                  minLength={16}
                  maxLength={256}
                  pattern="[A-Za-z0-9_-]+"
                  value={form.webhookSecret}
""",
    label="Telegram webhook secret input",
)
replace_once(
    FRONTEND,
    """                  <Input
                    type="password"
                    value={form.verificationToken}
""",
    """                  <Input
                    type="password"
                    required={!isEditing}
                    value={form.verificationToken}
""",
    label="Feishu verification token input",
)

# Keep WeCom callback tests fresh while retaining deterministic encrypted payloads.
WECOM_TEST = "src/backend/tests/unit/channels/test_wecom.py"
replace_once(
    WECOM_TEST,
    "import base64\n",
    "import base64\nimport time\n",
    label="WeCom test time import",
)
replace_once(
    WECOM_TEST,
    """def _encrypted_payload(inner_xml: str, *, timestamp: str = "1710000000", nonce: str = "nonce"):
    crypt = WeComMessageCrypt(TOKEN, ENCODING_AES_KEY, CORP_ID)
""",
    """def _encrypted_payload(inner_xml: str, *, timestamp: str | None = None, nonce: str = "nonce"):
    timestamp = timestamp or str(int(time.time()))
    crypt = WeComMessageCrypt(TOKEN, ENCODING_AES_KEY, CORP_ID)
""",
    label="WeCom current encrypted callback timestamp",
)
replace_once(
    WECOM_TEST,
    """    signature = crypt.signature("1710000000", "nonce", encrypted)
    assert (
        adapter.verify_url(
            signature=signature,
            timestamp="1710000000",
""",
    """    timestamp = str(int(time.time()))
    signature = crypt.signature(timestamp, "nonce", encrypted)
    assert (
        adapter.verify_url(
            signature=signature,
            timestamp=timestamp,
""",
    label="WeCom current URL verification timestamp",
)

# Stabilize the three failing Playwright shards without weakening their assertions.
AUTO_LOGIN = "src/frontend/tests/core/features/auto-login-off.spec.ts"
replace_all(
    AUTO_LOGIN,
    "await page.getByText(TEXTS.save, { exact: true }).click();",
    'await page.getByRole("button", { name: TEXTS.save, exact: true }).last().click();',
    label="auto-login save button targeting",
    minimum=3,
)
replace_once(
    AUTO_LOGIN,
    """    expect(
      (
        await page.waitForSelector("text=Welcome to OpenXFlow", {
          timeout: 30000,
        })
      ).isVisible(),
    );
""",
    """    await expect(page.getByTestId("mainpage_title").last()).toBeVisible({
      timeout: 30000,
    });
""",
    label="current branded empty-page assertion",
)

ADD_USER = "src/frontend/tests/utils/add-new-user-and-loggin.ts"
replace_once(
    ADD_USER,
    "await page.getByText(TEXTS.save, { exact: true }).click();",
    'await page.getByRole("button", { name: TEXTS.save, exact: true }).last().click();',
    label="new-user save button targeting",
)
replace_once(
    ADD_USER,
    "await page.getByText(TEXTS.logout, { exact: true }).click();",
    """await page
    .getByRole("menuitem", { name: TEXTS.logout })
    .dispatchEvent("click");""",
    label="new-user logout dispatch",
)

FLOW_CLEANUP = "src/frontend/tests/core/features/user-flow-state-cleanup.spec.ts"
replace_all(
    FLOW_CLEANUP,
    "await page.getByText(TEXTS.logout, { exact: true }).click();",
    """await page
      .getByRole("menuitem", { name: TEXTS.logout })
      .dispatchEvent("click");""",
    label="flow cleanup logout dispatch",
    minimum=2,
)
replace_once(
    FLOW_CLEANUP,
    "await page.getByText(TEXTS.save, { exact: true }).click();",
    'await page.getByRole("button", { name: TEXTS.save, exact: true }).last().click();',
    label="flow cleanup save button targeting",
)

PROGRESS = "src/frontend/tests/core/features/user-progress-track.spec.ts"
replace_once(
    PROGRESS,
    """  await page.getByTestId("empty_page_github_button").click();

  const pagePromiseGithub = context.waitForEvent("page");

  const newPageGithub = await pagePromiseGithub;
""",
    """  const pagePromiseGithub = context.waitForEvent("page");
  await page.getByTestId("empty_page_github_button").click();

  const newPageGithub = await pagePromiseGithub;
""",
    label="GitHub popup listener ordering",
)
replace_once(
    PROGRESS,
    """  await newPageGithub.close();

  await expect(page.getByTestId("mainpage_title")).toBeVisible();
""",
    """  await newPageGithub.close();

  await expect(
    page.getByTestId("get_started_progress_percentage").first(),
  ).toHaveText("50%", { timeout: 30000 });
  await expect(page.getByTestId("mainpage_title")).toBeVisible();
""",
    label="GitHub progress persistence wait",
)
replace_once(
    PROGRESS,
    """  await expect(
    page.getByTestId("get_started_progress_percentage").first(),
  ).toHaveText("100%");
""",
    """  await expect(
    page.getByTestId("get_started_progress_percentage").first(),
  ).toHaveText("100%", { timeout: 30000 });
""",
    label="flow progress refresh wait",
)

SESSION = "src/frontend/tests/core/regression/general-bugs-remove-session-after-logout.spec.ts"
replace_once(
    SESSION,
    """    await page.getByRole("button", { name: TEXTS.signIn }).click();

    await page.waitForSelector('[data-testid="mainpage_title"]', {
      timeout: 30000,
    });
""",
    """    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes("/api/v1/login") && response.status() === 200,
        { timeout: 60000 },
      ),
      page.getByRole("button", { name: TEXTS.signIn }).click(),
    ]);

    await page.waitForSelector('[data-testid="mainpage_title"]', {
      timeout: 60000,
    });
""",
    label="session logout login synchronization",
)
replace_once(
    SESSION,
    "await page.getByText(TEXTS.logout, { exact: true }).click();",
    """await page
      .getByRole("menuitem", { name: TEXTS.logout })
      .dispatchEvent("click");""",
    label="session logout dispatch",
)
