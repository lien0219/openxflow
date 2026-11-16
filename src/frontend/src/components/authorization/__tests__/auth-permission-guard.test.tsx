import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ProtectedPermissionRoute } from "../authPermissionGuard";

const mockUseRbacAccess = jest.fn();

jest.mock("@/hooks/use-rbac-access", () => ({
  useRbacAccess: () => mockUseRbacAccess(),
}));

jest.mock("@/pages/LoadingPage", () => ({
  LoadingPage: () => <p>Checking permissions</p>,
}));

function renderPermissionsRoute() {
  return render(
    <MemoryRouter initialEntries={["/settings/permissions"]}>
      <Routes>
        <Route path="/" element={<p>Public homepage</p>} />
        <Route path="/flows" element={<p>Workspace</p>} />
        <Route
          path="/settings/permissions"
          element={
            <ProtectedPermissionRoute>
              <p>Permissions panel</p>
            </ProtectedPermissionRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Permissions route", () => {
  it("returns users without access to their workspace", () => {
    mockUseRbacAccess.mockReturnValue({ canReadRbac: false, isLoading: false });
    renderPermissionsRoute();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });

  it("keeps users with access on the permissions page", () => {
    mockUseRbacAccess.mockReturnValue({ canReadRbac: true, isLoading: false });
    renderPermissionsRoute();
    expect(screen.getByText("Permissions panel")).toBeInTheDocument();
  });

  it("waits for permissions before choosing a destination", () => {
    mockUseRbacAccess.mockReturnValue({ canReadRbac: false, isLoading: true });
    renderPermissionsRoute();
    expect(screen.getByText("Checking permissions")).toBeInTheDocument();
    expect(screen.queryByText("Workspace")).not.toBeInTheDocument();
  });
});
