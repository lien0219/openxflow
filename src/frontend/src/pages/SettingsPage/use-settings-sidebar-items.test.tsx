import { renderHook } from "@testing-library/react";
import type { SettingsSidebarItem } from "./use-settings-sidebar-items";
import { useSettingsSidebarItems } from "./use-settings-sidebar-items";

let mockIsSuperuser = false;
let mockMigrationEnabled = false;
let mockCanReadRbac = false;

jest.mock("@/hooks/use-rbac-access", () => ({
  useRbacAccess: () => ({ canReadRbac: mockCanReadRbac }),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock("@/components/common/genericIconComponent", () => ({
  __esModule: true,
  default: ({ name }: { name: string }) => <span>{name}</span>,
}));

jest.mock("@/customization/components/custom-store-sidebar", () => ({
  CustomStoreSidebar: (): SettingsSidebarItem[] => [
    {
      title: "Custom Store",
      href: "/settings/custom-store",
      icon: null,
    },
  ],
}));

jest.mock("@/customization/feature-flags", () => ({
  ENABLE_DATASTAX_LANGFLOW: false,
  ENABLE_PROFILE_ICONS: true,
}));

jest.mock("@/stores/authStore", () => ({
  __esModule: true,
  default: (
    selector: (state: {
      autoLogin: boolean;
      userData: { is_superuser: boolean };
    }) => unknown,
  ) =>
    selector({
      autoLogin: false,
      userData: { is_superuser: mockIsSuperuser },
    }),
}));

jest.mock("@/stores/storeStore", () => ({
  useStoreStore: (selector: (state: { hasStore: boolean }) => unknown) =>
    selector({ hasStore: false }),
}));

jest.mock("@/stores/utilityStore", () => ({
  useUtilityStore: (
    selector: (state: {
      featureFlags: { instance_migration: boolean };
    }) => unknown,
  ) =>
    selector({
      featureFlags: { instance_migration: mockMigrationEnabled },
    }),
}));

describe("useSettingsSidebarItems", () => {
  beforeEach(() => {
    mockIsSuperuser = false;
    mockMigrationEnabled = false;
    mockCanReadRbac = false;
  });

  it("keeps the Channels settings entry", () => {
    const { result } = renderHook(() => useSettingsSidebarItems());

    expect(result.current).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          href: "/settings/channels",
          title: "settings.nav.channels",
        }),
      ]),
    );
  });

  it.each([false, true])(
    "shows Permissions only when RBAC read access is %s",
    (canReadRbac) => {
      mockCanReadRbac = canReadRbac;

      const { result } = renderHook(() => useSettingsSidebarItems());

      expect(
        result.current.some((item) => item.href === "/settings/permissions"),
      ).toBe(canReadRbac);
    },
  );

  it.each([
    { isSuperuser: false, migrationEnabled: false },
    { isSuperuser: false, migrationEnabled: true },
    { isSuperuser: true, migrationEnabled: false },
  ])(
    "hides Migration when isSuperuser=$isSuperuser and migrationEnabled=$migrationEnabled",
    ({ isSuperuser, migrationEnabled }) => {
      mockIsSuperuser = isSuperuser;
      mockMigrationEnabled = migrationEnabled;

      const { result } = renderHook(() => useSettingsSidebarItems());

      expect(result.current).not.toEqual(
        expect.arrayContaining([
          expect.objectContaining({ href: "/settings/migration" }),
        ]),
      );
    },
  );

  it("adds Migration after Messages without changing the custom-store insertion", () => {
    mockIsSuperuser = true;
    mockMigrationEnabled = true;

    const { result } = renderHook(() => useSettingsSidebarItems());
    const hrefs = result.current.map((item) => item.href);

    expect(hrefs[2]).toBe("/settings/custom-store");
    expect(hrefs.at(-2)).toBe("/settings/messages");
    expect(hrefs.at(-1)).toBe("/settings/migration");
  });
});
