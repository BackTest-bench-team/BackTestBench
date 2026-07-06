"use client";

import { useState } from "react";

const STRATEGY_TEMPLATE = `# Composable strategy YAML (saved to config/strategies/{name}.yaml)
name: my_strategy
title: My Strategy

params:
  order_size: { type: float, default: 1, choices: [1, 2, 3], optimizable: false }

series:
  sma_fast: { fn: sma, source: price, period: 10 }
  sma_slow: { fn: sma, source: price, period: 30 }

rules:
  - id: entry
    scope: flat
    priority: 10
    when: { cross_above: [sma_fast, sma_slow] }
    then: { action: buy, size: "\${order_size}" }

  - id: exit
    scope: long
    priority: 10
    when: { cross_below: [sma_fast, sma_slow] }
    then: { action: sell, size: all }
`;

type AddStrategyPanelProps = {
  busy: boolean;
  onAdded: () => Promise<void> | void;
};

export function AddStrategyPanel({ busy, onAdded }: AddStrategyPanelProps) {
  const [open, setOpen] = useState(false);
  const [yaml, setYaml] = useState(STRATEGY_TEMPLATE);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/strategies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml }),
      });
      const json = (await res.json()) as { ok: boolean; message?: string; strategy?: { id: string } };
      if (!res.ok || !json.ok) {
        throw new Error(json.message ?? "Failed to save strategy");
      }
      setOpen(false);
      setYaml(STRATEGY_TEMPLATE);
      await onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save strategy");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="add-strategy-panel" aria-label="Add strategy">
      <div className="add-strategy-head">
        <div>
          <p className="add-strategy-kicker">Strategies</p>
          <h2 className="add-strategy-title">Registered from config/strategies/</h2>
        </div>
        <button
          className="control-btn control-btn-run"
          type="button"
          disabled={busy || saving}
          onClick={() => {
            setError(null);
            setOpen((value) => !value);
          }}
        >
          {open ? "Close editor" : "Add strategy"}
        </button>
      </div>

      {open && (
        <div className="add-strategy-editor">
          <label className="control-field">
            <span className="control-label">Strategy YAML</span>
            <textarea
              className="add-strategy-textarea"
              value={yaml}
              disabled={busy || saving}
              spellCheck={false}
              rows={18}
              onChange={(event) => {
                setYaml(event.target.value);
                setError(null);
              }}
            />
            <span className="control-hint">
              Must include name, params, series, and rules. File is saved as config/strategies/
              {"{name}"}.yaml and picked up on the next dashboard refresh.
            </span>
          </label>

          {error && <div className="control-panel-error">{error}</div>}

          <div className="add-strategy-actions">
            <button
              className="control-btn control-btn-run"
              type="button"
              disabled={busy || saving || !yaml.trim()}
              onClick={handleSave}
            >
              {saving ? "Saving…" : "Save strategy"}
            </button>
            <button
              className="control-btn control-btn-stop"
              type="button"
              disabled={busy || saving}
              onClick={() => {
                setOpen(false);
                setError(null);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
