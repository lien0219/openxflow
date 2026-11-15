import { expect, test } from "../../fixtures";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    for (const [key, value] of Object.entries({
      languagePreference: "en",
      themePreset: "classic",
      themePreference: "light",
    })) {
      if (!localStorage.getItem(key)) localStorage.setItem(key, value);
    }
  });
});

for (const initialTheme of [
  {
    preset: "classic",
    preference: "light",
    system: "dark",
    appearance: "light",
  },
  {
    preset: "classic",
    preference: "dark",
    system: "light",
    appearance: "dark",
  },
  {
    preset: "classic",
    preference: "system",
    system: "dark",
    appearance: "dark",
  },
  {
    preset: "classic",
    preference: "system",
    system: "light",
    appearance: "light",
  },
  {
    preset: "nebula",
    preference: "light",
    system: "light",
    appearance: "dark",
  },
  { preset: "polar", preference: "dark", system: "dark", appearance: "light" },
] as const) {
  test(
    `applies ${initialTheme.preset} ${initialTheme.preference} theme before application scripts with a ${initialTheme.system} system`,
    { tag: ["@release"] },
    async ({ page }) => {
      await page.emulateMedia({ colorScheme: initialTheme.system });
      await page.addInitScript(({ preset, preference, appearance }) => {
        localStorage.setItem("themePreset", preset);
        localStorage.setItem("themePreference", preference);
        localStorage.setItem("isDark", String(appearance !== "dark"));
      }, initialTheme);
      // The HTML shell must select the theme even before React can load.
      await page.route("**/*", (route) =>
        route.request().resourceType() === "script"
          ? route.abort()
          : route.continue(),
      );
      await page.goto("/", { waitUntil: "domcontentloaded" });

      expect(
        await page.evaluate(() => ({
          preset: document.documentElement.dataset.theme,
          appearance: document.documentElement.dataset.appearance,
          colorScheme: getComputedStyle(document.documentElement).colorScheme,
        })),
      ).toEqual({
        preset: initialTheme.preset,
        appearance: initialTheme.appearance,
        colorScheme: initialTheme.appearance,
      });
    },
  );
}

test(
  "public homepage renders without backend initialization",
  { tag: ["@release"] },
  async ({ page }) => {
    const apiRequests: string[] = [];
    await page.route("**/api/**", (route) => {
      apiRequests.push(new URL(route.request().url()).pathname);
      return route.fulfill({ status: 503, json: { detail: "Unavailable" } });
    });

    await page.goto("/");
    await expect(page.getByTestId("landing-title")).toHaveText(
      "Connect ideas Build AI workflows",
    );
    await expect(page).toHaveURL(/\/$/);
    await page.waitForLoadState("networkidle");
    expect(apiRequests).toEqual([]);
  },
);

test(
  "homepage appearance toggle switches and persists across reloads",
  { tag: ["@release"] },
  async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute(
      "data-appearance",
      "light",
    );
    await page.getByTestId("landing-theme-toggle").click();
    await expect(page.locator("html")).toHaveAttribute(
      "data-appearance",
      "dark",
    );
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute(
      "data-appearance",
      "dark",
    );
    await page.getByTestId("landing-theme-toggle").click();
    await expect(page.locator("html")).toHaveAttribute(
      "data-appearance",
      "light",
    );
  },
);

test(
  "appearance toggle works from presets with a fixed appearance",
  { tag: ["@release"] },
  async ({ page }) => {
    await page.goto("/");
    for (const preset of ["nebula", "polar"]) {
      await page.evaluate(
        (value) => localStorage.setItem("themePreset", value),
        preset,
      );
      await page.reload();
      const appearance = preset === "nebula" ? "dark" : "light";
      await expect(page.locator("html")).toHaveAttribute(
        "data-appearance",
        appearance,
      );
      await page.getByTestId("landing-theme-toggle").click();
      await expect(page.locator("html")).toHaveAttribute(
        "data-theme",
        "classic",
      );
      await expect(page.locator("html")).toHaveAttribute(
        "data-appearance",
        appearance === "dark" ? "light" : "dark",
      );
    }
  },
);

test(
  "navigation compacts on downward scroll and expands on upward scroll",
  { tag: ["@release"] },
  async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 800 });
    await page.goto("/");
    const header = page.getByTestId("landing-header");
    const scroller = page.getByTestId("landing-page");
    await expect(header).toHaveAttribute("data-compact", "false");
    const expandedWidth = (await header.boundingBox())!.width;
    await scroller.evaluate((element) =>
      element.scrollTo({ top: 440, behavior: "instant" }),
    );
    await expect(header).toHaveAttribute("data-compact", "true");
    await expect
      .poll(async () => (await header.boundingBox())!.width)
      .toBeLessThan(expandedWidth - 40);
    await scroller.evaluate((element) =>
      element.scrollTo({ top: 260, behavior: "instant" }),
    );
    await expect(header).toHaveAttribute("data-compact", "false");
    await page
      .getByRole("navigation")
      .getByRole("link", { name: "Capabilities" })
      .click();
    await expect(page.locator("#capabilities-title")).toBeInViewport();
    await expect(
      page.getByRole("navigation").getByRole("link", { name: "Capabilities" }),
    ).toHaveAttribute("aria-current", "location");
  },
);

test(
  "capabilities stays selected when a tall viewport limits anchor scrolling",
  { tag: ["@release"] },
  async ({ page }) => {
    await page.setViewportSize({ width: 2560, height: 1440 });
    await page.goto("/");
    const capabilities = page
      .getByRole("navigation")
      .getByRole("link", { name: "Capabilities" });
    await capabilities.click();
    await expect(page).toHaveURL(/#capabilities$/);
    await expect(page.locator("#capabilities-title")).toBeInViewport();
    await expect(capabilities).toHaveAttribute("aria-current", "location");
    const scroller = page.getByTestId("landing-page");
    await expect
      .poll(() =>
        scroller.evaluate(
          (element) =>
            element.scrollHeight - element.scrollTop - element.clientHeight,
        ),
      )
      .toBeLessThanOrEqual(2);
    await expect(capabilities).toHaveAttribute("aria-current", "location");
    await scroller.evaluate((element) =>
      element.scrollTo({ top: 0, behavior: "instant" }),
    );
    await expect(
      page.getByRole("navigation").getByRole("link", { name: "Overview" }),
    ).toHaveAttribute("aria-current", "location");
    await page.goto("/#capabilities");
    await expect(capabilities).toHaveAttribute("aria-current", "location");
  },
);

test(
  "particle water pauses offscreen and uses a static scene for reduced motion",
  { tag: ["@release"] },
  async ({ page }) => {
    await page.goto("/");
    const water = page.locator(".landing-particle-hero");
    await expect(water).toHaveAttribute("data-motion", "running");
    const painted = await water.evaluate((element: HTMLCanvasElement) => {
      const context = element.getContext("2d");
      const pixels = context!.getImageData(
        0,
        0,
        element.width,
        element.height,
      ).data;
      return pixels.some((value, index) => index % 4 === 3 && value > 0);
    });
    expect(painted).toBe(true);
    const scroller = page.getByTestId("landing-page");
    await scroller.evaluate((element) =>
      element.scrollTo({ top: element.scrollHeight, behavior: "instant" }),
    );
    await expect(water).toHaveAttribute("data-motion", "paused");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await scroller.evaluate((element) =>
      element.scrollTo({ top: 0, behavior: "instant" }),
    );
    await expect(water).toHaveAttribute("data-motion", "static");
  },
);

test(
  "page background fills the viewport and keeps rendering beyond the hero",
  { tag: ["@release"] },
  async ({ page }) => {
    await page.setViewportSize({ width: 2560, height: 1440 });
    await page.goto("/");
    const background = page.locator(".landing-particle-ambient");
    await expect(background).toHaveAttribute("data-motion", "running");
    const before = (await background.boundingBox())!;
    expect(before.x).toBe(0);
    expect(before.y).toBe(0);
    expect(before.width).toBe(2560);
    expect(before.height).toBe(1440);
    const painted = await background.evaluate((canvas: HTMLCanvasElement) => {
      const pixels = canvas
        .getContext("2d")!
        .getImageData(0, 0, canvas.width, canvas.height).data;
      return pixels.some((value, index) => index % 4 === 3 && value > 0);
    });
    expect(painted).toBe(true);
    await page
      .getByTestId("landing-page")
      .evaluate((element) =>
        element.scrollTo({ top: element.scrollHeight, behavior: "instant" }),
      );
    await expect(background).toHaveAttribute("data-motion", "running");
    expect(await background.boundingBox()).toEqual(before);
    await page.getByRole("button", { name: "Pause animations" }).click();
    await expect(background).toHaveAttribute("data-motion", "paused");
    await page.getByRole("button", { name: "Resume animations" }).click();
    await expect(background).toHaveAttribute("data-motion", "running");
  },
);

test(
  "workflow starts automatically, pauses, and restarts a changed scenario",
  { tag: ["@release"] },
  async ({ page }) => {
    await page.goto("/#workflow");
    const preview = page.getByTestId("landing-preview");
    await expect(preview).toHaveAttribute("data-motion", "running");
    await expect(preview).toHaveAttribute("data-stage", "1");
    await page.getByRole("button", { name: "Pause animations" }).click();
    await expect(preview).toHaveAttribute("data-motion", "paused");
    const frozen = await preview.getAttribute("data-stage");
    await page.waitForTimeout(1700);
    await expect(preview).toHaveAttribute("data-stage", frozen!);
    await page.getByRole("button", { name: "Content creation" }).click();
    await expect(preview).toHaveAttribute("data-stage", "0");
    await expect(
      page.getByText("Write a short introduction for my new idea."),
    ).toBeVisible();
    await page.getByRole("button", { name: "Resume animations" }).click();
    await expect(preview).toHaveAttribute("data-stage", "1");
    await expect(preview).toHaveAttribute("data-stage", "3");
    await expect(preview).toHaveAttribute("data-stage", "0");
    await page.setViewportSize({ width: 1440, height: 700 });
    await page
      .getByTestId("landing-page")
      .evaluate((element) =>
        element.scrollTo({ top: element.scrollHeight, behavior: "instant" }),
      );
    await expect(preview).toHaveAttribute("data-motion", "paused");
    const capabilities = page.locator(".landing-capability");
    await expect(capabilities.first()).toHaveAttribute(
      "data-motion",
      "running",
    );
    await expect(capabilities.first()).toHaveAttribute("data-stage", "1");
    await page.getByRole("button", { name: "Pause animations" }).click();
    for (const capability of await capabilities.all()) {
      await expect(capability).toHaveAttribute("data-motion", "paused");
    }
  },
);

test(
  "pipeline demos show complete scenes and remain usable with reduced motion",
  { tag: ["@release"] },
  async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.getByTestId("landing-preview")).toHaveAttribute(
      "data-motion",
      "static",
    );
    await expect(page.getByTestId("landing-preview")).toHaveAttribute(
      "data-stage",
      "3",
    );
    await page.getByRole("button", { name: "Content creation" }).click();
    await expect(page.getByTestId("landing-preview")).toHaveAttribute(
      "data-stage",
      "3",
    );
    await expect(
      page.getByText("Write a short introduction for my new idea."),
    ).toBeVisible();
    for (const capability of await page.locator(".landing-capability").all()) {
      await expect(capability).toHaveAttribute("data-motion", "static");
      await expect(capability).toHaveAttribute("data-stage", "3");
    }
    expect(
      await page
        .locator(".landing-orbit")
        .first()
        .evaluate((element) => getComputedStyle(element).animationName),
    ).toBe("none");
  },
);

test(
  "homepage supports all locales and page navigation on a narrow screen",
  { tag: ["@release"] },
  async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 812 });
    await page.goto("/");

    const headings = [
      ["zh-Hans", "连接想法 构建 AI 应用"],
      ["de", "Ideen verbinden KI-Workflows gestalten"],
      ["es", "Conecta ideas Crea flujos de IA"],
      ["fr", "Reliez vos idées Créez des workflows IA"],
      ["ja", "アイデアをつなぐ AI フローをつくる"],
      ["ko", "아이디어를 연결하고 AI 워크플로를 만들어요"],
      ["pt", "Conecte ideias Crie fluxos de IA"],
      ["en", "Connect ideas Build AI workflows"],
    ];

    for (const [locale, heading] of headings) {
      await page.getByRole("combobox").selectOption(locale);
      await expect(page.getByTestId("landing-title")).toHaveText(heading);
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
      const dimensions = await page
        .getByTestId("landing-page")
        .evaluate((el) => ({
          viewport: el.clientWidth,
          content: el.scrollWidth,
        }));
      expect(
        dimensions.content,
        `${locale} horizontal overflow`,
      ).toBeLessThanOrEqual(dimensions.viewport);
    }

    await page.getByRole("button", { name: "Content creation" }).click();
    await expect(
      page.getByText("Write a short introduction for my new idea."),
    ).toBeVisible();
    await page.getByRole("link", { name: "See it flow" }).click();
    await expect(page.locator("#workflow-title")).toBeInViewport();
  },
);

test(
  "workspace entry sends an anonymous visitor through the existing login guard",
  { tag: ["@release", "@workspace"] },
  async ({ page }) => {
    await page.route("**/api/**", (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith("/auto_login")) {
        return route.fulfill({
          status: 403,
          json: {
            detail: { message: "Auto login is disabled.", auto_login: false },
          },
        });
      }
      if (pathname.endsWith("/session")) {
        return route.fulfill({ json: { authenticated: false } });
      }
      if (pathname.endsWith("/flows/basic_examples/")) {
        return route.fulfill({ json: [] });
      }
      if (pathname.endsWith("/version")) {
        return route.fulfill({
          json: { version: "test", package: "langflow", main_version: "test" },
        });
      }
      return route.fulfill({ json: {} });
    });

    await page.goto("/");
    await page
      .getByRole("link", { name: "Open workspace", exact: true })
      .first()
      .click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole("button", { name: /^sign in$/i }),
    ).toBeVisible();
  },
);
