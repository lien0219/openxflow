jest.mock("@/controllers/API", () => ({
  getRepoStars: jest.fn(),
  getDiscordCount: jest.fn(),
}));

describe("initial theme preference", () => {
  afterEach(() => jest.restoreAllMocks());

  it.each([
    { preference: "light", cachedDark: "true", systemDark: true, dark: false },
    { preference: "dark", cachedDark: "false", systemDark: false, dark: true },
    { preference: "system", cachedDark: "false", systemDark: true, dark: true },
    { preference: null, cachedDark: "true", systemDark: false, dark: false },
  ])(
    "resolves $preference before rendering when the cached appearance is $cachedDark",
    ({ preference, cachedDark, systemDark, dark }) => {
      jest.spyOn(Storage.prototype, "getItem").mockImplementation((key) => {
        if (key === "themePreference") return preference;
        if (key === "isDark") return cachedDark;
        return null;
      });
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      jest.spyOn(window, "matchMedia").mockReturnValue({
        ...mediaQuery,
        matches: systemDark,
      });

      jest.isolateModules(() => {
        const { useDarkStore } =
          jest.requireActual<typeof import("../darkStore")>("../darkStore");
        expect(useDarkStore.getState().dark).toBe(dark);
      });
    },
  );
});
