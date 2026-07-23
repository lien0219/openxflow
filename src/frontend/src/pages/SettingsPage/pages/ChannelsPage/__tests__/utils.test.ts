import type { ChannelConnection } from "@/controllers/API/queries/channels";
import {
  buildChannelWebhookUrl,
  getChannelStatusMeta,
  parseAllowedExtensions,
} from "../utils";

describe("channel settings helpers", () => {
  it("normalizes and deduplicates file extensions", () => {
    expect(parseAllowedExtensions(".PDF, docx，pdf  xlsx")).toEqual([
      "pdf",
      "docx",
      "xlsx",
    ]);
  });

  it("returns a readable fallback for unknown statuses", () => {
    expect(getChannelStatusMeta("configuring").label).toBe("待配置");
    expect(getChannelStatusMeta("connected").label).toBe("已连接");
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
