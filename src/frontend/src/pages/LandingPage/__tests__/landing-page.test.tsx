import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { axe } from "@/utils/a11y-test";
import LandingPage from "..";

jest.mock("@/assets/LangflowLogo.svg?react", () => ({
  __esModule: true,
  default: (props: React.SVGProps<SVGSVGElement>) => <svg {...props} />,
}));

function renderLandingPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Public homepage", () => {
  it("offers workspace entry points and working page sections", () => {
    renderLandingPage();

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Connect ideas Build AI workflows",
      }),
    ).toBeInTheDocument();

    for (const link of screen.getAllByRole("link")) {
      const href = link.getAttribute("href");
      if (href?.startsWith("#")) {
        expect(document.getElementById(href.slice(1))).not.toBeNull();
      } else {
        expect(href).toBe("/flows");
      }
    }

    expect(
      screen.getByRole("link", { name: "Start building" }),
    ).toHaveAttribute("href", "/flows");
  });

  it("switches the illustrative workflow without leaving the page", async () => {
    const user = userEvent.setup();
    renderLandingPage();

    expect(screen.getByText("What can I build with OpenXFlow?")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Content creation" }));

    expect(
      screen.getByRole("button", { name: "Content creation" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: "Knowledge Q&A" }),
    ).toHaveAttribute("aria-pressed", "false");
    expect(
      screen.getByText("Write a short introduction for my new idea."),
    ).toBeVisible();
    expect(
      screen.queryByText("What can I build with OpenXFlow?"),
    ).not.toBeInTheDocument();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = renderLandingPage();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("automatically loops the workflow and preserves pause across scenario changes", async () => {
    jest.useFakeTimers();
    const originalObserver = jest
      .mocked(IntersectionObserver)
      .getMockImplementation();
    jest.mocked(IntersectionObserver).mockImplementation(
      (callback) =>
        ({
          observe: (target: Element) => {
            if (target.matches(".landing-preview, .landing-capability")) {
              callback(
                [{ target, isIntersecting: true } as IntersectionObserverEntry],
                {} as IntersectionObserver,
              );
            }
          },
          unobserve: jest.fn(),
          disconnect: jest.fn(),
        }) as unknown as IntersectionObserver,
    );
    try {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      const { unmount } = renderLandingPage();
      const preview = screen.getByTestId("landing-preview");
      expect(preview).toHaveAttribute("data-motion", "running");
      expect(preview).toHaveAttribute("data-stage", "0");
      act(() => jest.advanceTimersByTime(1500));
      expect(preview).toHaveAttribute("data-stage", "1");
      await user.click(
        screen.getByRole("button", { name: "Pause animations" }),
      );
      expect(preview).toHaveAttribute("data-motion", "paused");
      act(() => jest.advanceTimersByTime(9000));
      expect(preview).toHaveAttribute("data-stage", "1");
      await user.click(
        screen.getByRole("button", { name: "Content creation" }),
      );
      expect(preview).toHaveAttribute("data-stage", "0");
      expect(preview).toHaveAttribute("data-motion", "paused");
      await user.click(
        screen.getByRole("button", { name: "Resume animations" }),
      );
      act(() => jest.advanceTimersByTime(6000));
      expect(preview).toHaveAttribute("data-stage", "0");
      expect(
        screen.getByRole("list", { name: "Workflow" }),
      ).not.toHaveAttribute("aria-live");
      unmount();
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.mocked(IntersectionObserver).mockImplementation(originalObserver!);
      jest.useRealTimers();
    }
  });
});
