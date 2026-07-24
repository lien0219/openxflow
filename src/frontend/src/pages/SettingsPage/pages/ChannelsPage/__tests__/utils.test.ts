import type { TFunction } from "i18next";
import type { ChannelConnection } from "@/controllers/API/queries/channels";
import {
  buildChannelWebhookUrl,
  getChannelStatusMeta,
  parseAllowedExtensions,
} from "../utils";

const translations: Record<string, string> = {
  "channels.status.configuring": "Not configured",
  "channels.status.connected": "Connected",
};
const t = ((key: string) => translations[key] ?? key) as TFunction;

describe("channel settings helpers", () => {
  it("normalizes and deduplicates file extensions", () => {
    expect(parseAllowedExtensions(".PDF, docx，pdf  xlsx")).toEqual([
      "pdf",
      "docx",
      "xlsx",
    ]);
  });

  it("returns localized labels for channel statuses", () => {
    expect(getChannelStatusMeta("configuring", t).label).toBe(
      "Not configured",
    );
    expect(getChannelStatusMeta("connected", t).label).toBe("Connected");
  });

  it("builds a provider-specific webhook URL", () => {
    const connection = {
      id: "connection-id",
      channel_type: "feishu",
      settings_data: { public_base_url: "https://example.com/" },
    } as ChannelConnection;

    expect(buildChannelWebhookUrl(connection)).toBe(
      "https://example.com/api/v1/channel-webhooks/feishu/connection-id",
    );
  });
});
