import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { ErrorBoundary } from "../components/ErrorBoundary";

function Boom({ message = "kaboom" }: { message?: string }): never {
  throw new Error(message);
}

describe("ErrorBoundary", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // React logs caught errors to console.error; silence during error-path tests
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    cleanup();
  });

  it("renders children unchanged when no error is thrown", () => {
    render(
      <ErrorBoundary>
        <div>happy path content</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("happy path content")).toBeDefined();
  });

  it("renders the fallback with the error message when a child throws", () => {
    render(
      <ErrorBoundary>
        <Boom message="specific-failure-text" />
      </ErrorBoundary>
    );
    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getByText("Something went wrong")).toBeDefined();
    expect(screen.getByText("specific-failure-text")).toBeDefined();
    expect(screen.getByRole("button", { name: "Reset navigation" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Reload page" })).toBeDefined();
  });

  it("Reset navigation button clears URL query params and reloads", () => {
    const replaceStateSpy = vi
      .spyOn(window.history, "replaceState")
      .mockImplementation(() => {});
    const reloadMock = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...originalLocation,
        pathname: "/solution-explorer/",
        search: "?component=foo&drill=bar",
        reload: reloadMock,
      },
    });

    try {
      render(
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>
      );
      fireEvent.click(screen.getByRole("button", { name: "Reset navigation" }));

      expect(replaceStateSpy).toHaveBeenCalledWith({}, "", "/solution-explorer/");
      expect(reloadMock).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, "location", {
        configurable: true,
        value: originalLocation,
      });
      replaceStateSpy.mockRestore();
    }
  });

  it("Reload page button reloads without touching history", () => {
    const replaceStateSpy = vi
      .spyOn(window.history, "replaceState")
      .mockImplementation(() => {});
    const reloadMock = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, reload: reloadMock },
    });

    try {
      render(
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>
      );
      fireEvent.click(screen.getByRole("button", { name: "Reload page" }));

      expect(reloadMock).toHaveBeenCalledTimes(1);
      expect(replaceStateSpy).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, "location", {
        configurable: true,
        value: originalLocation,
      });
      replaceStateSpy.mockRestore();
    }
  });
});
