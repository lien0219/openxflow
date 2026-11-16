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
    swatch: "linear-gradient(135deg, #312e81, #7c3aed 58%, #22d3ee)",
  },
  {
    id: "polar",
    label: "Polar Studio",
    shortLabel: { en: "Polar", zh: "极地" },
    swatch: "linear-gradient(135deg, #f8fafc, #bfdbfe 58%, #38bdf8)",
  },
  {
    id: "terminal",
    label: "Terminal Ops",
    shortLabel: { en: "Terminal", zh: "终端" },
    swatch: "linear-gradient(135deg, #111827, #065f46 62%, #4ade80)",
  },
  {
    id: "bloom",
    label: "Bloom Studio",
    shortLabel: { en: "Bloom", zh: "暖曦" },
    swatch: "linear-gradient(135deg, #fff7ed, #fb7185 55%, #c084fc)",
  },
  {
    id: "aurora",
    label: "Aurora Glass",
    shortLabel: { en: "Aurora", zh: "极光" },
    swatch: "linear-gradient(135deg, #172554, #8b5cf6 52%, #22d3ee)",
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
                "group relative flex min-w-0 items-center gap-2 rounded-lg border p-2.5 text-left transition-colors",
                selected
                  ? "border-primary/70 bg-accent shadow-sm"
                  : "border-control bg-card hover:border-primary/50 hover:bg-accent/50",
              )}
              aria-pressed={selected}
              data-testid={`theme_preset_${preset.id}`}
            >
              <span
                className="block h-9 w-9 shrink-0 rounded-md border border-border shadow-inner"
                style={{ background: preset.swatch }}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1 pr-2">
                <span className="block break-words text-xs font-semibold leading-4 text-foreground">
                  {preset.label}
                </span>
                <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                  {isChinese ? preset.shortLabel.zh : preset.shortLabel.en}
                </span>
              </span>
              {selected && (
                <span
                  className="absolute right-1.5 top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-primary text-primary-foreground"
                  aria-hidden="true"
                >
                  <ForwardedIconComponent
                    name="Check"
                    className="h-2.5 w-2.5"
                    strokeWidth={2.5}
                  />
                </span>
              )}
            </Button>
          );
        })}
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
          <span>{isChinese ? "外观模式" : "Appearance"}</span>
          {appearanceDisabled && (
            <span>{isChinese ? "跟随主题" : "Preset controlled"}</span>
          )}
        </div>
        <div
          className={cn(
            "grid grid-cols-3 gap-1 rounded-lg border border-control bg-muted/55 p-1",
            appearanceDisabled && "cursor-not-allowed opacity-55",
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
                  "flex h-9 min-w-0 items-center justify-center gap-1 rounded-md px-1.5 text-xs transition-colors",
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
                  className="h-3.5 w-3.5 shrink-0"
                  strokeWidth={2}
                />
                <span className="whitespace-nowrap">{label}</span>
              </Button>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default ThemeButtons;
