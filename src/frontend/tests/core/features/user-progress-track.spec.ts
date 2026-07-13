import { BrowserContext, Page } from "playwright/test";
import { GITHUB_URL } from "../../../src/constants/constants";
import { expect, test } from "../../fixtures";
import { addNewUserAndLogin } from "../../utils/add-new-user-and-loggin";
import { cleanAllFlows } from "../../utils/clean-all-flows";
import { cleanOldFolders } from "../../utils/clean-old-folders";

import { TEXTS } from "../../utils/constants/texts";
import { openTemplatesModal } from "../../utils/flow/new-project-flow";

test(
  "admin user must be able to track their progress in getting started",
  { tag: ["@release", "@api"] },
  async ({ page, context }) => {
    await page.goto("/");
    await progressTrackTestFn(page, context);
  },
);

test(
  "normal user must be able to track their progress in getting started",
  { tag: ["@release", "@api"] },
  async ({ page, context }) => {
    await addNewUserAndLogin(page);
    await progressTrackTestFn(page, context);
  },
);

async function progressTrackTestFn(page: Page, context: BrowserContext) {
  // Wait for any loading text to disappear
  await page.waitForSelector('text="Loading"', {
    state: "hidden",
    timeout: 30000,
  });

  await page.waitForTimeout(2000);

  await cleanAllFlows(page);
  await cleanOldFolders(page);

  await expect(page.getByTestId("new_project_btn_empty_page")).toBeVisible();
  await expect(page.getByTestId("mainpage_title").last()).toBeVisible();
  await expect(page.getByTestId("empty_page_description")).toBeVisible();
  await expect(page.getByTestId("empty_page_github_button")).toBeVisible();
  await expect(page.getByTestId("empty_page_discord_button")).toHaveCount(0);
  await expect(page.getByTestId("empty_page_drag_and_drop_text")).toBeVisible();
  await expect(
    page.getByTestId("get_started_progress_title"),
  ).not.toBeVisible();

  await page.getByTestId("empty_page_github_button").click();

  const pagePromiseGithub = context.waitForEvent("page");

  const newPageGithub = await pagePromiseGithub;
  await newPageGithub.waitForTimeout(3000);
  const newUrlGithub = newPageGithub.url();

  await expect(newUrlGithub).toContain(GITHUB_URL);

  await newPageGithub.close();

  await expect(page.getByTestId("mainpage_title")).toBeVisible();
  await expect(page.getByTestId("empty_page_description")).toBeVisible();

  await openTemplatesModal(page, { fromEmptyPage: true });

  await page.getByTestId("side_nav_options_all-templates").click();
  await page
    .getByRole("heading", { name: TEXTS.templateBasicPrompting })
    .click();

  await page.waitForSelector('[data-testid="sidebar-search-input"]', {
    timeout: 100000,
  });

  await page.getByTestId("icon-ChevronLeft").first().click();

  await page.waitForSelector('[data-testid="home-dropdown-menu"]', {
    timeout: 100000,
  });

  await expect(
    page.getByTestId("get_started_progress_percentage").first(),
  ).toHaveText("100%");

  await cleanAllFlows(page);

  await expect(
    page.getByTestId("get_started_progress_title"),
  ).not.toBeVisible();
  await expect(
    page.getByTestId("github_starred_icon_get_started"),
  ).not.toBeVisible();
  await expect(
    page.getByTestId("create_flow_icon_get_started"),
  ).not.toBeVisible();
  await expect(page.getByTestId("discord_joined_icon_get_started")).toHaveCount(
    0,
  );
}
