import { render, screen } from "@testing-library/react";
import { axe } from "@/utils/a11y-test";
import { LangflowCounts } from "../langflow-counts";

type DarkStoreState = {
  stars: number;
};

let mockDarkStoreState: DarkStoreState = {
  stars: 0,
};

jest.mock("@/stores/darkStore", () => ({
  useDarkStore: (selector: (state: DarkStoreState) => unknown) =>
    selector(mockDarkStoreState),
}));

describe("LangflowCounts", () => {
  beforeEach(() => {
    mockDarkStoreState = { stars: 0 };
  });

  it("should_have_no_axe_violations with zero counts", async () => {
    const { container } = render(<LangflowCounts />);

    expect(await axe(container)).toHaveNoViolations();
  });

  it("should_have_no_axe_violations with non-zero counts", async () => {
    mockDarkStoreState = { stars: 42000 };
    const { container } = render(<LangflowCounts />);

    expect(await axe(container)).toHaveNoViolations();
  });

  it("exposes an accessible name for the GitHub link via sr-only text", () => {
    render(<LangflowCounts />);

    expect(
      screen.getByRole("button", { name: "Go to GitHub repo" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /discord/i }),
    ).not.toBeInTheDocument();
  });

  it("hides the numeric star count from the accessibility tree", () => {
    mockDarkStoreState = { stars: 42000 };
    render(<LangflowCounts />);

    const starsCount = screen.getByText("42k");
    expect(starsCount).toHaveAttribute("aria-hidden", "true");
  });
});
