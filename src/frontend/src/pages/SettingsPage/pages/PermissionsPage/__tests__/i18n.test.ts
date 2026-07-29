import i18n from "@/i18n";

describe("RBAC permission-center locale initialization", () => {
  it("loads the Chinese permission labels before the first render", () => {
    expect(i18n.hasResourceBundle("zh-Hans", "translation")).toBe(true);
    expect(i18n.getFixedT("zh-Hans")("rbac.title")).toBe("权限与访问控制");
    expect(i18n.getFixedT("zh-Hans")("settings.nav.permissions")).toBe(
      "权限管理",
    );
  });
});
