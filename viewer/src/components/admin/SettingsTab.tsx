import { useArchStore } from "../../store";

export function SettingsTab() {
  const { darkMode, liveConfig } = useArchStore();

  if (!liveConfig) {
    return (
      <div className={`flex items-center justify-center py-12 text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        No live configuration available
      </div>
    );
  }

  const isGitHub = liveConfig.backend_mode === "github";

  return (
    <div className="p-4 space-y-5">
      {/* Read-only banner for GitHub mode */}
      {isGitHub && (
        <div className={`rounded-lg border p-3 text-xs ${
          darkMode
            ? "border-amber-800/40 bg-amber-950/30 text-amber-300"
            : "border-amber-200 bg-amber-50 text-amber-800"
        }`}>
          Edit <code className={`px-1 py-0.5 rounded ${darkMode ? "bg-amber-900/40" : "bg-amber-100"}`}>solution-explorer.json</code> in your repo to change settings.
        </div>
      )}

      {/* General */}
      <div>
        <h3 className={`text-xs font-semibold mb-2 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
          General
        </h3>
        <div className={`rounded-lg border p-3 space-y-2.5 ${darkMode ? "border-zinc-800 bg-zinc-800/30" : "border-zinc-200 bg-zinc-50"}`}>
          <SettingsRow label="Backend Mode" darkMode={darkMode}>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              liveConfig.backend_mode === "github"
                ? darkMode ? "bg-zinc-700 text-zinc-300" : "bg-zinc-200 text-zinc-700"
                : darkMode ? "bg-orange-500/20 text-orange-300" : "bg-orange-100 text-orange-700"
            }`}>
              {liveConfig.backend_mode}
            </span>
          </SettingsRow>
          <SettingsRow label="Data URL" darkMode={darkMode}>
            <span className={`text-xs font-medium truncate max-w-[60%] ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{liveConfig.data_url}</span>
          </SettingsRow>
          {liveConfig.project_id && (
            <SettingsRow label="Project ID" darkMode={darkMode}>
              <span className={`text-xs font-medium ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{liveConfig.project_id}</span>
            </SettingsRow>
          )}
        </div>
      </div>

      {/* Polling config */}
      <div>
        <h3 className={`text-xs font-semibold mb-2 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
          Polling
        </h3>
        <div className={`rounded-lg border p-3 space-y-2.5 ${darkMode ? "border-zinc-800 bg-zinc-800/30" : "border-zinc-200 bg-zinc-50"}`}>
          <ValueRow label="Default Interval" value={`${liveConfig.polling.default_interval_seconds}s`} darkMode={darkMode} />
          <ValueRow label="Min Interval" value={`${liveConfig.polling.min_interval_seconds}s`} darkMode={darkMode} />
          <ValueRow label="Idle Interval" value={`${liveConfig.polling.idle_interval_seconds}s`} darkMode={darkMode} />
          <ValueRow label="Adaptive" value={liveConfig.polling.adaptive ? "Enabled" : "Disabled"} darkMode={darkMode} />
          <ValueRow label="Pause When Hidden" value={liveConfig.polling.pause_when_hidden ? "Enabled" : "Disabled"} darkMode={darkMode} />
        </div>
      </div>

      {/* Feature flags */}
      <div>
        <h3 className={`text-xs font-semibold mb-2 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
          Features
        </h3>
        <div className={`rounded-lg border p-3 space-y-2.5 ${darkMode ? "border-zinc-800 bg-zinc-800/30" : "border-zinc-200 bg-zinc-50"}`}>
          <FeatureRow label="Activity Log" enabled={liveConfig.features.activity_log} darkMode={darkMode} />
          <FeatureRow label="Admin Dashboard" enabled={liveConfig.features.admin_dashboard} darkMode={darkMode} />
          <FeatureRow label="Version History" enabled={liveConfig.features.version_history} darkMode={darkMode} />
          <FeatureRow label="CI Status Overlay" enabled={liveConfig.features.ci_status_overlay} darkMode={darkMode} />
          <FeatureRow label="Realtime CI Webhooks" enabled={liveConfig.features.realtime_ci_webhooks} darkMode={darkMode} requirement="cloudflare" />
          <FeatureRow label="Realtime Push" enabled={liveConfig.features.realtime_push} darkMode={darkMode} requirement="cloudflare" />
        </div>
      </div>
    </div>
  );
}

function SettingsRow({ label, darkMode, children }: { label: string; darkMode: boolean; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className={darkMode ? "text-zinc-400" : "text-zinc-500"}>{label}</span>
      {children}
    </div>
  );
}

function ValueRow({ label, value, darkMode }: { label: string; value: string; darkMode: boolean }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className={darkMode ? "text-zinc-400" : "text-zinc-500"}>{label}</span>
      <span className={`font-medium ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{value}</span>
    </div>
  );
}

function FeatureRow({ label, enabled, darkMode, requirement }: {
  label: string;
  enabled: boolean;
  darkMode: boolean;
  requirement?: string;
}) {
  return (
    <div className="flex items-center justify-between text-xs">
      <div className="flex items-center gap-2">
        <span className={darkMode ? "text-zinc-400" : "text-zinc-500"}>{label}</span>
        {requirement && (
          <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            (requires: {requirement})
          </span>
        )}
      </div>
      <span className={`font-medium ${
        enabled
          ? darkMode ? "text-emerald-400" : "text-emerald-600"
          : darkMode ? "text-zinc-600" : "text-zinc-400"
      }`}>
        {enabled ? "On" : "Off"}
      </span>
    </div>
  );
}
