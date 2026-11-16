import { useTranslation } from "react-i18next";
import { DATASTAX_DOCS_URL, DOCS_URL } from "@/constants/constants";
import { useLogout } from "@/controllers/API/queries/auth";
import { CustomAccountMenuCommunityLinks } from "@/customization/components/custom-account-menu-community-links";
import { CustomAccountMenuNavigationItems } from "@/customization/components/custom-account-menu-navigation-items";
import { CustomHeaderMenuItemsTitle } from "@/customization/components/custom-header-menu-items-title";
import { CustomProfileIcon } from "@/customization/components/custom-profile-icon";
import {
  ENABLE_DATASTAX_LANGFLOW,
  ENABLE_EXTERNAL_LINKS,
} from "@/customization/feature-flags";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import useAuthStore from "@/stores/authStore";
import { useDarkStore } from "@/stores/darkStore";
import { useUtilityStore } from "@/stores/utilityStore";
import { cn, stripReleaseStageFromVersion } from "@/utils/utils";
import {
  HeaderMenu,
  HeaderMenuItemButton,
  HeaderMenuItemLink,
  HeaderMenuItems,
  HeaderMenuToggle,
} from "../HeaderMenu";
import ThemeButtons from "../ThemeButtons";

export const AccountMenu = () => {
  const { t } = useTranslation();
  const version = useDarkStore((state) => state.version);
  const imageVersion = useDarkStore((state) => state.imageVersion);
  const latestVersion = useDarkStore((state) => state.latestVersion);
  const displayVersion = imageVersion || version;
  const showPackageStatus = !imageVersion && Boolean(version && latestVersion);
  const navigate = useCustomNavigate();
  const { mutate: mutationLogout } = useLogout();
  const hideLogoutButton = useUtilityStore((state) => state.hideLogoutButton);
  const autoLogin = useAuthStore((state) => state.autoLogin);

  const handleLogout = () => {
    mutationLogout();
  };

  const isLatestVersion = (() => {
    if (!version || !latestVersion) return false;

    const currentBaseVersion = stripReleaseStageFromVersion(version);
    const latestBaseVersion = stripReleaseStageFromVersion(latestVersion);

    return currentBaseVersion === latestBaseVersion;
  })();

  return (
    <HeaderMenu>
      <HeaderMenuToggle>
        <div
          className="h-6 w-6 rounded-lg focus-visible:outline-0"
          data-testid="user-profile-settings"
        >
          <CustomProfileIcon />
        </div>
      </HeaderMenuToggle>
      <HeaderMenuItems
        position="right"
        classNameSize="w-[360px] max-w-[calc(100vw-1rem)] max-h-[calc(100dvh-5rem)] overflow-y-auto"
      >
        <div className="divide-y divide-foreground/10">
          <CustomHeaderMenuItemsTitle />
          <div>
            <div className="px-4 py-3">
              <div className="flex items-start justify-between gap-4">
                <span
                  data-testid="menu_version_button"
                  id="menu_version_button"
                  className="shrink-0 text-sm"
                >
                  {t("account.version")}
                </span>
                <div
                  className={cn(
                    "min-w-0 break-words text-right text-xs",
                    showPackageStatus &&
                      (isLatestVersion
                        ? "text-accent-emerald-foreground"
                        : "text-accent-amber-foreground"),
                  )}
                  title={displayVersion}
                >
                  {displayVersion}
                  {showPackageStatus && (
                    <>
                      {" "}
                      {isLatestVersion
                        ? t("account.latest")
                        : t("account.updateAvailable")}
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div>
            <CustomAccountMenuNavigationItems
              onNavigate={(path) => navigate(path)}
            />
            {ENABLE_EXTERNAL_LINKS && (
              <HeaderMenuItemLink
                newPage
                href={ENABLE_DATASTAX_LANGFLOW ? DATASTAX_DOCS_URL : DOCS_URL}
              >
                <span data-testid="menu_docs_button" id="menu_docs_button">
                  {t("account.docs")}
                </span>
              </HeaderMenuItemLink>
            )}
          </div>

          <CustomAccountMenuCommunityLinks />

          <div className="space-y-3 px-4 py-4 text-sm">
            <div className="font-medium">{t("account.theme")}</div>
            <ThemeButtons />
          </div>

          {!autoLogin && !hideLogoutButton && (
            <div>
              <HeaderMenuItemButton onClick={handleLogout} icon="log-out">
                {t("account.logout")}
              </HeaderMenuItemButton>
            </div>
          )}
        </div>
      </HeaderMenuItems>
    </HeaderMenu>
  );
};
