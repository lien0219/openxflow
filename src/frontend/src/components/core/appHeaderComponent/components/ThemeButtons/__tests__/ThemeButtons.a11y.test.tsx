import { render, screen } from "@testing-library/react";
import { axe } from "@/utils/a11y-test";
import { ThemeButtons } from "..";

describe("ThemeButtons accessibility", () => {
  it("has no detectable axe violations", async () => {
    const { container } = render(<ThemeButtons />);

    const results = await axe(container);

    expect(results).toHaveNoViolations();
  });

  it("names the theme presets and appearance buttons", () => {
    render(<ThemeButtons />);

    expect(
      screen.getByRole("button", { name: /OpenXFlow Classic/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Nebula Forge/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Light" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dark" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "System" })).toBeInTheDocument();
  });
});
