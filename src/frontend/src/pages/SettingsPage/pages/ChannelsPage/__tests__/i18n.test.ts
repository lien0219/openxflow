import i18n from "@/i18n";

describe("channel locale initialization", () => {
  it("loads the persisted Chinese bundle before the first render", () => {
    expect(i18n.hasResourceBundle("zh-Hans", "translation")).toBe(true);
    expect(i18n.getFixedT("zh-Hans")("channels.title")).toBe("渠道中心");
  });
});
