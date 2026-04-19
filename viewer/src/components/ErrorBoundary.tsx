import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Class-based ErrorBoundary: deliberately has no store access, no hooks, and
// no non-React imports so the fallback UI itself cannot crash for the same
// reasons the wrapped tree might.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ErrorBoundary] Caught render error:", error, info);
  }

  handleReload = (): void => {
    window.location.reload();
  };

  handleResetNav = (): void => {
    window.history.replaceState({}, "", window.location.pathname);
    window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.error) return this.props.children;

    const message = this.state.error.message || "An unexpected error occurred.";

    // Read theme from the document element to avoid any store or hook coupling.
    // App.tsx toggles `dark`/`light` classes on <html>; default to dark if absent.
    const isDark =
      typeof document === "undefined" ||
      !document.documentElement.classList.contains("light");

    const palette = isDark
      ? {
          bg: "#0b0e14",
          fg: "#e6e6e6",
          panelBg: "#1a1f2a",
          border: "#2a3140",
          secondaryFg: "#e6e6e6",
        }
      : {
          bg: "#f6f7f9",
          fg: "#1a1f2a",
          panelBg: "#ffffff",
          border: "#d5d9e0",
          secondaryFg: "#1a1f2a",
        };

    return (
      <div
        role="alert"
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "24px",
          backgroundColor: palette.bg,
          color: palette.fg,
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        <div style={{ maxWidth: "560px", width: "100%" }}>
          <h2 style={{ margin: "0 0 12px", fontSize: "20px", fontWeight: 600 }}>
            Something went wrong
          </h2>
          <p style={{ margin: "0 0 8px", opacity: 0.85, lineHeight: 1.5 }}>
            The viewer hit an error while rendering this view.
          </p>
          <pre
            style={{
              margin: "0 0 20px",
              padding: "12px",
              backgroundColor: palette.panelBg,
              border: `1px solid ${palette.border}`,
              borderRadius: "6px",
              fontSize: "13px",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {message}
          </pre>
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={this.handleResetNav}
              style={{
                padding: "10px 16px",
                backgroundColor: "#3b82f6",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                fontSize: "14px",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Reset navigation
            </button>
            <button
              type="button"
              onClick={this.handleReload}
              style={{
                padding: "10px 16px",
                backgroundColor: "transparent",
                color: palette.secondaryFg,
                border: `1px solid ${palette.border}`,
                borderRadius: "6px",
                fontSize: "14px",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Reload page
            </button>
          </div>
        </div>
      </div>
    );
  }
}
