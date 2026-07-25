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
        raise RuntimeError(f"Missing frontend rollout target: {label}")
    write(path, content.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str, *, label: str) -> None:
    content = read(path)
    start_index = content.find(start)
    end_index = content.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"Missing frontend rollout block: {label}")
    write(path, content[:start_index] + replacement + content[end_index:])


# ---------------------------------------------------------------------------
# Main channel page navigation
# ---------------------------------------------------------------------------
INDEX = "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/index.tsx"
replace_once(
    INDEX,
    'import AccountsTab from "./components/AccountsTab";\n',
    'import AccountsTab from "./components/AccountsTab";\n'
    'import AuditLogTab from "./components/AuditLogTab";\n',
    label="audit tab import",
)
replace_once(
    INDEX,
    'import DefaultRoutingTab from "./components/DefaultRoutingTab";\n',
    'import DefaultRoutingTab from "./components/DefaultRoutingTab";\n'
    'import DeliveriesTab from "./components/DeliveriesTab";\n',
    label="delivery tab import",
)
replace_once(
    INDEX,
    'import ExecutionLogsTab from "./components/ExecutionLogsTab";\n',
    'import ExecutionLogsTab from "./components/ExecutionLogsTab";\n'
    'import MessagesTab from "./components/MessagesTab";\n',
    label="message tab import",
)
replace_once(
    INDEX,
    '  | "accounts"\n  | "logs";\n',
    '  | "accounts"\n'
    '  | "messages"\n'
    '  | "deliveries"\n'
    '  | "logs"\n'
    '  | "audits";\n',
    label="detail tab union",
)
replace_once(
    INDEX,
    '  { id: "accounts", label: "账号" },\n  { id: "logs", label: "运行记录" },\n',
    '  { id: "accounts", label: "账号" },\n'
    '  { id: "messages", label: "消息" },\n'
    '  { id: "deliveries", label: "投递" },\n'
    '  { id: "logs", label: "运行记录" },\n'
    '  { id: "audits", label: "审计" },\n',
    label="detail tab definitions",
)
replace_once(
    INDEX,
    '''              {activeTab === "accounts" && (
                <AccountsTab connectionId={selectedConnection.id} />
              )}
              {activeTab === "logs" && (
                <ExecutionLogsTab connectionId={selectedConnection.id} />
              )}
''',
    '''              {activeTab === "accounts" && (
                <AccountsTab connectionId={selectedConnection.id} />
              )}
              {activeTab === "messages" && (
                <MessagesTab connectionId={selectedConnection.id} />
              )}
              {activeTab === "deliveries" && (
                <DeliveriesTab connectionId={selectedConnection.id} />
              )}
              {activeTab === "logs" && (
                <ExecutionLogsTab connectionId={selectedConnection.id} />
              )}
              {activeTab === "audits" && (
                <AuditLogTab connectionId={selectedConnection.id} />
              )}
''',
    label="detail tab rendering",
)

# ---------------------------------------------------------------------------
# Per-conversation access, context and response policies
# ---------------------------------------------------------------------------
DIALOG = "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/ConversationBindingDialog.tsx"
replace_once(
    DIALOG,
    '''import type {
  ChannelConversationBinding,
  ChannelConversationBindingUpdate,
  ChannelConversationRouteMode,
} from "@/controllers/API/queries/channels";
''',
    '''import type {
  ChannelAccessPolicyOverride,
  ChannelContextModeOverride,
  ChannelConversationBinding,
  ChannelConversationBindingUpdate,
  ChannelConversationRouteMode,
  ChannelResponseMode,
} from "@/controllers/API/queries/channels";
''',
    label="conversation policy type imports",
)
replace_once(
    DIALOG,
    '''  routeMode: ChannelConversationRouteMode;
  responseMode: string;
  defaultFlowId: string;
''',
    '''  routeMode: ChannelConversationRouteMode;
  responseMode: ChannelResponseMode;
  accessPolicy: ChannelAccessPolicyOverride;
  contextMode: ChannelContextModeOverride;
  defaultFlowId: string;
''',
    label="conversation policy form fields",
)
replace_once(
    DIALOG,
    '''    routeMode: "inherit",
    responseMode: "mentions_only",
    defaultFlowId: "",
''',
    '''    routeMode: "inherit",
    responseMode: "mention_only",
    accessPolicy: "inherit",
    contextMode: "inherit",
    defaultFlowId: "",
''',
    label="conversation policy defaults",
)
replace_once(
    DIALOG,
    '''      routeMode: binding.route_mode,
      responseMode: binding.response_mode,
      defaultFlowId: binding.default_flow_id ?? "",
''',
    '''      routeMode: binding.route_mode,
      responseMode: binding.response_mode,
      accessPolicy: binding.access_policy,
      contextMode: binding.context_mode,
      defaultFlowId: binding.default_flow_id ?? "",
''',
    label="conversation policy initialization",
)
replace_once(
    DIALOG,
    '''      route_mode: form.routeMode,
      response_mode: form.responseMode,
      allow_file_upload: form.allowFileUpload,
''',
    '''      route_mode: form.routeMode,
      response_mode: form.responseMode,
      access_policy: form.accessPolicy,
      context_mode: form.contextMode,
      allow_file_upload: form.allowFileUpload,
''',
    label="conversation policy submit",
)
replace_between(
    DIALOG,
    '          {isGroupConversation && supportsMentions && (\n',
    '          {supportsFileUpload && (\n',
    '''          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              {copy("访问策略")}
              <select
                className="primary-input h-10"
                value={form.accessPolicy}
                onChange={(event) =>
                  setField(
                    "accessPolicy",
                    event.target.value as ChannelAccessPolicyOverride,
                  )
                }
              >
                <option value="inherit">{copy("继承连接策略")}</option>
                <option value="shared">{copy("所有成员共享使用")}</option>
                <option value="bound_only">{copy("仅已绑定账号")}</option>
                <option value="hybrid">{copy("共享与个人混合")}</option>
              </select>
              <span className="text-xs font-normal text-muted-foreground">
                {copy("共享能力使用服务身份，个人资源使用已绑定的 OpenXFlow 用户。")}
              </span>
            </label>

            <label className="flex flex-col gap-2 text-sm font-medium">
              {copy("会话上下文")}
              <select
                className="primary-input h-10"
                value={form.contextMode}
                onChange={(event) =>
                  setField(
                    "contextMode",
                    event.target.value as ChannelContextModeOverride,
                  )
                }
              >
                <option value="inherit">{copy("继承连接设置")}</option>
                <option value="isolated">{copy("按成员隔离")}</option>
                <option value="shared">{copy("群内共享上下文")}</option>
              </select>
              <span className="text-xs font-normal text-muted-foreground">
                {isGroupConversation
                  ? copy("生产环境建议按成员隔离，防止不同成员上下文串线。")
                  : copy("私聊始终按当前用户和线程形成独立会话。")}
              </span>
            </label>
          </div>

          <label className="flex flex-col gap-2 text-sm font-medium">
            {t("channels.conversationDialog.responseMode")}
            <select
              className="primary-input h-10"
              value={form.responseMode}
              onChange={(event) =>
                setField(
                  "responseMode",
                  event.target.value as ChannelResponseMode,
                )
              }
            >
              {isGroupConversation && supportsMentions ? (
                <option value="mention_only">{copy("仅被提及时响应")}</option>
              ) : null}
              <option value="all_messages">{copy("响应全部消息")}</option>
              <option value="commands_only">{copy("仅响应指令")}</option>
              <option value="disabled">{copy("完全停用响应")}</option>
            </select>
          </label>

''',
    label="conversation access context response controls",
)
replace_once(
    DIALOG,
    '              emptyLabel={t("channels.conversationDialog.noKnowledgeBase")}\n',
    '              emptyLabel={copy("继承连接默认知识库")}\n',
    label="conversation knowledge base inheritance label",
)
replace_once(
    DIALOG,
    '                  {t("channels.conversationDialog.allowUploadHelp")}\n',
    '                  {copy("文件会先经过内容类型、宏、路径穿越和压缩炸弹检查，再进入知识库。")}\n',
    label="secure upload help",
)

# ---------------------------------------------------------------------------
# Connection-level production controls
# ---------------------------------------------------------------------------
CONNECTION_DIALOG = "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/ChannelConnectionDialog.tsx"
replace_once(
    CONNECTION_DIALOG,
    '''  ChannelConnection,
  ChannelConnectionCreate,
  ChannelConnectionUpdate,
  ChannelType,
''',
    '''  ChannelAccessPolicy,
  ChannelConnection,
  ChannelConnectionCreate,
  ChannelConnectionUpdate,
  ChannelContextMode,
  ChannelResponseMode,
  ChannelType,
  ChannelUnconfiguredBehavior,
''',
    label="connection production type imports",
)
replace_once(
    CONNECTION_DIALOG,
    '''  maxFileSizeMb: string;
  allowedExtensions: string;
  enabled: boolean;
''',
    '''  maxFileSizeMb: string;
  allowedExtensions: string;
  accessPolicy: ChannelAccessPolicy;
  defaultContextMode: ChannelContextMode;
  defaultResponseMode: ChannelResponseMode;
  unconfiguredBehavior: ChannelUnconfiguredBehavior;
  maxConcurrency: string;
  perUserConcurrency: string;
  perUserQueueLimit: string;
  rateLimitPerMinute: string;
  dailyQuota: string;
  taskTimeoutSeconds: string;
  queueTimeoutSeconds: string;
  sharedContextWindow: string;
  contextRetentionDays: string;
  autoDiscoverConversations: boolean;
  pendingNoticeEnabled: boolean;
  personalCommandsEnabled: boolean;
  defaultAllowFileUpload: boolean;
  enabled: boolean;
''',
    label="connection production form fields",
)
replace_once(
    CONNECTION_DIALOG,
    '''const DEFAULT_EXTENSIONS =
  "pdf, docx, xlsx, csv, txt, md, json, html, png, jpg, jpeg, webp, gif, mp3, wav, m4a, ogg, mp4";
''',
    '''const DEFAULT_EXTENSIONS =
  "pdf, docx, xlsx, pptx, csv, txt, md, json, html, rtf, xml, yaml, yml";

function boundedNumber(
  value: string,
  fallback: number,
  minimum: number,
  maximum?: number,
): number {
  const parsed = Number(value);
  const normalized = Number.isFinite(parsed) ? parsed : fallback;
  return Math.min(maximum ?? normalized, Math.max(minimum, normalized));
}
''',
    label="secure default extensions and number normalization",
)
replace_once(
    CONNECTION_DIALOG,
    '''    maxFileSizeMb: "10",
    allowedExtensions: DEFAULT_EXTENSIONS,
    enabled: true,
''',
    '''    maxFileSizeMb: "10",
    allowedExtensions: DEFAULT_EXTENSIONS,
    accessPolicy: "hybrid",
    defaultContextMode: "isolated",
    defaultResponseMode: "mention_only",
    unconfiguredBehavior: "notify_pending",
    maxConcurrency: "10",
    perUserConcurrency: "1",
    perUserQueueLimit: "3",
    rateLimitPerMinute: "20",
    dailyQuota: "0",
    taskTimeoutSeconds: "120",
    queueTimeoutSeconds: "60",
    sharedContextWindow: "20",
    contextRetentionDays: "30",
    autoDiscoverConversations: true,
    pendingNoticeEnabled: true,
    personalCommandsEnabled: true,
    defaultAllowFileUpload: true,
    enabled: true,
''',
    label="connection production defaults",
)
replace_once(
    CONNECTION_DIALOG,
    '''      allowedExtensions:
        allowed.length > 0 ? allowed.join(", ") : DEFAULT_EXTENSIONS,
      enabled: connection?.enabled ?? true,
''',
    '''      allowedExtensions:
        allowed.length > 0 ? allowed.join(", ") : DEFAULT_EXTENSIONS,
      accessPolicy: connection?.access_policy ?? "hybrid",
      defaultContextMode: connection?.default_context_mode ?? "isolated",
      defaultResponseMode: connection?.default_response_mode ?? "mention_only",
      unconfiguredBehavior:
        connection?.unconfigured_behavior ?? "notify_pending",
      maxConcurrency: String(connection?.max_concurrency ?? 10),
      perUserConcurrency: String(connection?.per_user_concurrency ?? 1),
      perUserQueueLimit: String(connection?.per_user_queue_limit ?? 3),
      rateLimitPerMinute: String(connection?.rate_limit_per_minute ?? 20),
      dailyQuota: String(connection?.daily_quota ?? 0),
      taskTimeoutSeconds: String(connection?.task_timeout_seconds ?? 120),
      queueTimeoutSeconds: String(connection?.queue_timeout_seconds ?? 60),
      sharedContextWindow: String(connection?.shared_context_window ?? 20),
      contextRetentionDays: String(connection?.context_retention_days ?? 30),
      autoDiscoverConversations:
        connection?.auto_discover_conversations ?? true,
      pendingNoticeEnabled: connection?.pending_notice_enabled ?? true,
      personalCommandsEnabled: connection?.personal_commands_enabled ?? true,
      defaultAllowFileUpload: connection?.default_allow_file_upload ?? true,
      enabled: connection?.enabled ?? true,
''',
    label="connection production initialization",
)
replace_once(
    CONNECTION_DIALOG,
    '''        allowedExtensions: current.allowedExtensions,
        enabled: current.enabled,
''',
    '''        allowedExtensions: current.allowedExtensions,
        accessPolicy: current.accessPolicy,
        defaultContextMode: current.defaultContextMode,
        defaultResponseMode: current.defaultResponseMode,
        unconfiguredBehavior: current.unconfiguredBehavior,
        maxConcurrency: current.maxConcurrency,
        perUserConcurrency: current.perUserConcurrency,
        perUserQueueLimit: current.perUserQueueLimit,
        rateLimitPerMinute: current.rateLimitPerMinute,
        dailyQuota: current.dailyQuota,
        taskTimeoutSeconds: current.taskTimeoutSeconds,
        queueTimeoutSeconds: current.queueTimeoutSeconds,
        sharedContextWindow: current.sharedContextWindow,
        contextRetentionDays: current.contextRetentionDays,
        autoDiscoverConversations: current.autoDiscoverConversations,
        pendingNoticeEnabled: current.pendingNoticeEnabled,
        personalCommandsEnabled: current.personalCommandsEnabled,
        defaultAllowFileUpload: current.defaultAllowFileUpload,
        enabled: current.enabled,
''',
    label="preserve production controls across provider switch",
)
replace_once(
    CONNECTION_DIALOG,
    '''    const connectionMode =
      form.channelType === "dingtalk" ? "stream" : "webhook";
    const payload = isEditing
''',
    '''    const productionSettings = {
      auto_discover_conversations: form.autoDiscoverConversations,
      unconfigured_behavior: form.unconfiguredBehavior,
      pending_notice_enabled: form.pendingNoticeEnabled,
      personal_commands_enabled: form.personalCommandsEnabled,
      default_response_mode: form.defaultResponseMode,
      default_allow_file_upload: form.defaultAllowFileUpload,
      access_policy: form.accessPolicy,
      default_context_mode: form.defaultContextMode,
      max_concurrency: boundedNumber(form.maxConcurrency, 10, 1, 100),
      per_user_concurrency: boundedNumber(
        form.perUserConcurrency,
        1,
        1,
        10,
      ),
      per_user_queue_limit: boundedNumber(
        form.perUserQueueLimit,
        3,
        1,
        100,
      ),
      rate_limit_per_minute: boundedNumber(
        form.rateLimitPerMinute,
        20,
        0,
        10000,
      ),
      daily_quota: boundedNumber(form.dailyQuota, 0, 0),
      task_timeout_seconds: boundedNumber(
        form.taskTimeoutSeconds,
        120,
        10,
        3600,
      ),
      queue_timeout_seconds: boundedNumber(
        form.queueTimeoutSeconds,
        60,
        5,
        3600,
      ),
      shared_context_window: boundedNumber(
        form.sharedContextWindow,
        20,
        0,
        100,
      ),
      context_retention_days: boundedNumber(
        form.contextRetentionDays,
        30,
        1,
        365,
      ),
    };
    const connectionMode =
      form.channelType === "dingtalk" ? "stream" : "webhook";
    const payload = isEditing
''',
    label="normalize production settings",
)
replace_once(
    CONNECTION_DIALOG,
    '''          connection_mode: connectionMode,
          settings_data: settingsData,
''',
    '''          connection_mode: connectionMode,
          ...productionSettings,
          settings_data: settingsData,
''',
    label="connection update production payload",
)
replace_once(
    CONNECTION_DIALOG,
    '''          connection_mode: connectionMode,
          settings_data: settingsData,
          credentials,
''',
    '''          connection_mode: connectionMode,
          ...productionSettings,
          settings_data: settingsData,
          credentials,
''',
    label="connection create production payload",
)
replace_once(
    CONNECTION_DIALOG,
    '                placeholder="pdf, docx, xlsx, txt, png, jpg, mp3"\n',
    '                placeholder="pdf, docx, xlsx, pptx, txt, md, json"\n',
    label="secure extension placeholder",
)
replace_once(
    CONNECTION_DIALOG,
    '''          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <div className="text-sm font-medium">
                {t("channels.connectionDialog.enable")}
''',
    '''          <div className="rounded-xl border p-4">
            <div>
              <div className="text-sm font-semibold">{copy("生产策略与容量")}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {copy("控制共享身份、群聊上下文、并发、排队、限流、配额和超时。")}
              </div>
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-2 text-sm font-medium">
                {copy("访问策略")}
                <select
                  className="primary-input h-10"
                  value={form.accessPolicy}
                  onChange={(event) =>
                    setField(
                      "accessPolicy",
                      event.target.value as ChannelAccessPolicy,
                    )
                  }
                >
                  <option value="hybrid">{copy("混合：共享能力 + 个人资源")}</option>
                  <option value="shared">{copy("共享：群成员共用机器人")}</option>
                  <option value="bound_only">{copy("仅已绑定 OpenXFlow 用户")}</option>
                </select>
              </label>
              <label className="flex flex-col gap-2 text-sm font-medium">
                {copy("默认上下文模式")}
                <select
                  className="primary-input h-10"
                  value={form.defaultContextMode}
                  onChange={(event) =>
                    setField(
                      "defaultContextMode",
                      event.target.value as ChannelContextMode,
                    )
                  }
                >
                  <option value="isolated">{copy("按群成员和线程隔离")}</option>
                  <option value="shared">{copy("群内共享上下文")}</option>
                </select>
              </label>
              <label className="flex flex-col gap-2 text-sm font-medium">
                {copy("默认响应模式")}
                <select
                  className="primary-input h-10"
                  value={form.defaultResponseMode}
                  onChange={(event) =>
                    setField(
                      "defaultResponseMode",
                      event.target.value as ChannelResponseMode,
                    )
                  }
                >
                  <option value="mention_only">{copy("仅被提及时响应")}</option>
                  <option value="all_messages">{copy("响应全部消息")}</option>
                  <option value="commands_only">{copy("仅响应指令")}</option>
                  <option value="disabled">{copy("完全停用响应")}</option>
                </select>
              </label>
              <label className="flex flex-col gap-2 text-sm font-medium">
                {copy("未配置会话处理")}
                <select
                  className="primary-input h-10"
                  value={form.unconfiguredBehavior}
                  onChange={(event) =>
                    setField(
                      "unconfiguredBehavior",
                      event.target.value as ChannelUnconfiguredBehavior,
                    )
                  }
                >
                  <option value="notify_pending">{copy("记录并提示管理员配置")}</option>
                  <option value="use_global_default">{copy("直接使用全局默认工作流")}</option>
                  <option value="ignore">{copy("静默忽略")}</option>
                </select>
              </label>
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {[
                ["maxConcurrency", copy("连接最大并发"), 1, 100],
                ["perUserConcurrency", copy("单用户并发"), 1, 10],
                ["perUserQueueLimit", copy("单用户队列上限"), 1, 100],
                ["rateLimitPerMinute", copy("每分钟请求限制，0 为不限"), 0, 10000],
                ["dailyQuota", copy("每日配额，0 为不限"), 0, undefined],
                ["queueTimeoutSeconds", copy("排队超时（秒）"), 5, 3600],
                ["taskTimeoutSeconds", copy("执行超时（秒）"), 10, 3600],
                ["sharedContextWindow", copy("共享上下文窗口"), 0, 100],
                ["contextRetentionDays", copy("上下文保留天数"), 1, 365],
              ].map(([key, label, min, max]) => (
                <label
                  key={String(key)}
                  className="flex flex-col gap-2 text-sm font-medium"
                >
                  {String(label)}
                  <Input
                    type="number"
                    min={Number(min)}
                    max={max === undefined ? undefined : Number(max)}
                    value={form[key as keyof ConnectionFormState] as string}
                    onChange={(event) =>
                      setField(
                        key as keyof ConnectionFormState,
                        event.target.value as never,
                      )
                    }
                  />
                </label>
              ))}
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {[
                [
                  "autoDiscoverConversations",
                  copy("自动发现会话"),
                  copy("首次消息自动进入待配置会话列表。"),
                ],
                [
                  "pendingNoticeEnabled",
                  copy("待配置提示"),
                  copy("对尚未配置的会话发送一次友好提示。"),
                ],
                [
                  "personalCommandsEnabled",
                  copy("允许个人指令"),
                  copy("已绑定成员可使用个人范围的工作流指令。"),
                ],
                [
                  "defaultAllowFileUpload",
                  copy("默认允许安全文件上传"),
                  copy("上传文件仍需通过内容扫描与知识库授权。"),
                ],
              ].map(([key, label, help]) => (
                <div
                  key={String(key)}
                  className="flex items-center justify-between rounded-lg bg-muted/40 p-3"
                >
                  <div>
                    <div className="text-sm font-medium">{String(label)}</div>
                    <div className="text-xs text-muted-foreground">{String(help)}</div>
                  </div>
                  <Switch
                    checked={form[key as keyof ConnectionFormState] as boolean}
                    onCheckedChange={(checked) =>
                      setField(key as keyof ConnectionFormState, checked as never)
                    }
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <div className="text-sm font-medium">
                {t("channels.connectionDialog.enable")}
''',
    label="connection production controls UI",
)
