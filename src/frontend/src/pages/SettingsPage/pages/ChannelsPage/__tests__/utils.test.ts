import type { useTranslation } from "react-i18next";
import type { ChannelConnection } from "@/controllers/API/queries/channels";
import { resolveChannelCopy } from "../use-channel-copy";
import {
  buildChannelWebhookUrl,
  formatWorkflowOptionLabel,
  getChannelStatusMeta,
  parseAllowedExtensions,
} from "../utils";

type TranslationFunction = ReturnType<typeof useTranslation>["t"];

const translations: Record<string, string> = {
  "channels.status.configuring": "Not configured",
  "channels.status.connected": "Connected",
};
const t = ((key: string) => translations[key] ?? key) as TranslationFunction;

describe("channel settings helpers", () => {
  it("normalizes and deduplicates file extensions", () => {
    expect(parseAllowedExtensions(".PDF, docx，pdf  xlsx")).toEqual([
      "pdf",
      "docx",
      "xlsx",
    ]);
  });

  it("formats workflow options with short IDs and endpoints", () => {
    expect(
      formatWorkflowOptionLabel({
        id: "12345678-aaaa-bbbb-cccc-1234567890ab",
        name: "Document Q&A",
        endpoint_name: "document-qa",
      }),
    ).toBe("Document Q&A [12345678] / document-qa");
    expect(
      formatWorkflowOptionLabel({
        id: "abcdefgh-aaaa-bbbb-cccc-1234567890ab",
        name: "Fallback flow",
      }),
    ).toBe("Fallback flow [abcdefgh]");
  });

  it("returns localized labels for channel statuses", () => {
    expect(getChannelStatusMeta("configuring", t).label).toBe("Not configured");
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

  it("uses Chinese copy for zh locales and English fallback otherwise", () => {
    expect(resolveChannelCopy("zh-CN", "会话管理")).toBe("会话管理");
    expect(resolveChannelCopy("en", "会话管理")).toBe(
      "Conversation management",
    );
    expect(resolveChannelCopy("ja", "共 {{count}} 个会话", { count: 3 })).toBe(
      "3 conversations",
    );
  });
});
