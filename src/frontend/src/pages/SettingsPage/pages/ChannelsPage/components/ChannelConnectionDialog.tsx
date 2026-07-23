import { useEffect, useState } from "react";
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

function getProviderName(channelType: ConfigurableChannelType): string {
  if (channelType === "feishu") return "飞书";
  if (channelType === "dingtalk") return "钉钉";
  if (channelType === "wecom") return "企业微信";
  return "Telegram";
}

function emptyForm(channelType: ConfigurableChannelType): ConnectionFormState {
  return {
    channelType,
    name: getProviderName(channelType),
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
  const isEditing = Boolean(connection);
  const [form, setForm] = useState<ConnectionFormState>(() =>
    emptyForm(initialChannelType),
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
    setForm({
      ...emptyForm(channelType),
      name: connection?.name ?? getProviderName(channelType),
      publicBaseUrl: readConnectionSetting(connection, "public_base_url", ""),
      maxFileSizeMb: String(
        readConnectionSetting(connection, "max_file_size_mb", 10),
      ),
      allowedExtensions:
        allowed.length > 0 ? allowed.join(", ") : DEFAULT_EXTENSIONS,
      enabled: connection?.enabled ?? true,
    });
  }, [connection, initialChannelType, open]);

  const setField = <K extends keyof ConnectionFormState>(
    key: K,
    value: ConnectionFormState[K],
  ) => setForm((current) => ({ ...current, [key]: value }));

  const changeChannelType = (channelType: ConfigurableChannelType) => {
    setForm((current) => {
      const standardNames = ["Telegram", "飞书", "钉钉", "企业微信"];
      return {
        ...emptyForm(channelType),
        name: standardNames.includes(current.name)
          ? getProviderName(channelType)
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
      if (form.corpSecret.trim())
        credentials.corp_secret = form.corpSecret.trim();
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

  const providerName = getProviderName(form.channelType);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? `编辑${providerName}连接` : `新增${providerName}连接`}
          </DialogTitle>
          <DialogDescription>
            保存应用凭证、接入方式以及手机文件上传限制。凭证加密存储，保存后不会回显。
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              连接名称
              <Input
                value={form.name}
                onChange={(event) => setField("name", event.target.value)}
                placeholder={`例如：生产环境${providerName}`}
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm font-medium">
              渠道类型
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
                <option value="telegram">Telegram Bot</option>
                <option value="feishu">飞书自建应用</option>
                <option value="dingtalk">钉钉企业内部机器人</option>
                <option value="wecom">企业微信自建应用</option>
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
                    isEditing ? "留空保留已配置 Token" : "123456:ABC..."
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
                    isEditing ? "留空保留原值" : "建议设置随机字符串"
                  }
                />
              </label>
            </>
          )}

          {form.channelType === "feishu" && (
            <>
              <div className="rounded-lg border bg-muted/40 p-4 text-sm">
                飞书事件订阅可启用加密。启用后，Verification Token 和 Encrypt
                Key 必须与飞书开放平台中的事件订阅配置完全一致。
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  App ID
                  <Input
                    value={form.appId}
                    onChange={(event) => setField("appId", event.target.value)}
                    placeholder={isEditing ? "留空保留原值" : "cli_xxxxxxxxx"}
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
                    placeholder={isEditing ? "留空保留原值" : "飞书应用密钥"}
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
                      isEditing ? "留空保留原值" : "事件订阅 Verification Token"
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
                      isEditing ? "留空保留原值" : "可选，事件订阅 Encrypt Key"
                    }
                  />
                </label>
              </div>
            </>
          )}

          {form.channelType === "dingtalk" && (
            <>
              <div className="rounded-lg border bg-muted/40 p-4 text-sm">
                钉钉默认使用 Stream
                长连接，不需要公网回调地址。服务会自动维护连接并在断线后重连。
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  Client ID / AppKey
                  <Input
                    value={form.clientId}
                    onChange={(event) =>
                      setField("clientId", event.target.value)
                    }
                    placeholder={isEditing ? "留空保留原值" : "dingxxxxxxxx"}
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
                    placeholder={isEditing ? "留空保留原值" : "钉钉应用密钥"}
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
                  placeholder="通常与 Client ID 相同，留空自动使用 Client ID"
                />
              </label>
            </>
          )}

          {form.channelType === "wecom" && (
            <>
              <div className="rounded-lg border bg-muted/40 p-4 text-sm">
                企业微信要求使用 HTTPS 回调，并使用 Token 与 EncodingAESKey
                对回调进行签名校验和 AES 解密。
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  企业 ID（CorpID）
                  <Input
                    value={form.corpId}
                    onChange={(event) => setField("corpId", event.target.value)}
                    placeholder={
                      isEditing ? "留空保留原值" : "wwxxxxxxxxxxxxxxxx"
                    }
                    required={!isEditing}
                  />
                </label>
                <label className="flex flex-col gap-2 text-sm font-medium">
                  应用 AgentID
                  <Input
                    type="number"
                    min={1}
                    value={form.agentId}
                    onChange={(event) =>
                      setField("agentId", event.target.value)
                    }
                    placeholder={isEditing ? "留空保留原值" : "1000002"}
                    required={!isEditing}
                  />
                </label>
              </div>
              <label className="flex flex-col gap-2 text-sm font-medium">
                应用 Secret
                <Input
                  type="password"
                  value={form.corpSecret}
                  onChange={(event) =>
                    setField("corpSecret", event.target.value)
                  }
                  placeholder={
                    isEditing ? "留空保留原值" : "企业微信应用 Secret"
                  }
                  required={!isEditing}
                />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  回调 Token
                  <Input
                    type="password"
                    value={form.callbackToken}
                    onChange={(event) =>
                      setField("callbackToken", event.target.value)
                    }
                    placeholder={
                      isEditing ? "留空保留原值" : "企业微信回调 Token"
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
                      isEditing ? "留空保留原值" : "43 位 EncodingAESKey"
                    }
                    required={!isEditing}
                  />
                </label>
              </div>
            </>
          )}

          <label className="flex flex-col gap-2 text-sm font-medium">
            OpenXFlow 公开地址
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
                ? "Stream 模式不需要该地址；仅在启用签名 HTTP 回调时填写。"
                : form.channelType === "wecom"
                  ? "企业微信必须配置外网可访问的 HTTPS 地址，用于保存接收消息服务器。"
                  : "必须是外网可访问的 HTTPS 地址，保存后会生成平台回调地址。"}
            </span>
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              单文件大小限制（MB）
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
              允许的扩展名
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
              <div className="text-sm font-medium">启用连接</div>
              <div className="text-xs text-muted-foreground">
                关闭后停止接收消息、运行工作流和解析文件。
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
              取消
            </Button>
            <Button type="submit" loading={loading}>
              {isEditing ? "保存连接" : "创建连接"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
