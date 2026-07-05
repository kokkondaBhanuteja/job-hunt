import React, { type ReactNode } from "react";
import { Bug } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { friendlyError } from "@/lib/friendlyError";

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
    console.error("Uncaught error in UI:", error, info.componentStack);
  }

  private reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      const friendly = friendlyError(this.state.error);
      return (
        <div className="mx-auto max-w-2xl p-5">
          <Alert variant="destructive" role="alert">
            <Bug className="h-4 w-4" />
            <AlertTitle>Something in the app crashed.</AlertTitle>
            <AlertDescription className="space-y-1">
              <p>{friendly.message}</p>
              <p className="text-xs opacity-80">
                Dismiss to try loading the screen again. If it keeps happening, refresh
                the page.
              </p>
            </AlertDescription>
            <div className="mt-3">
              <Button size="sm" variant="outline" onClick={this.reset}>
                Dismiss
              </Button>
            </div>
          </Alert>
        </div>
      );
    }
    return this.props.children;
  }
}
