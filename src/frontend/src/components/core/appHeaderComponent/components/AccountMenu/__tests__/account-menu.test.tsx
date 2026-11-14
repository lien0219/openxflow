import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { useUtilityStore } from "@/stores/utilityStore";
import { AccountMenu } from "../index";

const mockNavigate = jest.fn();
let mockImageVersion: string | null = null;

jest.mock("react-icons/fa", () => ({
  FaGithub: () => <span data-testid="github-icon" />,
}));

jest.mock("@/components/common/genericIconComponent", () => ({
  __esModule: true,
  default: () => <span data-testid="icon-component" />,
  ForwardedIconComponent: () => <span data-testid="forwarded-icon-component" />,
}));

jest.mock("@/controllers/API/queries/auth", () => ({
  useLogout: () => ({ mutate: jest.fn() }),
}));

jest.mock(
  "@/customization/components/custom-account-menu-community-links",
  () => ({
    CustomAccountMenuCommunityLinks: () => (
      <div data-testid="custom-account-menu-community-links" />
    ),
  }),
);

jest.mock("@/customization/components/custom-profile-icon", () => ({
  CustomProfileIcon: () => <div data-testid="custom-profile-icon" />,
}));

jest.mock("@/customization/hooks/use-custom-navigate", () => ({
  useCustomNavigate: () => mockNavigate,
}));

jest.mock("@/customization/feature-flags", () => ({
  ENABLE_DATASTAX_LANGFLOW: false,
  ENABLE_EXTERNAL_LINKS: false,
}));

jest.mock("@/stores/authStore", () => ({
  __esModule: true,
  default: (selector: (state: { autoLogin: boolean }) => unknown) =>
    selector({ autoLogin: false }),
}));

jest.mock("@/stores/darkStore", () => ({
  useDarkStore: (
    selector: (state: {
      version: string;
      latestVersion: string;
      imageVersion: string | null;
    }) => unknown,
  ) =>
    selector({
      version: "1.0.0",
      latestVersion: "1.0.0",
      imageVersion: mockImageVersion,
    }),
}));

jest.mock("../../HeaderMenu/index", () => ({
  HeaderMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  HeaderMenuToggle: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  HeaderMenuItems: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  HeaderMenuItemButton: ({
    children,
    onClick,
  }: {
    children: ReactNode;
    onClick?: () => void;
  }) => <button onClick={onClick}>{children}</button>,
  HeaderMenuItemLink: ({
    children,
    href,
  }: {
    children: ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

jest.mock("../../ThemeButtons/index", () => ({
  __esModule: true,
  default: () => <div data-testid="theme-buttons" />,
}));

describe("AccountMenu", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockImageVersion = null;
    act(() => {
      useUtilityStore.setState({ hideLogoutButton: false });
    });
  });

  afterEach(() => {
    act(() => {
      useUtilityStore.setState({ hideLogoutButton: false });
    });
  });

  it("shows logout when hideLogoutButton is false", () => {
    render(<AccountMenu />);

    expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
  });

  it("shows the image version without comparing it to the upstream package", () => {
    mockImageVersion = "0.4.2";
    render(<AccountMenu />);

    expect(screen.getByText("0.4.2")).toBeInTheDocument();
    expect(screen.queryByText(/1\.0\.0/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/latest|update available/i),
    ).not.toBeInTheDocument();
  });

  it("falls back to the package version when image metadata is unavailable", () => {
    render(<AccountMenu />);

    expect(screen.getByText(/1\.0\.0/)).toBeInTheDocument();
    expect(screen.getByText(/latest/i)).toBeInTheDocument();
  });

  it("hides logout when hideLogoutButton is true", () => {
    act(() => {
      useUtilityStore.setState({ hideLogoutButton: true });
    });

    render(<AccountMenu />);

    expect(
      screen.queryByRole("button", { name: /logout/i }),
    ).not.toBeInTheDocument();
  });

  it("hides the external documentation link", () => {
    render(<AccountMenu />);

    expect(screen.queryByTestId("menu_docs_button")).not.toBeInTheDocument();
  });

  it("keeps settings navigation in the OSS account menu", () => {
    render(<AccountMenu />);

    fireEvent.click(screen.getByRole("button", { name: /settings/i }));

    expect(mockNavigate).toHaveBeenCalledWith("/settings");
  });

  it("renders the community links through the customization seam", () => {
    render(<AccountMenu />);

    expect(
      screen.getByTestId("custom-account-menu-community-links"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("menu_github_button")).not.toBeInTheDocument();
  });
});
