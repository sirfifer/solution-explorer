import { useArchStore } from "../store";

export function ReviewModeButton() {
  const { reviewMode, annotations, darkMode, toggleReviewMode, setActivePanel } = useArchStore();
  const count = annotations.length;

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={toggleReviewMode}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors
          ${reviewMode
            ? darkMode
              ? "bg-blue-500/20 text-blue-300 ring-1 ring-blue-500/40"
              : "bg-blue-100 text-blue-700 ring-1 ring-blue-300"
            : darkMode
              ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300"
              : "bg-zinc-100 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-700"
          }
        `}
        title={reviewMode ? "Exit review mode" : "Enter review mode"}
      >
        <span className="text-sm">&#x270D;&#xFE0F;</span>
        <span className="hidden sm:inline">Review</span>
        {count > 0 && (
          <span className={`
            text-[10px] min-w-[18px] h-[18px] flex items-center justify-center rounded-full font-medium
            ${darkMode ? "bg-blue-500/30 text-blue-200" : "bg-blue-200 text-blue-700"}
          `}>
            {count}
          </span>
        )}
      </button>

      {/* Show review summary button when there are annotations */}
      {count > 0 && reviewMode && (
        <button
          onClick={() => setActivePanel("review")}
          className={`
            p-1.5 rounded-lg text-sm transition-colors
            ${darkMode
              ? "hover:bg-zinc-700 text-zinc-400"
              : "hover:bg-zinc-200 text-zinc-500"
            }
          `}
          title="View all annotations"
        >
          &#x1F4CB;
        </button>
      )}
    </div>
  );
}
