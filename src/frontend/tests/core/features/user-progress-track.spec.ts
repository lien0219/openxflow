import { Page } from "playwright/test";
import { expect, test } from "../../fixtures";
import { addNewUserAndLogin } from "../../utils/add-new-user-and-loggin";
import { cleanAllFlows } from "../../utils/clean-all-flows";
import { cleanOldFolders } from "../../utils/clean-old-folders";
import { openTemplatesModal } from "../../utils/flow/new-project-flow";

test(
  "admin user can use the empty-state getting-started actions",
  { tag: ["@release", "@api"] },
  async ({ page }) => {
    await page.goto("/");
    await gettingStartedActionsTestFn(page);
  },
);

test(
  "normal user can use the empty-state getting-started actions",
  { tag: ["@release", "@api"] },
  async ({ page }) => {
    await addNewUserAndLogin(page);
    await gettingStartedActionsTestFn(page);
  },
);

async function gettingStartedActionsTestFn(page: Page) {
  // Wait for any loading text to disappear
  await page.waitForSelector('text="Loading"', {
    state: "hidden",
    timeout: 30000,
  });

  await cleanAllFlows(page);
  await cleanOldFolders(page);

  await expect(page.getByTestId("new_project_btn_empty_page")).toBeVisible();
  await expect(page.getByTestId("mainpage_title").last()).toBeVisible();
  await expect(page.getByTestId("empty_page_description")).toBeVisible();
  await expect(page.getByTestId("empty_page_github_button")).toHaveCount(0);
  await expect(page.getByTestId("empty_page_discord_button")).toHaveCount(0);
  await expect(page.getByTestId("empty_page_drag_and_drop_text")).toBeVisible();
  await expect(page.getByTestId("get_started_progress_title")).toHaveCount(0);
  await expect(page.getByTestId("get_started_progress_percentage")).toHaveCount(
    0,
  );

  // OpenXFlow's current empty state uses direct actions rather than the legacy
  // percentage progress widget. Exercise the create-flow action itself.
  await openTemplatesModal(page, { fromEmptyPage: true });
  await page.waitForSelector('[data-testid="blank-flow"]', {
    timeout: 30000,
  });
  await page.getByTestId("blank-flow").click();
  await page.waitForSelector('[data-testid="canvas_controls_dropdown"]', {
    timeout: 100000,
  });

  await page.getByTestId("icon-ChevronLeft").first().click();
  await page.waitForSelector('[data-testid="home-dropdown-menu"]', {
    timeout: 100000,
  });

  // Creating a flow completes the local checklist; social steps are hidden.
  await expect(page.getByTestId("get_started_progress_percentage")).toHaveText(
    "100%",
  );
  await expect(page.getByTestId("search-store-input")).toBeVisible();

  await cleanAllFlows(page);

  await expect(page.getByTestId("new_project_btn_empty_page")).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByTestId("get_started_progress_title")).toHaveCount(0);
  await expect(page.getByTestId("github_starred_icon_get_started")).toHaveCount(
    0,
  );
  await expect(page.getByTestId("create_flow_icon_get_started")).toHaveCount(0);
  await expect(page.getByTestId("discord_joined_icon_get_started")).toHaveCount(
    0,
  );
}
