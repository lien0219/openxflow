import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

component = ROOT / "src/frontend/src/components/core/appHeaderComponent/components/ThemeButtons/index.tsx"
component.write_text('''import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import useTheme from "@/customization/hooks/use-custom-theme";
import type { ThemePreference, ThemePreset } from "@/types/theme";
import { cn } from "@/utils/utils";

const PRESETS: Array<{
  id: ThemePreset;
  label: string;
  shortLabelKey: string;
  swatch: string;
}> = [
  { id: "classic", label: "OpenXFlow Classic", shortLabelKey: "theme.preset.classic", swatch: "linear-gradient(135deg, #18181b, #71717a)" },
  { id: "nebula", label: "Nebula Forge", shortLabelKey: "theme.preset.nebula", swatch: "linear-gradient(135deg, #7c3aed, #d946ef 55%, #22d3ee)" },
  { id: "polar", label: "Polar Studio", shortLabelKey: "theme.preset.polar", swatch: "linear-gradient(135deg, #f8fafc, #bfdbfe 55%, #22d3ee)" },
  { id: "terminal", label: "Terminal Ops", shortLabelKey: "theme.preset.terminal", swatch: "linear-gradient(135deg, #050706, #064e3b 60%, #a3e635)" },
  { id: "bloom", label: "Bloom Studio", shortLabelKey: "theme.preset.bloom", swatch: "linear-gradient(135deg, #ffedd5, #fda4af 55%, #a78bfa)" },
  { id: "aurora", label: "Aurora Glass", shortLabelKey: "theme.preset.aurora", swatch: "linear-gradient(135deg, #1e1b4b, #8b5cf6 50%, #67e8f9)" },
];

const APPEARANCE_OPTIONS: Array<{
  id: ThemePreference;
  icon: "Sun" | "Moon" | "Monitor";
  labelKey: string;
}> = [
  { id: "light", icon: "Sun", labelKey: "theme.appearance.light" },
  { id: "dark", icon: "Moon", labelKey: "theme.appearance.dark" },
  { id: "system", icon: "Monitor", labelKey: "theme.appearance.system" },
];

export const ThemeButtons = () => {
  const { t } = useTranslation();
  const { systemTheme, dark, themePreset, setThemePreset, setThemePreference } = useTheme();
  const [selectedAppearance, setSelectedAppearance] = useState<ThemePreference>(
    systemTheme ? "system" : dark ? "dark" : "light",
  );
  const appearanceDisabled = themePreset !== "classic";

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
                  {t(preset.shortLabelKey)}
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
        title={appearanceDisabled ? t("theme.appearance.classicOnly") : undefined}
      >
        {APPEARANCE_OPTIONS.map((option) => {
          const selected = selectedAppearance === option.id;
          const label = t(option.labelKey);
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
              title={appearanceDisabled ? t("theme.appearance.classicOnly") : label}
              aria-label={label}
              aria-pressed={selected}
              data-testid={`menu_${option.id}_button`}
            >
              <ForwardedIconComponent name={option.icon} className="h-3.5 w-3.5" strokeWidth={2} />
              <span className="hidden xl:inline">{label}</span>
            </Button>
          );
        })}
      </div>
    </div>
  );
};

export default ThemeButtons;
''', encoding="utf-8")

account_menu = ROOT / "src/frontend/src/components/core/appHeaderComponent/components/AccountMenu/index.tsx"
text = account_menu.read_text(encoding="utf-8")
text = text.replace("主题风格与外观模式独立设置", '{t("theme.description")}')
account_menu.write_text(text, encoding="utf-8")

home = ROOT / "src/frontend/src/pages/MainPage/pages/homePage/index.tsx"
text = home.read_text(encoding="utf-8")
text = text.replace('        // Folder doesn\'t exist for this user, redirect to /all\n        console.error("Invalid folderId, redirecting to /all");\n        navigate("/all");', '        navigate("/all", { replace: true });')
home.write_text(text, encoding="utf-8")

translations = {
    "en.json": {
        "theme.description": "Only the Classic theme supports appearance switching",
        "theme.preset.classic": "Classic",
        "theme.preset.nebula": "Nebula",
        "theme.preset.polar": "Polar",
        "theme.preset.terminal": "Terminal",
        "theme.preset.bloom": "Bloom",
        "theme.preset.aurora": "Aurora",
        "theme.appearance.light": "Light",
        "theme.appearance.dark": "Dark",
        "theme.appearance.system": "System",
        "theme.appearance.classicOnly": "Appearance switching is available only for the Classic theme",
    },
    "zh-Hans.json": {
        "theme.description": "仅经典主题支持外观切换",
        "theme.preset.classic": "经典",
        "theme.preset.nebula": "星云",
        "theme.preset.polar": "极地",
        "theme.preset.terminal": "终端",
        "theme.preset.bloom": "暖曦",
        "theme.preset.aurora": "极光",
        "theme.appearance.light": "浅色",
        "theme.appearance.dark": "深色",
        "theme.appearance.system": "跟随系统",
        "theme.appearance.classicOnly": "仅经典主题支持外观切换",
    },
}

for filename, additions in translations.items():
    path = ROOT / "src/frontend/src/i18n/locales" / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(additions)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
