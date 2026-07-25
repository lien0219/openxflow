import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const channelRoot = resolve(
  process.cwd(),
  "src/pages/SettingsPage/pages/ChannelsPage",
);
const queryRoot = resolve(
  process.cwd(),
  "src/controllers/API/queries/channels",
);

function read(path: string): string {
  return readFileSync(path, "utf8");
}

describe("Channel Center production UI contract", () => {
  it("exposes message, delivery, execution, audit and overview operations", () => {
    const page = read(resolve(channelRoot, "index.tsx"));
    const queryExports = read(resolve(queryRoot, "index.ts"));

    expect(page).toContain('id: "messages"');
    expect(page).toContain('id: "deliveries"');
    expect(page).toContain('id: "logs"');
    expect(page).toContain('id: "audits"');
    expect(queryExports).toContain('export * from "./use-get-channel-overview"');
    expect(queryExports).toContain('export * from "./use-get-channel-messages"');
    expect(queryExports).toContain('export * from "./use-get-channel-deliveries"');
    expect(queryExports).toContain('export * from "./use-get-channel-audits"');
    expect(queryExports).toContain('export * from "./use-retry-channel-delivery"');
  });

  it("uses the production response mode spelling and complete execution states", () => {
    const conversationDialog = read(
      resolve(channelRoot, "components/ConversationBindingDialog.tsx"),
    );
    const types = read(resolve(queryRoot, "types.ts"));

    expect(conversationDialog).not.toContain('value="mentions_only"');
    expect(conversationDialog).toContain('value="mention_only"');
    expect(conversationDialog).toContain('value="commands_only"');
    expect(conversationDialog).toContain('value="disabled"');
    for (const status of [
      "queued",
      "running",
      "succeeded",
      "failed",
      "timeout",
      "cancelled",
      "delivery_failed",
    ]) {
      expect(types).toContain(`| "${status}"`);
    }
  });

  it("does not advertise unscanned media or legacy Office formats by default", () => {
    const connectionDialog = read(
      resolve(channelRoot, "components/ChannelConnectionDialog.tsx"),
    );

    expect(connectionDialog).toContain(
      '"pdf, docx, xlsx, pptx, csv, txt, md, json, html, rtf, xml, yaml, yml"',
    );
    expect(connectionDialog).not.toContain("png, jpg");
    expect(connectionDialog).not.toContain("mp3, wav");
    expect(connectionDialog).not.toContain('"doc,');
    expect(connectionDialog).not.toContain('"xls,');
    expect(connectionDialog).not.toContain('"ppt,');
  });
});
