import { getChannelStatusMeta, parseAllowedExtensions } from "../utils";

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
});
