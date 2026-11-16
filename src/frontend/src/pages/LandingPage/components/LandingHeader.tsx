import { useTranslation } from "react-i18next";
import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import Icon from "@/components/common/genericIconComponent";
import { CustomLink } from "@/customization/components/custom-link";
import useTheme from "@/customization/hooks/use-custom-theme";
import { useLandingMotion } from "../hooks/use-landing-motion";

export default function LandingHeader({
  compact,
  activeSection,
  onNavigate,
}: {
  compact: boolean;
  activeSection: string;
  onNavigate: (id: string) => void;
}) {
  const { t } = useTranslation();
  const { paused, reducedMotion, togglePaused } = useLandingMotion();
  const { dark, themePreset, setThemePreset, setThemePreference } = useTheme();
  const isDark =
    themePreset === "classic"
      ? dark
      : ["nebula", "terminal", "aurora"].includes(themePreset);
  const themeLabel = t(
    isDark ? "landing.switchToLight" : "landing.switchToDark",
  );
  const toggleTheme = () => {
    // App fixes the appearance of nonclassic presets; explicit light/dark
    // selection returns to the adaptive preset before changing preference.
    if (themePreset !== "classic") setThemePreset("classic");
    setThemePreference(isDark ? "light" : "dark");
  };
  return (
    <div className="landing-header-position">
      <header
        className="landing-header landing-glass"
        data-testid="landing-header"
        data-compact={compact}
      >
        <a
          href="#main-content"
          className="landing-brand"
          aria-label="OpenXFlow"
        >
          <span className="landing-brand-mark">
            <LangflowLogo aria-hidden="true" />
          </span>
          <span className="landing-brand-name" aria-hidden="true">
            OpenXFlow
          </span>
        </a>
        <nav className="landing-nav" aria-label={t("landing.navigation")}>
          {[
            { id: "main-content", label: "landing.overviewNav" },
            { id: "workflow", label: "landing.workflowNav" },
            { id: "capabilities", label: "landing.capabilitiesNav" },
          ].map(({ id, label }) => (
            <a
              key={id}
              href={`#${id}`}
              aria-current={activeSection === id ? "location" : undefined}
              onClick={(event) => {
                if (
                  !event.metaKey &&
                  !event.ctrlKey &&
                  !event.shiftKey &&
                  !event.altKey
                )
                  onNavigate(id);
              }}
            >
              {t(label)}
            </a>
          ))}
        </nav>
        <div className="landing-header-actions">
          {!reducedMotion && (
            <button
              type="button"
              className="landing-theme-toggle landing-motion-toggle"
              onClick={togglePaused}
              aria-pressed={paused}
              aria-label={t(
                paused ? "landing.resumeAnimations" : "landing.pauseAnimations",
              )}
              title={t(
                paused ? "landing.resumeAnimations" : "landing.pauseAnimations",
              )}
            >
              <Icon name={paused ? "Play" : "Pause"} aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            className="landing-theme-toggle"
            data-testid="landing-theme-toggle"
            onClick={toggleTheme}
            aria-label={themeLabel}
            title={themeLabel}
            aria-pressed={isDark}
          >
            <span
              key={isDark ? "dark" : "light"}
              className="landing-theme-icon"
            >
              <Icon name={isDark ? "Sun" : "Moon"} aria-hidden="true" />
            </span>
          </button>
          <CustomLink to="/flows" className="landing-button landing-header-cta">
            {t("landing.openWorkspace")}
            <Icon name="ArrowUpRight" aria-hidden="true" />
          </CustomLink>
        </div>
      </header>
    </div>
  );
}
