// Top-level error boundary. Wraps the whole app so any uncaught render error
// shows a dismissible banner instead of a blank white screen.
//
// React does not have a functional API for error boundaries yet, so this stays
// a class component.

import React, { type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // Surface to devtools; production observability will replace this later.
    console.error("Uncaught error in UI:", error, info.componentStack);
  }

  private reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="banner error" role="alert" style={{ margin: 20 }}>
          <b>Something broke.</b> {this.state.error.message}{" "}
          <button onClick={this.reset}>Dismiss</button>
        </div>
      );
    }
    return this.props.children;
  }
}
