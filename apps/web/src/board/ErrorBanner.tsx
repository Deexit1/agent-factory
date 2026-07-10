import { XIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}): React.JSX.Element {
  return (
    <Alert
      variant="destructive"
      data-testid="transition-error"
      className="flex items-center justify-between gap-2"
    >
      <AlertDescription className="text-destructive/90">{message}</AlertDescription>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={onDismiss}
        aria-label="Dismiss error"
        className="shrink-0"
      >
        <XIcon />
      </Button>
    </Alert>
  );
}
