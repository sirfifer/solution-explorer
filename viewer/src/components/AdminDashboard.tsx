import { useEffect, useState } from "react";
import { useArchStore } from "../store";
import { useAdminData } from "../hooks/useAdminData";
import { HealthTab } from "./admin/HealthTab";
import { ActivityTab } from "./admin/ActivityTab";
import { HistoryTab } from "./admin/HistoryTab";
import { SettingsTab } from "./admin/SettingsTab";
import { ResourcesTab } from "./admin/ResourcesTab";

type AdminTab = "health" | "activity" | "history" | "settings" | "resources";

export function AdminDashboard() {
  const { adminOpen, setAdminOpen, liveConfig, darkMode } = useArchStore();
  const { data: adminData, loading, error, refetch } = useAdminData();
  const [activeTab, setActiveTab] = useState<AdminTab>("health");

  const showResources = liveConfig?.backend_mode !== "github";

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "a") {
        e.preventDefault();
        setAdminOpen(!adminOpen);
      }
      if (e.key === "Escape" && adminOpen) {
        setAdminOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [adminOpen, setAdminOpen]);

  if (!adminOpen) return null;

  const tabs: { key: AdminTab; label: string }[] = [
    { key: "health", label: "Health" },
    { key: "activity", label: "Activity" },
    { key: "history", label: "History" },
    { key: "settings", label: "Settings" },
    ...(showResources ? [{ key: "resources" as AdminTab, label: "Resources" }] : []),
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh]"
      onClick={() => setAdminOpen(false)}
    >
      {/* Backdrop */}
      <div className={`absolute inset-0 ${darkMode ? "bg-black/60" : "bg-black/30"} backdrop-blur-sm`} />

      {/* Panel */}
      <div
        className={`
          relative w-full max-w-4xl mx-4 rounded-2xl shadow-2xl overflow-hidden flex flex-col
          max-h-[80vh]
          ${darkMode ? "bg-zinc-900 border border-zinc-800" : "bg-white border border-zinc-200"}
        `}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className={`flex items-center justify-between px-5 py-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <div className="flex items-center gap-3">
            <span className={`text-sm font-semibold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
              Admin Dashboard
            </span>
            {liveConfig && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                liveConfig.backend_mode === "github"
                  ? darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"
                  : darkMode ? "bg-orange-500/20 text-orange-300" : "bg-orange-100 text-orange-700"
              }`}>
                {liveConfig.backend_mode}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {error && (
              <span className={`text-[10px] ${darkMode ? "text-red-400" : "text-red-600"}`}>
                {error}
              </span>
            )}
            <button
              onClick={refetch}
              className={`text-xs px-2 py-1 rounded ${
                darkMode
                  ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                  : "text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100"
              }`}
              title="Refresh data"
            >
              {loading ? "..." : "\u21BB"}
            </button>
            <kbd className={`text-[10px] px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-100 text-zinc-400"}`}>
              ESC
            </kbd>
          </div>
        </div>

        {/* Tab bar */}
        <div className={`flex border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`
                flex-1 px-3 py-2 text-xs font-medium transition-colors
                ${activeTab === tab.key
                  ? darkMode
                    ? "border-b-2 border-blue-500 text-blue-400"
                    : "border-b-2 border-blue-500 text-blue-600"
                  : darkMode
                    ? "text-zinc-500 hover:text-zinc-300"
                    : "text-zinc-400 hover:text-zinc-600"
                }
              `}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === "health" && <HealthTab adminData={adminData} loading={loading} />}
          {activeTab === "activity" && <ActivityTab adminData={adminData} loading={loading} />}
          {activeTab === "history" && <HistoryTab adminData={adminData} loading={loading} />}
          {activeTab === "settings" && <SettingsTab />}
          {activeTab === "resources" && showResources && <ResourcesTab adminData={adminData} loading={loading} />}
        </div>
      </div>
    </div>
  );
}
