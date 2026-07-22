import { useTranslation } from "react-i18next";
import { FaGithub } from "react-icons/fa";
import { DATASTAX_DOCS_URL, DOCS_URL, GITHUB_URL } from "@/constants/constants";
import { useLogout } from "@/controllers/API/queries/auth";
import { CustomProfileIcon } from "@/customization/components/custom-profile-icon";
import { ENABLE_DATASTAX_LANGFLOW } from "@/customization/feature-flags";
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
  const { t, i18n } = useTranslation();
  const version = useDarkStore((state) => state.version);
  const latestVersion = useDarkStore((state) => state.latestVersion);
  const navigate = useCustomNavigate();
  const { mutate: mutationLogout } = useLogout();
  const hideLogoutButton = useUtilityStore((state) => state.hideLogoutButton);
  const isChinese = i18n.resolvedLanguage?.startsWith("zh") ?? false;

  const { isAdmin, autoLogin } = useAuthStore((state) => ({
    isAdmin: state.isAdmin,
    autoLogin: state.autoLogin,
  }));

  const handleLogout = () => mutationLogout();

  const isLatestVersion = (() => {
    if (!version || !latestVersion) return false;
    return (
      stripReleaseStageFromVersion(version) ===
      stripReleaseStageFromVersion(latestVersion)
    );
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
        classNameSize="w-[400px] max-w-[calc(100vw-24px)]"
      >
        <div
          className="divide-y divide-border/70"
          data-theme-region="account-menu"
        >
          <div className="px-4 py-3">
            <div className="flex items-center justify-between gap-4">
              <span
                className="text-sm font-medium"
                data-testid="menu_version_button"
              >
                {t("account.version")}
              </span>
              <div
                className={cn(
                  "text-xs",
                  isLatestVersion
                    ? "text-accent-emerald-foreground"
                    : "text-accent-amber-foreground",
                )}
              >
                {version}{" "}
                {isLatestVersion
                  ? t("account.latest")
                  : t("account.updateAvailable")}
              </div>
            </div>
          </div>

          <div className="py-1">
            <HeaderMenuItemButton onClick={() => navigate("/settings")}>
              <span data-testid="menu_settings_button">
                {t("account.settings")}
              </span>
            </HeaderMenuItemButton>
            {isAdmin && !autoLogin && (
              <HeaderMenuItemButton onClick={() => navigate("/admin")}>
                <span data-testid="menu_admin_page_button">
                  {t("account.adminPage")}
                </span>
              </HeaderMenuItemButton>
            )}
            <HeaderMenuItemLink
              newPage
              href={ENABLE_DATASTAX_LANGFLOW ? DATASTAX_DOCS_URL : DOCS_URL}
            >
              <span data-testid="menu_docs_button">{t("account.docs")}</span>
            </HeaderMenuItemLink>
          </div>

          <div className="py-1">
            <HeaderMenuItemLink newPage href={GITHUB_URL}>
              <span
                className="flex items-center gap-2"
                data-testid="menu_github_button"
              >
                <FaGithub className="h-4 w-4" />
                {t("account.github")}
              </span>
            </HeaderMenuItemLink>
          </div>

          <section
            className="space-y-3 px-4 py-4"
            aria-labelledby="theme-menu-title"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div
                  id="theme-menu-title"
                  className="text-sm font-semibold text-foreground"
                >
                  {t("account.theme")}
                </div>
                <div className="mt-1 text-xs leading-5 text-muted-foreground">
                  {isChinese
                    ? "选择适合当前工作场景的界面风格"
                    : "Choose a visual style for your workspace"}
                </div>
              </div>
              <span className="rounded-full bg-muted px-2 py-1 text-[10px] font-medium text-muted-foreground">
                6
              </span>
            </div>
            <ThemeButtons />
          </section>

          {!autoLogin && !hideLogoutButton && (
            <div className="py-1">
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
