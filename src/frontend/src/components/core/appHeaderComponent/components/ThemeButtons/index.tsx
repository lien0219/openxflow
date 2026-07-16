import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import useTheme from "@/customization/hooks/use-custom-theme";
import type { ThemePreference, ThemePreset } from "@/types/theme";
import { cn } from "@/utils/utils";

const PRESETS: Array<{
  id: ThemePreset;
  label: string;
  shortLabel: { en: string; zh: string };
  swatch: string;
}> = [
  {
    id: "classic",
    label: "OpenXFlow Classic",
    shortLabel: { en: "Classic", zh: "经典" },
    swatch: "linear-gradient(135deg, #18181b, #71717a)",
  },
  {
    id: "nebula",
    label: "Nebula Forge",
    shortLabel: { en: "Nebula", zh: "星云" },
    swatch: "linear-gradient(135deg, #7c3aed, #d946ef 55%, #22d3ee)",
  },
  {
    id: "polar",
    label: "Polar Studio",
    shortLabel: { en: "Polar", zh: "极地" },
    swatch: "linear-gradient(135deg, #f8fafc, #bfdbfe 55%, #22d3ee)",
  },
  {
    id: "terminal",
    label: "Terminal Ops",
    shortLabel: { en: "Terminal", zh: "终端" },
    swatch: "linear-gradient(135deg, #050706, #064e3b 60%, #a3e635)",
  },
  {
    id: "bloom",
    label: "Bloom Studio",
    shortLabel: { en: "Bloom", zh: "暖曦" },
    swatch: "linear-gradient(135deg, #ffedd5, #fda4af 55%, #a78bfa)",
  },
  {
    id: "aurora",
    label: "Aurora Glass",
    shortLabel: { en: "Aurora", zh: "极光" },
    swatch: "linear-gradient(135deg, #1e1b4b, #8b5cf6 50%, #67e8f9)",
  },
];

const APPEARANCE_OPTIONS: Array<{
  id: ThemePreference;
  icon: "Sun" | "Moon" | "Monitor";
  label: { en: string; zh: string };
}> = [
  { id: "light", icon: "Sun", label: { en: "Light", zh: "浅色" } },
  { id: "dark", icon: "Moon", label: { en: "Dark", zh: "深色" } },
  { id: "system", icon: "Monitor", label: { en: "System", zh: "跟随系统" } },
];

export const ThemeButtons = () => {
  const { i18n } = useTranslation();
  const { systemTheme, dark, themePreset, setThemePreset, setThemePreference } =
    useTheme();
  const [selectedAppearance, setSelectedAppearance] = useState<ThemePreference>(
    systemTheme ? "system" : dark ? "dark" : "light",
  );
  const isChinese = i18n.resolvedLanguage?.startsWith("zh") ?? false;
  const appearanceDisabled = themePreset !== "classic";
  const classicOnlyMessage = isChinese
    ? "仅经典主题支持外观切换"
    : "Appearance switching is available only for the Classic theme";

  useEffect(() => {
    setSelectedAppearance(systemTheme ? "system" : dark ? "dark" : "light");
  }, [systemTheme, dark]);

  const handleAppearanceChange = (appearance: ThemePreference) => {
    if (appearanceDisabled) return;
    setSelectedAppearance(appearance);
    setThemePreference(appearance);
  };

  return (
    <div className="flex w-full flex-col gap-3" data-testid="theme-controls">
      <div className="grid grid-cols-2 gap-2">
        {PRESETS.map((preset) => {
          const selected = themePreset === preset.id;
          return (
            <Button
              key={preset.id}
              unstyled
              type="button"
              onClick={() => setThemePreset(preset.id)}
              className={cn(
                "group relative flex min-h-16 items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition-colors",
                selected
                  ? "border-primary bg-accent text-accent-foreground"
                  : "border-border bg-background hover:bg-accent/70",
              )}
              aria-pressed={selected}
              data-testid={`theme_preset_${preset.id}`}
            >
              <span
                className="h-8 w-8 shrink-0 rounded-md border border-white/20 shadow-sm"
                style={{ background: preset.swatch }}
              />
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium text-foreground">
                  {preset.label}
                </span>
                <span className="block truncate text-[10px] text-muted-foreground">
                  {isChinese ? preset.shortLabel.zh : preset.shortLabel.en}
                </span>
              </span>
              {selected && (
                <ForwardedIconComponent
                  name="Check"
                  className="absolute right-1.5 top-1.5 h-3.5 w-3.5 text-primary"
                  strokeWidth={2.5}
                />
              )}
            </Button>
          );
        })}
      </div>

      <div
        className={cn(
          "grid grid-cols-3 rounded-lg border border-border bg-muted/50 p-1",
          appearanceDisabled && "cursor-not-allowed opacity-50",
        )}
        title={appearanceDisabled ? classicOnlyMessage : undefined}
      >
        {APPEARANCE_OPTIONS.map((option) => {
          const selected = selectedAppearance === option.id;
          const label = isChinese ? option.label.zh : option.label.en;
          return (
            <Button
              key={option.id}
              unstyled
              type="button"
              disabled={appearanceDisabled}
              onClick={() => handleAppearanceChange(option.id)}
              className={cn(
                "flex h-8 items-center justify-center gap-1 rounded-md px-2 text-xs transition-colors",
                appearanceDisabled
                  ? "pointer-events-none text-muted-foreground"
                  : selected
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
              )}
              title={appearanceDisabled ? classicOnlyMessage : label}
              aria-label={label}
              aria-pressed={selected}
              data-testid={`menu_${option.id}_button`}
            >
              <ForwardedIconComponent
                name={option.icon}
                className="h-3.5 w-3.5"
                strokeWidth={2}
              />
              <span className="hidden xl:inline">{label}</span>
            </Button>
          );
        })}
      </div>
    </div>
  );
};

export default ThemeButtons;
