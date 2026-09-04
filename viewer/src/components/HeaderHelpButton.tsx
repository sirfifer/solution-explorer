export function HeaderHelpButton({ className = "" }: { className?: string }) {
  return (
    <button
      type="button"
      data-testid="help-button"
      onClick={() => window.dispatchEvent(new Event("arch-viz-open-help"))}
      aria-label="Open Help"
      title="Open Help"
      className={`flex min-h-11 shrink-0 items-center gap-1 rounded-lg px-2 py-2 text-xs font-bold text-zinc-500 hover:bg-zinc-500/10 hover:text-cyan-500 sm:min-h-0 sm:py-1.5 ${className}`}
    >
      <span aria-hidden="true">?</span>
      <span>Help</span>
    </button>
  );
}
