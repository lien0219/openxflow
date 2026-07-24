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
  ChannelConnection,
  ChannelConnectionCreate,
  ChannelConnectionUpdate,
  ChannelType,
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
  enabled: boolean;
}

const DEFAULT_EXTENSIONS =
  "pdf, docx, xlsx, csv, txt, md, json, html, png, jpg, jpeg, webp, gif, mp3, wav, m4a, ogg, mp4";

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
    const connectionMode =
      form.channelType === "dingtalk" ? "stream" : "webhook";
    const payload = isEditing
      ? {
          name: form.name.trim(),
          enabled: form.enabled,
          connection_mode: connectionMode,
          settings_data: settingsData,
          ...(Object.keys(credentials).length > 0 ? { credentials } : {}),
        }
      : {
          name: form.name.trim(),
          channel_type: form.channelType,
          enabled: form.enabled,
          connection_mode: connectionMode,
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
                placeholder="pdf, docx, xlsx, txt, png, jpg, mp3"
              />
            </label>
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
