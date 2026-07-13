import { fireEvent, render, screen } from "@testing-library/react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import HelpDropdown from "../HelpDropdown";

jest.mock("@/components/ui/button", () => ({
  Button: ({
    children,
    ...props
  }: ButtonHTMLAttributes<HTMLButtonElement> & { children?: ReactNode }) => (
    <button {...props}>{children}</button>
  ),
}));

jest.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({
    children,
    ...props
  }: HTMLAttributes<HTMLDivElement> & { children?: ReactNode }) => (
    <div data-testid="dropdown-menu" {...props}>
      {children}
    </div>
  ),
  DropdownMenuTrigger: ({
    children,
    ...props
  }: HTMLAttributes<HTMLDivElement> & { children?: ReactNode }) => (
    <div data-testid="dropdown-trigger" {...props}>
      {children}
    </div>
  ),
  DropdownMenuContent: ({
    children,
    ...props
  }: HTMLAttributes<HTMLDivElement> & { children?: ReactNode }) => (
    <div data-testid="dropdown-content" {...props}>
      {children}
    </div>
  ),
}));

jest.mock("@/components/ui/separator", () => ({
  Separator: () => <div data-testid="separator" />,
}));

jest.mock("@/components/common/genericIconComponent", () => ({
  __esModule: true,
  default: () => <span data-testid="icon" />,
  ForwardedIconComponent: ({ name }: { name: string }) => (
    <span data-testid={`icon-${name}`} />
  ),
}));

jest.mock("@/constants/constants", () => ({
  __esModule: true,
  BUG_REPORT_URL: "https://github.com/lien0219/openxflow/issues",
  DATASTAX_DOCS_URL: "https://docs.datastax.com",
  DOCS_URL: "https://github.com/lien0219/openxflow#readme",
}));

jest.mock("@/customization/feature-flags", () => ({
  ENABLE_DATASTAX_LANGFLOW: false,
}));

jest.mock("@/utils/utils", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
  getOS: () => "macos",
}));

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    useNavigate: jest.fn(),
  };
});

jest.mock("@/stores/darkStore", () => ({
  useDarkStore: () => ({
    dark: false,
    setDark: jest.fn(),
  }),
}));

jest.mock("@/stores/flowStore", () => ({
  __esModule: true,
  default: () => ({
    helperLineEnabled: false,
    setHelperLineEnabled: jest.fn(),
  }),
}));

// Mock window.open
Object.defineProperty(window, "open", {
  writable: true,
  value: jest.fn(),
});

describe("HelpDropdown", () => {
  beforeEach(() => {
    (window.open as jest.Mock).mockClear();
  });

  it("opens docs in new tab and navigates to shortcuts", () => {
    const mockNavigate = jest.fn();
    (useNavigate as unknown as jest.Mock).mockReturnValue(mockNavigate);

    render(
      <MemoryRouter>
        <HelpDropdown isOpen={true} onOpenChange={() => {}} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("canvas_controls_dropdown_docs"));
    expect(window.open).toHaveBeenCalledWith(
      "https://github.com/lien0219/openxflow#readme",
      "_blank",
    );

    fireEvent.click(screen.getByTestId("canvas_controls_dropdown_shortcuts"));
    expect(mockNavigate).toHaveBeenCalledWith("/settings/shortcuts");
  });
});
