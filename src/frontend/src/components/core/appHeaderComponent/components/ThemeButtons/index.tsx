import { useEffect, useState } from "react";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import useTheme from "@/customization/hooks/use-custom-theme";
import type { ThemePreference, ThemePreset } from "@/types/theme";
import { cn } from "@/utils/utils";

const PRESETS: Array<{
  id: ThemePreset;
  label: string;
  description: string;
  swatchClassName: string;
}> = [
  {
    id: "classic",
    label: "OpenXFlow Classic",
    description: "原有经典主题",
    swatchClassName: "bg-gradient-to-br from-zinc-950 to-zinc-500",
  },
  {
    id: "nebula",
    label: "Nebula Forge",
    description: "星云锻造",
    swatchClassName:
      "bg-gradient-to-br from-violet-600 via-fuchsia-500 to-cyan-400",
  },
];

const APPEARANCE_OPTIONS: Array<{
  id: ThemePreference;
  icon: "Sun" | "Moon" | "Monitor";
  label: string;
}> = [
  { id: "light", icon: "Sun", label: "浅色" },
  { id: "dark", icon: "Moon", label: "深色" },
  { id: "system", icon: "Monitor", label: "跟随系统" },
];

export const ThemeButtons = () => {
  const { systemTheme, dark, themePreset, setThemePreset, setThemePreference } =
    useTheme();
  const [selectedAppearance, setSelectedAppearance] = useState<ThemePreference>(
    systemTheme ? "system" : dark ? "dark" : "light",
  );

  useEffect(() => {
    setSelectedAppearance(systemTheme ? "system" : dark ? "dark" : "light");
  }, [systemTheme, dark]);

  const handleAppearanceChange = (appearance: ThemePreference) => {
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
                className={cn(
                  "h-8 w-8 shrink-0 rounded-md border border-white/20 shadow-sm",
                  preset.swatchClassName,
                )}
              />
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium text-foreground">
                  {preset.label}
                </span>
                <span className="block truncate text-[10px] text-muted-foreground">
                  {preset.description}
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

      <div className="grid grid-cols-3 rounded-lg border border-border bg-muted/50 p-1">
        {APPEARANCE_OPTIONS.map((option) => {
          const selected = selectedAppearance === option.id;
          return (
            <Button
              key={option.id}
              unstyled
              type="button"
              onClick={() => handleAppearanceChange(option.id)}
              className={cn(
                "flex h-8 items-center justify-center gap-1 rounded-md px-2 text-xs transition-colors",
                selected
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
              title={option.label}
              aria-label={option.label}
              aria-pressed={selected}
              data-testid={`menu_${option.id}_button`}
            >
              <ForwardedIconComponent
                name={option.icon}
                className="h-3.5 w-3.5"
                strokeWidth={2}
              />
              <span className="hidden xl:inline">{option.label}</span>
            </Button>
          );
        })}
      </div>
    </div>
  );
};

export default ThemeButtons;
