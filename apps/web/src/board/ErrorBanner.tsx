export function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}): React.JSX.Element {
  return (
    <div
      role="alert"
      data-testid="transition-error"
      className="flex items-center justify-between rounded-md border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-800"
    >
      <span>{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss error"
        className="ml-4 font-bold text-red-600 hover:text-red-800"
      >
        ×
      </button>
    </div>
  );
}
