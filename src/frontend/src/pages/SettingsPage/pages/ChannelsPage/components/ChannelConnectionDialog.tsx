import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type {
  ChannelAccessPolicy,
  ChannelConnection,
  ChannelConnectionCreate,
  ChannelConnectionUpdate,
  ChannelContextMode,
  ChannelResponseMode,
  ChannelType,
  ChannelUnconfiguredBehavior,
} from "@/controllers/API/queries/channels";
import useChannelCopy from "../use-channel-copy";
import { parseAllowedExtensions, readConnectionSetting } from "../utils";

type ConfigurableChannelType = Extract<
  ChannelType,
  "telegram" | "feishu" | "dingtalk" | "wecom"
>;

interface ConnectionFormState {
  channelType: ConfigurableChannelType;
  name: string;
  botToken: string;
  webhookSecret: string;
  appId: string;
  appSecret: string;
  verificationToken: string;
  encryptKey: string;
  clientId: string;
  clientSecret: string;
  robotCode: string;
  corpId: string;
  corpSecret: string;
  agentId: string;
  callbackToken: string;
  encodingAesKey: string;
  publicBaseUrl: string;
  maxFileSizeMb: string;
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
}

const DEFAULT_EXTENSIONS =
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

interface ChannelConnectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connection?: ChannelConnection | null;
  initialChannelType?: ConfigurableChannelType;
  loading?: boolean;
  onSubmit: (value: {
    payload: ChannelConnectionCreate | ChannelConnectionUpdate;
    publicBaseUrl: string;
  }) => Promise<void>;
}

const PROVIDER_KEYS: Record<ConfigurableChannelType, string> = {
  telegram: "channels.provider.telegram",
  feishu: "channels.provider.feishu",
  dingtalk: "channels.provider.dingtalk",
  wecom: "channels.provider.wecom",
};

function emptyForm(
  channelType: ConfigurableChannelType,
  providerName: string,
): ConnectionFormState {
  return {
    channelType,
    name: providerName,
    botToken: "",
    webhookSecret: "",
    appId: "",
    appSecret: "",
    verificationToken: "",
    encryptKey: "",
    clientId: "",
    clientSecret: "",
    robotCode: "",
    corpId: "",
    corpSecret: "",
    agentId: "",
    callbackToken: "",
    encodingAesKey: "",
    publicBaseUrl: "",
    maxFileSizeMb: "10",
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
  };
}

export default function ChannelConnectionDialog({
  open,
  onOpenChange,
  connection,
  initialChannelType = "telegram",
  loading = false,
  onSubmit,
}: ChannelConnectionDialogProps) {
  const copy = useChannelCopy();
  const { t } = useTranslation();
  const providerNameFor = (channelType: ConfigurableChannelType) =>
    t(PROVIDER_KEYS[channelType]);
  const isEditing = Boolean(connection);
  const [form, setForm] = useState<ConnectionFormState>(() =>
    emptyForm(initialChannelType, providerNameFor(initialChannelType)),
  );

  useEffect(() => {
    if (!open) return;
    const connectionType = connection?.channel_type;
    const channelType: ConfigurableChannelType =
      connectionType === "telegram" ||
      connectionType === "feishu" ||
      connectionType === "dingtalk" ||
      connectionType === "wecom"
        ? connectionType
        : initialChannelType;
    const allowed = readConnectionSetting<string[]>(
      connection,
      "allowed_file_extensions",
      [],
    );
    const providerName = providerNameFor(channelType);
    setForm({
      ...emptyForm(channelType, providerName),
      name: connection?.name ?? providerName,
      publicBaseUrl: readConnectionSetting(connection, "public_base_url", ""),
      maxFileSizeMb: String(
        readConnectionSetting(connection, "max_file_size_mb", 10),
      ),
      allowedExtensions:
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
    });
  }, [connection, initialChannelType, open, t]);

  const setField = <K extends keyof ConnectionFormState>(
    key: K,
    value: ConnectionFormState[K],
  ) => setForm((current) => ({ ...current, [key]: value }));

  const changeChannelType = (channelType: ConfigurableChannelType) => {
    setForm((current) => {
      const standardNames = [
        "Telegram",
        "Feishu",
        "DingTalk",
        "WeCom",
        copy("飞书"),
        copy("钉钉"),
        copy("企业微信"),
      ];
      return {
        ...emptyForm(channelType, providerNameFor(channelType)),
        name: standardNames.includes(current.name)
          ? providerNameFor(channelType)
          : current.name,
        publicBaseUrl: current.publicBaseUrl,
        maxFileSizeMb: current.maxFileSizeMb,
        allowedExtensions: current.allowedExtensions,
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
      };
    });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.name.trim()) return;
    if (
      !isEditing &&
      form.channelType === "telegram" &&
      !form.botToken.trim()
    ) {
      return;
    }
    if (
      !isEditing &&
      form.channelType === "feishu" &&
      (!form.appId.trim() || !form.appSecret.trim())
    ) {
      return;
    }
    if (
      !isEditing &&
      form.channelType === "dingtalk" &&
      (!form.clientId.trim() || !form.clientSecret.trim())
    ) {
      return;
    }
    if (
      !isEditing &&
      form.channelType === "wecom" &&
      (!form.corpId.trim() ||
        !form.corpSecret.trim() ||
        !form.agentId.trim() ||
        !form.callbackToken.trim() ||
        form.encodingAesKey.trim().length !== 43 ||
        !form.publicBaseUrl.trim())
    ) {
      return;
    }

    const credentials: Record<string, string> = {};
    if (form.channelType === "telegram") {
      if (form.botToken.trim()) credentials.bot_token = form.botToken.trim();
      if (form.webhookSecret.trim()) {
        credentials.webhook_secret = form.webhookSecret.trim();
      }
    } else if (form.channelType === "feishu") {
      if (form.appId.trim()) credentials.app_id = form.appId.trim();
      if (form.appSecret.trim()) credentials.app_secret = form.appSecret.trim();
      if (form.verificationToken.trim()) {
        credentials.verification_token = form.verificationToken.trim();
      }
      if (form.encryptKey.trim()) {
        credentials.encrypt_key = form.encryptKey.trim();
      }
    } else if (form.channelType === "dingtalk") {
      if (form.clientId.trim()) credentials.client_id = form.clientId.trim();
      if (form.clientSecret.trim()) {
        credentials.client_secret = form.clientSecret.trim();
      }
      if (form.robotCode.trim()) credentials.robot_code = form.robotCode.trim();
    } else {
      if (form.corpId.trim()) credentials.corp_id = form.corpId.trim();
      if (form.corpSecret.trim()) {
        credentials.corp_secret = form.corpSecret.trim();
      }
      if (form.agentId.trim()) credentials.agent_id = form.agentId.trim();
      if (form.callbackToken.trim()) {
        credentials.callback_token = form.callbackToken.trim();
      }
      if (form.encodingAesKey.trim()) {
        credentials.encoding_aes_key = form.encodingAesKey.trim();
      }
    }

    const settingsData = {
      ...(connection?.settings_data ?? {}),
      public_base_url: form.publicBaseUrl.trim(),
      max_file_size_mb: Math.max(1, Number(form.maxFileSizeMb) || 10),
      allowed_file_extensions: parseAllowedExtensions(form.allowedExtensions),
    };
    const productionSettings = {
      auto_discover_conversations: form.autoDiscoverConversations,
      unconfigured_behavior: form.unconfiguredBehavior,
      pending_notice_enabled: form.pendingNoticeEnabled,
      personal_commands_enabled: form.personalCommandsEnabled,
      default_response_mode: form.defaultResponseMode,
      default_allow_file_upload: form.defaultAllowFileUpload,
      access_policy: form.accessPolicy,
      default_context_mode: form.defaultContextMode,
      max_concurrency: boundedNumber(form.maxConcurrency, 10, 1, 100),
      per_user_concurrency: boundedNumber(form.perUserConcurrency, 1, 1, 10),
      per_user_queue_limit: boundedNumber(form.perUserQueueLimit, 3, 1, 100),
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
      ? {
          name: form.name.trim(),
          enabled: form.enabled,
          connection_mode: connectionMode,
          ...productionSettings,
          settings_data: settingsData,
          ...(Object.keys(credentials).length > 0 ? { credentials } : {}),
        }
      : {
          name: form.name.trim(),
          channel_type: form.channelType,
          enabled: form.enabled,
          connection_mode: connectionMode,
          ...productionSettings,
          settings_data: settingsData,
          credentials,
        };

    await onSubmit({ payload, publicBaseUrl: form.publicBaseUrl.trim() });
  };

  const providerName = providerNameFor(form.channelType);
  const keepValuePlaceholder = isEditing
    ? t("channels.connectionDialog.keepValue")
    : undefined;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {t(
              isEditing
                ? "channels.connectionDialog.editTitle"
                : "channels.connectionDialog.createTitle",
              { provider: providerName },
            )}
          </DialogTitle>
          <DialogDescription>
            {t("channels.connectionDialog.description")}
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              {t("channels.connectionDialog.name")}
              <Input
                value={form.name}
                onChange={(event) => setField("name", event.target.value)}
                placeholder={t("channels.connectionDialog.namePlaceholder", {
                  provider: providerName,
                })}
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm font-medium">
              {t("channels.connectionDialog.channelType")}
              <select
                className="primary-input h-10"
                value={form.channelType}
                onChange={(event) =>
                  changeChannelType(
                    event.target.value as ConfigurableChannelType,
                  )
                }
                disabled={isEditing}
              >
                <option value="telegram">
                  {t("channels.connectionDialog.telegramOption")}
                </option>
                <option value="feishu">
                  {t("channels.connectionDialog.feishuOption")}
                </option>
                <option value="dingtalk">
                  {t("channels.connectionDialog.dingtalkOption")}
                </option>
                <option value="wecom">
                  {t("channels.connectionDialog.wecomOption")}
                </option>
              </select>
            </label>
          </div>

          {form.channelType === "telegram" && (
            <>
              <label className="flex flex-col gap-2 text-sm font-medium">
                Bot Token
                <Input
                  type="password"
                  value={form.botToken}
                  onChange={(event) => setField("botToken", event.target.value)}
                  placeholder={
                    isEditing
                      ? t("channels.connectionDialog.keepToken")
                      : "123456:ABC..."
                  }
                  required={!isEditing}
                />
              </label>
              <label className="flex flex-col gap-2 text-sm font-medium">
                Webhook Secret
                <Input
                  type="password"
                  value={form.webhookSecret}
                  onChange={(event) =>
                    setField("webhookSecret", event.target.value)
                  }
                  placeholder={
                    keepValuePlaceholder ??
                    t("channels.connectionDialog.randomSecret")
                  }
                />
              </label>
            </>
          )}

          {form.channelType === "feishu" && (
            <>
              <div className="rounded-lg border bg-muted/40 p-4 text-sm">
                {t("channels.connectionDialog.feishuHelp")}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  App ID
                  <Input
                    value={form.appId}
                    onChange={(event) => setField("appId", event.target.value)}
                    placeholder={keepValuePlaceholder ?? "cli_xxxxxxxxx"}
                    required={!isEditing}
                  />
                </label>
                <label className="flex flex-col gap-2 text-sm font-medium">
                  App Secret
                  <Input
                    type="password"
                    value={form.appSecret}
                    onChange={(event) =>
                      setField("appSecret", event.target.value)
                    }
                    placeholder={
                      keepValuePlaceholder ??
                      t("channels.connectionDialog.feishuSecret")
                    }
                    required={!isEditing}
                  />
                </label>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  Verification Token
                  <Input
                    type="password"
                    value={form.verificationToken}
                    onChange={(event) =>
                      setField("verificationToken", event.target.value)
                    }
                    placeholder={
                      keepValuePlaceholder ??
                      t(
                        "channels.connectionDialog.verificationTokenPlaceholder",
                      )
                    }
                  />
                </label>
                <label className="flex flex-col gap-2 text-sm font-medium">
                  Encrypt Key
                  <Input
                    type="password"
                    value={form.encryptKey}
                    onChange={(event) =>
                      setField("encryptKey", event.target.value)
                    }
                    placeholder={
                      keepValuePlaceholder ??
                      t("channels.connectionDialog.encryptKeyPlaceholder")
                    }
                  />
                </label>
              </div>
            </>
          )}

          {form.channelType === "dingtalk" && (
            <>
              <div className="rounded-lg border bg-muted/40 p-4 text-sm">
                {t("channels.connectionDialog.dingtalkHelp")}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  Client ID / AppKey
                  <Input
                    value={form.clientId}
                    onChange={(event) =>
                      setField("clientId", event.target.value)
                    }
                    placeholder={keepValuePlaceholder ?? "dingxxxxxxxx"}
                    required={!isEditing}
                  />
                </label>
                <label className="flex flex-col gap-2 text-sm font-medium">
                  Client Secret / AppSecret
                  <Input
                    type="password"
                    value={form.clientSecret}
                    onChange={(event) =>
                      setField("clientSecret", event.target.value)
                    }
                    placeholder={
                      keepValuePlaceholder ??
                      t("channels.connectionDialog.dingtalkSecret")
                    }
                    required={!isEditing}
                  />
                </label>
              </div>
              <label className="flex flex-col gap-2 text-sm font-medium">
                Robot Code
                <Input
                  value={form.robotCode}
                  onChange={(event) =>
                    setField("robotCode", event.target.value)
                  }
                  placeholder={t(
                    "channels.connectionDialog.robotCodePlaceholder",
                  )}
                />
              </label>
            </>
          )}

          {form.channelType === "wecom" && (
            <>
              <div className="rounded-lg border bg-muted/40 p-4 text-sm">
                {t("channels.connectionDialog.wecomHelp")}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  {t("channels.connectionDialog.corpId")}
                  <Input
                    value={form.corpId}
                    onChange={(event) => setField("corpId", event.target.value)}
                    placeholder={keepValuePlaceholder ?? "wwxxxxxxxxxxxxxxxx"}
                    required={!isEditing}
                  />
                </label>
                <label className="flex flex-col gap-2 text-sm font-medium">
                  {t("channels.connectionDialog.agentId")}
                  <Input
                    type="number"
                    min={1}
                    value={form.agentId}
                    onChange={(event) =>
                      setField("agentId", event.target.value)
                    }
                    placeholder={keepValuePlaceholder ?? "1000002"}
                    required={!isEditing}
                  />
                </label>
              </div>
              <label className="flex flex-col gap-2 text-sm font-medium">
                {t("channels.connectionDialog.corpSecret")}
                <Input
                  type="password"
                  value={form.corpSecret}
                  onChange={(event) =>
                    setField("corpSecret", event.target.value)
                  }
                  placeholder={
                    keepValuePlaceholder ??
                    t("channels.connectionDialog.corpSecretPlaceholder")
                  }
                  required={!isEditing}
                />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  {t("channels.connectionDialog.callbackToken")}
                  <Input
                    type="password"
                    value={form.callbackToken}
                    onChange={(event) =>
                      setField("callbackToken", event.target.value)
                    }
                    placeholder={
                      keepValuePlaceholder ??
                      t("channels.connectionDialog.callbackTokenPlaceholder")
                    }
                    required={!isEditing}
                  />
                </label>
                <label className="flex flex-col gap-2 text-sm font-medium">
                  EncodingAESKey
                  <Input
                    type="password"
                    minLength={43}
                    maxLength={43}
                    value={form.encodingAesKey}
                    onChange={(event) =>
                      setField("encodingAesKey", event.target.value)
                    }
                    placeholder={
                      keepValuePlaceholder ??
                      t("channels.connectionDialog.encodingKeyPlaceholder")
                    }
                    required={!isEditing}
                  />
                </label>
              </div>
            </>
          )}

          <label className="flex flex-col gap-2 text-sm font-medium">
            {t("channels.connectionDialog.publicUrl")}
            <Input
              type="url"
              value={form.publicBaseUrl}
              onChange={(event) =>
                setField("publicBaseUrl", event.target.value)
              }
              placeholder="https://openxflow.example.com"
              required={form.channelType === "wecom"}
            />
            <span className="text-xs font-normal text-muted-foreground">
              {form.channelType === "dingtalk"
                ? t("channels.connectionDialog.publicUrlStreamHelp")
                : form.channelType === "wecom"
                  ? t("channels.connectionDialog.publicUrlWecomHelp")
                  : t("channels.connectionDialog.publicUrlHelp")}
            </span>
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              {t("channels.connectionDialog.maxFileSize")}
              <Input
                type="number"
                min={1}
                value={form.maxFileSizeMb}
                onChange={(event) =>
                  setField("maxFileSizeMb", event.target.value)
                }
              />
            </label>
            <label className="flex flex-col gap-2 text-sm font-medium">
              {t("channels.connectionDialog.allowedExtensions")}
              <Input
                value={form.allowedExtensions}
                onChange={(event) =>
                  setField("allowedExtensions", event.target.value)
                }
                placeholder="pdf, docx, xlsx, pptx, txt, md, json"
              />
            </label>
          </div>

          <div className="rounded-xl border p-4">
            <div>
              <div className="text-sm font-semibold">
                {copy("生产策略与容量")}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {copy(
                  "控制共享身份、群聊上下文、并发、排队、限流、配额和超时。",
                )}
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
                  <option value="hybrid">
                    {copy("混合：共享能力 + 个人资源")}
                  </option>
                  <option value="shared">
                    {copy("共享：群成员共用机器人")}
                  </option>
                  <option value="bound_only">
                    {copy("仅已绑定 OpenXFlow 用户")}
                  </option>
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
                  <option value="notify_pending">
                    {copy("记录并提示管理员配置")}
                  </option>
                  <option value="use_global_default">
                    {copy("直接使用全局默认工作流")}
                  </option>
                  <option value="ignore">{copy("静默忽略")}</option>
                </select>
              </label>
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {[
                ["maxConcurrency", copy("连接最大并发"), 1, 100],
                ["perUserConcurrency", copy("单用户并发"), 1, 10],
                ["perUserQueueLimit", copy("单用户队列上限"), 1, 100],
                [
                  "rateLimitPerMinute",
                  copy("每分钟请求限制，0 为不限"),
                  0,
                  10000,
                ],
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
                    <div className="text-xs text-muted-foreground">
                      {String(help)}
                    </div>
                  </div>
                  <Switch
                    checked={form[key as keyof ConnectionFormState] as boolean}
                    onCheckedChange={(checked) =>
                      setField(
                        key as keyof ConnectionFormState,
                        checked as never,
                      )
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
              </div>
              <div className="text-xs text-muted-foreground">
                {t("channels.connectionDialog.enableHelp")}
              </div>
            </div>
            <Switch
              checked={form.enabled}
              onCheckedChange={(checked) => setField("enabled", checked)}
            />
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              type="button"
              onClick={() => onOpenChange(false)}
            >
              {t("channels.actions.cancel")}
            </Button>
            <Button type="submit" loading={loading}>
              {t(
                isEditing
                  ? "channels.actions.saveConnection"
                  : "channels.actions.createConnection",
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
