import type { ChannelConnection } from "@/controllers/API/queries/channels";

export function parseAllowedExtensions(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\s,，]+/)
        .map((item) => item.trim().toLowerCase().replace(/^\./, ""))
        .filter(Boolean),
    ),
  );
}

export function readConnectionSetting<T>(
  connection: ChannelConnection | null | undefined,
  key: string,
  fallback: T,
): T {
  const value = connection?.settings_data?.[key];
  return value === undefined || value === null ? fallback : (value as T);
}

export function buildChannelWebhookUrl(
  connection: ChannelConnection,
): string | null {
  const publicBaseUrl = readConnectionSetting(
    connection,
    "public_base_url",
    "",
  ).trim();
  if (!publicBaseUrl) return null;
  return `${publicBaseUrl.replace(/\/+$/, "")}/api/v1/channel-webhooks/${connection.channel_type}/${connection.id}`;
}

export function getChannelStatusMeta(status: string): {
  label: string;
  className: string;
} {
  switch (status) {
    case "connected":
      return {
        label: "已连接",
        className: "bg-accent-emerald text-accent-emerald-foreground",
      };
    case "error":
      return {
        label: "异常",
        className: "bg-accent-red text-accent-red-foreground",
      };
    case "disconnected":
      return {
        label: "已断开",
        className: "bg-muted text-muted-foreground",
      };
    default:
      return {
        label: "待配置",
        className: "bg-accent-amber text-accent-amber-foreground",
      };
  }
}

export function getApiErrorMessage(error: unknown): string {
  const candidate = error as {
    message?: string;
    response?: { data?: { detail?: string } };
  };
  return (
    candidate.response?.data?.detail ??
    candidate.message ??
    "请求失败，请稍后重试。"
  );
}
