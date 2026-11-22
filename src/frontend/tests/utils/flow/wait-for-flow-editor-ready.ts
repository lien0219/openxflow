import { expect, type Page } from "@playwright/test";
import { TID } from "../constants/testIds";
import { TIMEOUTS } from "../constants/timeouts";

export async function waitForFlowEditorReady(page: Page): Promise<void> {
  await expect(page.getByTestId(TID.modalTitle)).toBeHidden({
    timeout: TIMEOUTS.standard,
  });
  await expect(page.locator("#react-flow-id")).toBeVisible({
    timeout: TIMEOUTS.standard,
  });
  const sidebarSearchInput = page.getByTestId(TID.sidebarSearchInput);
  if (!(await sidebarSearchInput.isVisible().catch(() => false))) {
    const newSidebarComponentsButton = page.locator(
      '[data-sidebar-collapsed-nav-item="components"]',
    );
    if (await newSidebarComponentsButton.isVisible().catch(() => false)) {
      await newSidebarComponentsButton.click();
    } else {
      await page.locator('[data-sidebar="trigger"]').first().click();
    }
  }
  await expect(sidebarSearchInput).toBeVisible({
    timeout: TIMEOUTS.standard,
  });
  await expect(page.getByTestId(TID.flowSidebar)).toHaveAttribute(
    "data-search-hotkey-ready",
    "true",
    { timeout: TIMEOUTS.standard },
  );
  const catalogEntry = page
    .locator('[data-testid$="_draggable"]:visible')
    .first();
  if (!(await catalogEntry.isVisible().catch(() => false))) {
    // Component creation leaves the last search term in the sidebar. Clear it
    // before looking through categories so readiness does not depend on the
    // previous component that a test happened to add.
    await sidebarSearchInput.fill("");

    const categories = page.locator('[data-testid^="disclosure-"]');
    await expect(categories.first()).toBeVisible({
      timeout: TIMEOUTS.standard,
    });

    for (let index = 0; index < (await categories.count()); index += 1) {
      const category = categories.nth(index);
      if (!(await category.isVisible().catch(() => false))) {
        continue;
      }

      if ((await category.getAttribute("aria-expanded")) !== "true") {
        await category.click();
      }

      if (await catalogEntry.isVisible().catch(() => false)) {
        break;
      }
    }
  }
  await expect(catalogEntry).toBeVisible({ timeout: TIMEOUTS.standard });
}
