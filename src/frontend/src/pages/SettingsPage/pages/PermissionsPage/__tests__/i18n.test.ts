import i18n from "@/i18n";
import {
  translateRbacPermission,
  translateRbacRoleName,
  translateRbacValue,
  translateRbacWarning,
} from "../rbac-i18n";

describe("RBAC permission-center locale initialization", () => {
  it("loads the Chinese permission labels before the first render", () => {
    expect(i18n.hasResourceBundle("zh-Hans", "translation")).toBe(true);
    expect(i18n.getFixedT("zh-Hans")("rbac.title")).toBe("权限与访问控制");
    expect(i18n.getFixedT("zh-Hans")("settings.nav.permissions")).toBe(
      "权限管理",
    );
  });

  it("localizes backend warnings, permission codes and RBAC enum values", () => {
    const t = i18n.getFixedT("zh-Hans");

    expect(
      translateRbacWarning(
        t,
        "AUTO_LOGIN is enabled; disable it before using multi-user RBAC in production.",
      ),
    ).toContain("自动登录");
    expect(translateRbacValue(t, "domain", "channel")).toBe("渠道");
    expect(translateRbacValue(t, "permissionLevel", "execute")).toBe("执行");
    expect(translateRbacPermission(t, "flow:read")).toBe("工作流：读取");
    expect(translateRbacPermission(t, "rbac:*")).toBe("权限管理：全部权限");
    expect(translateRbacRoleName(t, "platform_admin")).toBe("平台管理员");
    expect(translateRbacRoleName(t, "admin")).toBe("工作区管理员");
    expect(translateRbacRoleName(t, "developer")).toBe("开发者");
  });
});
