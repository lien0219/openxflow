import { render, screen } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import ExpiryDateCellRender from "../index";

jest.mock("@/components/core/dateReaderComponent", () => ({
  __esModule: true,
  default: ({ date }: { date: string }) => (
    <span data-testid="date-reader">{date}</span>
  ),
}));

const renderWithProvider = (ui: React.ReactElement) =>
  render(<TooltipProvider>{ui}</TooltipProvider>);

describe("ExpiryDateCellRender", () => {
  it("renders DateReader when a date value is provided", () => {
    renderWithProvider(<ExpiryDateCellRender value="2025-06-01T00:00:00Z" />);
    expect(screen.getByTestId("date-reader")).toBeInTheDocument();
    expect(screen.getByTestId("date-reader")).toHaveTextContent(
      "2025-06-01T00:00:00Z",
    );
  });

  it("renders infinity symbol when value is null", () => {
    renderWithProvider(<ExpiryDateCellRender value={null} />);
    expect(screen.getByText("∞")).toBeInTheDocument();
    expect(screen.queryByTestId("date-reader")).not.toBeInTheDocument();
  });

  it("renders infinity symbol when value is undefined", () => {
    renderWithProvider(<ExpiryDateCellRender value={undefined} />);
    expect(screen.getByText("∞")).toBeInTheDocument();
    expect(screen.queryByTestId("date-reader")).not.toBeInTheDocument();
  });

  it("renders infinity symbol when value is an empty string", () => {
    renderWithProvider(<ExpiryDateCellRender value="" />);
    expect(screen.getByText("∞")).toBeInTheDocument();
  });
});
