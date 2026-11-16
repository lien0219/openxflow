import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import useAuthStore from "@/stores/authStore";
import { ProtectedLoginRoute } from "..";

function renderLoginRoute(initialEntry = "/login") {
  window.history.replaceState(null, "", initialEntry);
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/login"
          element={
            <ProtectedLoginRoute>
              <p>Login form</p>
            </ProtectedLoginRoute>
          }
        />
        <Route path="/flows" element={<p>Workspace</p>} />
        <Route path="/flow/example" element={<p>Requested flow</p>} />
        <Route path="*" element={<p>Unexpected destination</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Login route destinations", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuthStore.setState({ isAuthenticated: false, autoLogin: false });
  });

  it("opens the workspace after authentication", () => {
    useAuthStore.setState({ isAuthenticated: true });
    renderLoginRoute();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });

  it("opens the workspace when automatic login is enabled", () => {
    useAuthStore.setState({ autoLogin: true });
    renderLoginRoute();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });

  it("preserves a requested destination", () => {
    useAuthStore.setState({ isAuthenticated: true });
    renderLoginRoute("/login?redirect=/flow/example");
    expect(screen.getByText("Requested flow")).toBeInTheDocument();
  });

  it("shows the login form to an anonymous visitor", () => {
    renderLoginRoute();
    expect(screen.getByText("Login form")).toBeInTheDocument();
  });
});
