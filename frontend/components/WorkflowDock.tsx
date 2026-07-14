"use client";

import {
  BotDockPanel,
  type BotSession,
} from "@/components/BotDock";
import { ExploreDock, type ExploreSession } from "@/components/ExploreDock";
import type { WorkflowConfigSchema } from "@/lib/workflow-config";

export type WorkflowMode = "explore" | "bot";

function tabLabel(session: { title: string; strategyId: string }, kind: WorkflowMode) {
  const short = session.title.length > 22 ? `${session.title.slice(0, 20)}…` : session.title;
  return kind === "bot" ? short : short;
}

function statusLabel(status: string) {
  if (status === "running" || status === "queued") return "Running";
  if (status === "completed") return "Done";
  if (status === "error") return "Error";
  return "Ready";
}

export function WorkflowDock({
  mode,
  onModeChange,
  exploreSessions,
  activeExploreId,
  workflowSchema,
  onExploreSelect,
  onExploreClose,
  onExplorePatch,
  onExploreRun,
  botSessions,
  activeBotId,
  onBotSelect,
  onBotClose,
  onBotPatch,
  onBotRun,
  collapsed,
  onToggleCollapse,
  onBotStop,
}: {
  mode: WorkflowMode;
  onModeChange: (mode: WorkflowMode) => void;
  exploreSessions: ExploreSession[];
  activeExploreId: string | null;
  workflowSchema: WorkflowConfigSchema | null;
  onExploreSelect: (id: string) => void;
  onExploreClose: (id: string) => void;
  onExplorePatch: (id: string, patch: Partial<ExploreSession>) => void;
  onExploreRun: (id: string) => Promise<void>;
  botSessions: BotSession[];
  activeBotId: string | null;
  onBotSelect: (id: string) => void;
  onBotClose: (id: string) => void;
  onBotPatch: (id: string, patch: Partial<BotSession>) => void;
  onBotRun: (id: string) => Promise<void>;
  onBotStop: (id: string) => Promise<void>;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const hasExplore = exploreSessions.length > 0;
  const hasBot = botSessions.length > 0;
  if (!hasExplore && !hasBot) return null;

  const activeExplore = exploreSessions.find((s) => s.id === activeExploreId) ?? exploreSessions[0];
  const activeBot = botSessions.find((s) => s.id === activeBotId) ?? botSessions[0];
  const runningExplore = exploreSessions.filter((s) => s.status === "running" || s.status === "queued").length;
  const runningBot = botSessions.filter((s) => s.status === "running" || s.status === "queued").length;
  const runningCount = mode === "explore" ? runningExplore : runningBot;

  const tabs =
    mode === "explore"
      ? exploreSessions.map((session) => ({
          id: session.id,
          kind: "explore" as const,
          title: tabLabel(session, "explore"),
          status: session.status,
          onSelect: () => onExploreSelect(session.id),
          onClose: () => onExploreClose(session.id),
        }))
      : botSessions.map((session) => ({
          id: session.id,
          kind: "bot" as const,
          title: tabLabel(session, "bot"),
          status: session.status,
          onSelect: () => onBotSelect(session.id),
          onClose: () => onBotClose(session.id),
        }));

  return (
    <section
      className={`explore-dock workflow-dock${collapsed ? " is-collapsed" : ""}`}
      aria-label="Workflow sessions"
    >
      <header className="explore-dock-bar workflow-dock-bar">
        <div className="explore-dock-bar-title workflow-dock-bar-title">
          <div className="workflow-dock-modes" role="tablist" aria-label="Workflow mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "explore"}
              className={`workflow-mode-btn${mode === "explore" ? " is-active" : ""}`}
              disabled={!hasExplore}
              onClick={() => onModeChange("explore")}
            >
              <span className="workflow-kind-badge is-explore">Explore</span>
              {hasExplore && <span className="workflow-mode-count">{exploreSessions.length}</span>}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "bot"}
              className={`workflow-mode-btn${mode === "bot" ? " is-active" : ""}`}
              disabled={!hasBot}
              onClick={() => onModeChange("bot")}
            >
              <span className="workflow-kind-badge is-bot">Trading Bot</span>
              {hasBot && <span className="workflow-mode-count">{botSessions.length}</span>}
            </button>
            {runningCount > 0 && (
              <span className="explore-dock-badge workflow-active-badge">{runningCount} active</span>
            )}
          </div>
        </div>
        <div className="explore-dock-tabs" role="tablist">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={
                mode === "explore" ? tab.id === activeExplore?.id : tab.id === activeBot?.id
              }
              className={`explore-dock-tab workflow-dock-tab${
                (mode === "explore" ? tab.id === activeExplore?.id : tab.id === activeBot?.id)
                  ? " is-active"
                  : ""
              }`}
              onClick={tab.onSelect}
            >
              <span className={`workflow-kind-badge is-${tab.kind}`}>
                {tab.kind === "explore" ? "EXP" : "BOT"}
              </span>
              <span className={`explore-dock-tab-dot is-${tab.status}`} />
              <span className="explore-dock-tab-text">{tab.title}</span>
              <span
                className="explore-dock-tab-close"
                onClick={(e) => {
                  e.stopPropagation();
                  tab.onClose();
                }}
              >
                ×
              </span>
            </button>
          ))}
        </div>
        <button className="explore-dock-toggle" type="button" onClick={onToggleCollapse}>
          {collapsed ? "Expand" : "Collapse"}
        </button>
      </header>

      {!collapsed && mode === "explore" && activeExplore && workflowSchema && (
        <ExploreDock
          sessions={exploreSessions}
          activeId={activeExplore.id}
          schema={workflowSchema}
          onPatch={onExplorePatch}
          onRun={onExploreRun}
        />
      )}

      {!collapsed && mode === "bot" && activeBot && workflowSchema && (
        <BotDockPanel
          sessions={botSessions}
          activeId={activeBot.id}
          schema={workflowSchema}
          onPatch={onBotPatch}
          onRun={onBotRun}
          onStop={onBotStop}
        />
      )}
    </section>
  );
}

export { statusLabel as workflowStatusLabel };
