import { fireEvent, render, screen } from "@testing-library/react";
import { EmptyPageCommunity } from "../empty-page";

interface ButtonProps {
  children?: React.ReactNode;
  onClick?: () => void;
  "data-testid"?: string;
  unstyled?: boolean;
  [key: string]: unknown;
}

interface IconProps {
  name: string;
  [key: string]: unknown;
}

interface WrapperProps {
  children: React.ReactNode;
  [key: string]: unknown;
}

// startNewFlow mock shared across the suite so assertions can inspect it.
const startNewFlowMock = jest.fn();
const uploadFlowMock = jest.fn().mockResolvedValue(undefined);

jest.mock(
  "@/components/core/flowBuilderWelcome/hooks/use-start-new-flow",
  () => ({
    useStartNewFlow: () => startNewFlowMock,
  }),
);

jest.mock("@/hooks/flows/use-upload-flow", () => ({
  __esModule: true,
  default: () => uploadFlowMock,
}));

jest.mock("@/assets/logo_dark.png", () => "logo_dark.png");
jest.mock("@/assets/logo_light.png", () => "logo_light.png");

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
  initReactI18next: { type: "3rdParty", init: jest.fn() },
}));

jest.mock("react-icons/fa", () => ({
  FaGithub: () => <div data-testid="icon-github" />,
}));

jest.mock("@/components/common/genericIconComponent", () => ({
  ForwardedIconComponent: ({ name }: IconProps) => (
    <div data-testid={`icon-${name}`}>{name}</div>
  ),
}));

jest.mock("@/components/core/cardsWrapComponent", () => ({
  __esModule: true,
  default: ({ children }: WrapperProps) => <div>{children}</div>,
}));

jest.mock("@/components/ui/dot-background", () => ({
  DotBackgroundDemo: ({ children }: WrapperProps) => <div>{children}</div>,
}));

jest.mock("@/components/ui/button", () => ({
  Button: ({
    children,
    onClick,
    "data-testid": testId,
    unstyled: _unstyled,
    ...props
  }: ButtonProps) => (
    <button onClick={onClick} data-testid={testId} {...props}>
      {children}
    </button>
  ),
}));

jest.mock("@/stores/alertStore", () => ({
  __esModule: true,
  default: (
    selector: (s: {
      setSuccessData: jest.Mock;
      setErrorData: jest.Mock;
    }) => unknown,
  ) => selector({ setSuccessData: jest.fn(), setErrorData: jest.fn() }),
}));

jest.mock("@/stores/flowsManagerStore", () => ({
  __esModule: true,
  default: (selector: (s: { examples: unknown[] }) => unknown) =>
    selector({ examples: [] }),
}));

jest.mock("@/stores/utilityStore", () => ({
  useUtilityStore: (
    selector: (s: { hideStarterProjects: boolean }) => unknown,
  ) => selector({ hideStarterProjects: false }),
}));

jest.mock("../../hooks/use-on-file-drop", () => ({
  __esModule: true,
  default: () => jest.fn(),
}));

describe("EmptyPageCommunity - Create first flow behavior", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("should_start_new_flow_when_create_first_flow_clicked", () => {
    const setOpenModal = jest.fn();
    render(<EmptyPageCommunity setOpenModal={setOpenModal} />);

    fireEvent.click(screen.getByTestId("new_project_btn_empty_page"));

    // Empty-state button must open the new Langflow Assistant welcome flow,
    // matching the "New Flow" button shown when the user already has flows.
    expect(startNewFlowMock).toHaveBeenCalledTimes(1);
    // It must NOT open the old TemplatesModal.
    expect(setOpenModal).not.toHaveBeenCalled();
    expect(
      screen.queryByTestId("empty_page_discord_button"),
    ).not.toBeInTheDocument();
  });

  it("should_open_existing_file_picker_when_import_flow_clicked", () => {
    render(<EmptyPageCommunity setOpenModal={jest.fn()} />);

    fireEvent.click(screen.getByTestId("empty_page_import_flow_button"));

    expect(uploadFlowMock).toHaveBeenCalledWith({});
  });
});
