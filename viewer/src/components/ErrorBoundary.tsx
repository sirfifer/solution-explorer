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

    return (
      <div
        role="alert"
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "24px",
          backgroundColor: "#0b0e14",
          color: "#e6e6e6",
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
              backgroundColor: "#1a1f2a",
              border: "1px solid #2a3140",
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
                color: "#e6e6e6",
                border: "1px solid #2a3140",
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
