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
} from "@/controllers/API/queries/channels";
import {
  parseAllowedExtensions,
  readConnectionSetting,
} from "../utils";

interface ConnectionFormState {
  name: string;
  botToken: string;
  webhookSecret: string;
  publicBaseUrl: string;
  maxFileSizeMb: string;
  allowedExtensions: string;
  enabled: boolean;
}

const DEFAULT_EXTENSIONS = "pdf, docx, xlsx, csv, txt, md, json, html";

interface ChannelConnectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connection?: ChannelConnection | null;
  loading?: boolean;
  onSubmit: (value: {
    payload: ChannelConnectionCreate | ChannelConnectionUpdate;
    publicBaseUrl: string;
  }) => Promise<void>;
}

export default function ChannelConnectionDialog({
  open,
  onOpenChange,
  connection,
  loading = false,
  onSubmit,
}: ChannelConnectionDialogProps) {
  const isEditing = Boolean(connection);
  const [form, setForm] = useState<ConnectionFormState>({
    name: "Telegram",
    botToken: "",
    webhookSecret: "",
    publicBaseUrl: "",
    maxFileSizeMb: "10",
    allowedExtensions: DEFAULT_EXTENSIONS,
    enabled: true,
  });

  useEffect(() => {
    if (!open) return;
    const allowed = readConnectionSetting<string[]>(
      connection,
      "allowed_file_extensions",
      [],
    );
    setForm({
      name: connection?.name ?? "Telegram",
      botToken: "",
      webhookSecret: "",
      publicBaseUrl: readConnectionSetting(
        connection,
        "public_base_url",
        "",
      ),
      maxFileSizeMb: String(
        readConnectionSetting(connection, "max_file_size_mb", 10),
      ),
      allowedExtensions:
        allowed.length > 0 ? allowed.join(", ") : DEFAULT_EXTENSIONS,
      enabled: connection?.enabled ?? true,
    });
  }, [connection, open]);

  const setField = <K extends keyof ConnectionFormState>(
    key: K,
    value: ConnectionFormState[K],
  ) => setForm((current) => ({ ...current, [key]: value }));

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.name.trim()) return;
    if (!isEditing && !form.botToken.trim()) return;

    const credentials: Record<string, string> = {};
    if (form.botToken.trim()) credentials.bot_token = form.botToken.trim();
    if (form.webhookSecret.trim()) {
      credentials.webhook_secret = form.webhookSecret.trim();
    }

    const settingsData = {
      ...(connection?.settings_data ?? {}),
      public_base_url: form.publicBaseUrl.trim(),
      max_file_size_mb: Math.max(1, Number(form.maxFileSizeMb) || 10),
      allowed_file_extensions: parseAllowedExtensions(form.allowedExtensions),
    };

    const payload = isEditing
      ? {
          name: form.name.trim(),
          enabled: form.enabled,
          connection_mode: "webhook",
          settings_data: settingsData,
          ...(Object.keys(credentials).length > 0 ? { credentials } : {}),
        }
      : {
          name: form.name.trim(),
          channel_type: "telegram" as const,
          enabled: form.enabled,
          connection_mode: "webhook",
          settings_data: settingsData,
          credentials,
        };

    await onSubmit({ payload, publicBaseUrl: form.publicBaseUrl.trim() });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "编辑 Telegram 连接" : "新增 Telegram 连接"}
          </DialogTitle>
          <DialogDescription>
            保存机器人凭证、公开访问地址以及手机文件上传限制。凭证仅加密存储，保存后不会回显。
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              连接名称
              <Input
                value={form.name}
                onChange={(event) => setField("name", event.target.value)}
                placeholder="例如：生产环境 Telegram"
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm font-medium">
              渠道类型
              <select className="primary-input h-10" value="telegram" disabled>
                <option value="telegram">Telegram Bot</option>
              </select>
            </label>
          </div>

          <label className="flex flex-col gap-2 text-sm font-medium">
            Bot Token {isEditing && <span className="font-normal text-muted-foreground">留空表示保留原值</span>}
            <Input
              type="password"
              value={form.botToken}
              onChange={(event) => setField("botToken", event.target.value)}
              placeholder={isEditing ? "留空保留已配置 Token" : "123456:ABC..."}
              required={!isEditing}
            />
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium">
            Webhook Secret
            <Input
              type="password"
              value={form.webhookSecret}
              onChange={(event) => setField("webhookSecret", event.target.value)}
              placeholder={isEditing ? "留空保留原值" : "建议设置随机字符串"}
            />
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium">
            OpenXFlow 公开地址
            <Input
              value={form.publicBaseUrl}
              onChange={(event) => setField("publicBaseUrl", event.target.value)}
              placeholder="https://openxflow.example.com"
            />
            <span className="text-xs font-normal text-muted-foreground">
              用于自动生成 Telegram Webhook 地址，必须是外网可访问的 HTTPS 地址。
            </span>
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              单文件大小限制（MB）
              <Input
                type="number"
                min={1}
                value={form.maxFileSizeMb}
                onChange={(event) => setField("maxFileSizeMb", event.target.value)}
              />
            </label>
            <label className="flex flex-col gap-2 text-sm font-medium">
              允许的扩展名
              <Input
                value={form.allowedExtensions}
                onChange={(event) =>
                  setField("allowedExtensions", event.target.value)
                }
                placeholder="pdf, docx, xlsx, txt"
              />
            </label>
          </div>

          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <div className="text-sm font-medium">启用连接</div>
              <div className="text-xs text-muted-foreground">
                关闭后平台回调将返回未找到，不再触发工作流。
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
              {isEditing ? "保存连接" : "创建并配置"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
