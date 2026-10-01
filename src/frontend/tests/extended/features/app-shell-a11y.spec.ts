import { expect, test } from "../../fixtures";
import { awaitBootstrapTest } from "../../utils/await-bootstrap-test";
import { TIMEOUTS } from "../../utils/constants/timeouts";

/**
 * App-shell accessibility regression tests.
 *
 * WCAG 2.4.2 Page Titled — every route must set a `document.title` that names
 *   the page, so routes are distinguishable in tabs, history and AT window lists.
 * WCAG 3.1.1 Language of Page — `<html lang>` must track the selected i18n locale.
 * WCAG 2.4.1 Bypass Blocks — exactly one `<main>` landmark per route, including
 *   while a modal is open (a nested `<main>` breaks landmark navigation).
 *
 * Before the app-shell fix all three fail: every route rendered the generic
 * product title, `lang` stayed `en` for every locale, and the templates
 * modal added a second `<main>` on top of the page's own.
 */

/**
 * Expected titles are exact so the test also catches a route silently
 * inheriting the previous route's title. Settings entries whose label already
 * carries the product name are not double-branded.
 *
 * `/components` is deliberately absent: with MCP enabled (the default) it has
 * no Components tab and force-selects Flows, so it is the same page as `/flows`
 * and correctly shares its title. The home page titles itself after the active
 * header tab, which the Deployments test below covers.
 */
const ROUTE_TITLES = [
  { path: "/flows", title: "Flows | OpenXFlow" },
  { path: "/mcp", title: "MCP Server | OpenXFlow" },
  { path: "/assets/files", title: "Files | OpenXFlow" },
  { path: "/assets/knowledge-bases", title: "Knowledge | OpenXFlow" },
  { path: "/settings/general", title: "General | OpenXFlow" },
  { path: "/settings/global-variables", title: "Global Variables | OpenXFlow" },
  { path: "/settings/api-keys", title: "OpenXFlow API Keys" },
  { path: "/settings/mcp-servers", title: "MCP Servers | OpenXFlow" },
  { path: "/settings/shortcuts", title: "Shortcuts | OpenXFlow" },
  { path: "/settings/messages", title: "Messages | OpenXFlow" },
] as const;

test(
  "every route sets a document title that names the page",
  { tag: ["@release", "@workspace"] },
  async ({ page }) => {
    await awaitBootstrapTest(page, { skipModal: true });

    const observed: string[] = [];
    for (const route of ROUTE_TITLES) {
      await page.goto(route.path);
      await expect(page).toHaveURL(new RegExp(`${route.path}/?$`), {
        timeout: TIMEOUTS.standard,
      });
      await expect(page).toHaveTitle(route.title, {
        timeout: TIMEOUTS.standard,
      });
      observed.push(await page.title());
    }

    // A per-route title is only useful if it actually distinguishes the route.
    expect(new Set(observed).size).toBe(ROUTE_TITLES.length);
  },
);

test(
  "switching to the Deployments tab retitles the page without a route change",
  { tag: ["@release", "@workspace"] },
  async ({ page }) => {
    await page.route("**/api/v1/config*", async (route) => {
      const response = await route.fetch();
      const config = await response.json();
      await route.fulfill({
        response,
        json: {
          ...config,
          feature_flags: {
            ...config.feature_flags,
            wxo_deployments: true,
          },
        },
      });
    });
    await awaitBootstrapTest(page, { skipModal: true });
    await page.goto("/flows");
    await expect(page).toHaveTitle("Flows | OpenXFlow", {
      timeout: TIMEOUTS.standard,
    });

    // Flows and Deployments share /flows; only the header tab differs.
    await page.getByTestId("deployments-btn").click();
    await expect(page).toHaveURL(/\/flows\/?$/);
    await expect(page).toHaveTitle("Deployments | OpenXFlow", {
      timeout: TIMEOUTS.standard,
    });

    await page.getByTestId("flows-btn").click();
    await expect(page).toHaveTitle("Flows | OpenXFlow", {
      timeout: TIMEOUTS.standard,
    });
  },
);

test(
  "the flow editor titles the tab with the flow name",
  { tag: ["@release", "@workspace"] },
  async ({ page }) => {
    await awaitBootstrapTest(page, { skipModal: true });
    await page.getByTestId("list-card").first().click();
    await expect(page).toHaveURL(/\/flow\//, { timeout: TIMEOUTS.standard });

    // The header shows a placeholder name until the flow resolves, so poll
    // until the heading and the tab title agree.
    await expect(async () => {
      const flowName = (await page.getByTestId("flow_name").innerText()).trim();
      expect(flowName.length).toBeGreaterThan(0);
      await expect(page).toHaveTitle(`${flowName} | OpenXFlow`, {
        timeout: 2000,
      });
    }).toPass({ timeout: TIMEOUTS.standard });
  },
);

test(
  "the html lang attribute follows the selected locale",
  { tag: ["@release", "@workspace"] },
  async ({ page }) => {
    await awaitBootstrapTest(page, { skipModal: true });
    await page.goto("/settings/general");

    const html = page.locator("html");
    await expect(html).toHaveAttribute("lang", "en");

    await page.getByLabel("Select language").click();
    await page.getByRole("option", { name: "日本語" }).click();
    await expect(html).toHaveAttribute("lang", "ja", {
      timeout: TIMEOUTS.standard,
    });

    // The attribute must survive a reload, since the preference is persisted.
    await page.reload();
    await expect(html).toHaveAttribute("lang", "ja", {
      timeout: TIMEOUTS.standard,
    });
  },
);

test(
  "each route exposes exactly one main landmark",
  { tag: ["@release", "@workspace"] },
  async ({ page }) => {
    await awaitBootstrapTest(page, { skipModal: true });

    for (const route of ROUTE_TITLES) {
      await page.goto(route.path);
      await expect(page).toHaveURL(new RegExp(`${route.path}/?$`), {
        timeout: TIMEOUTS.standard,
      });
      await expect(page.locator("main"), route.path).toHaveCount(1);
    }
  },
);

test(
  "the templates modal does not nest a second main landmark",
  { tag: ["@release", "@workspace"] },
  async ({ page }) => {
    // Opens a new flow and the templates modal on top of the flow canvas,
    // which already owns the page's single <main>.
    await awaitBootstrapTest(page);
    await expect(page.getByTestId("modal-title")).toBeVisible({
      timeout: TIMEOUTS.standard,
    });

    await expect(page.locator("main")).toHaveCount(1);
  },
);
