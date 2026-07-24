import type { useTranslation } from "react-i18next";
import type { ChannelConnection } from "@/controllers/API/queries/channels";

type TranslationFunction = ReturnType<typeof useTranslation>["t"];

interface WorkflowOption {
  id: string;
  name: string;
  endpoint_name?: string | null;
}

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

export function formatWorkflowOptionLabel(flow: WorkflowOption): string {
  const shortId = flow.id.slice(0, 8);
  const endpoint = flow.endpoint_name?.trim();
  return `${flow.name} [${shortId}]${endpoint ? ` / ${endpoint}` : ""}`;
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

export function getChannelStatusMeta(
  status: string,
  t: TranslationFunction,
): {
  label: string;
  className: string;
} {
  switch (status) {
    case "connected":
      return {
        label: t("channels.status.connected"),
        className: "bg-accent-emerald text-accent-emerald-foreground",
      };
    case "error":
      return {
        label: t("channels.status.error"),
        className: "bg-accent-red text-accent-red-foreground",
      };
    case "disconnected":
      return {
        label: t("channels.status.disconnected"),
        className: "bg-muted text-muted-foreground",
      };
    default:
      return {
        label: t("channels.status.configuring"),
        className: "bg-accent-amber text-accent-amber-foreground",
      };
  }
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  const candidate = error as {
    message?: string;
    response?: { data?: { detail?: string } };
  };
  return candidate.response?.data?.detail ?? candidate.message ?? fallback;
}
