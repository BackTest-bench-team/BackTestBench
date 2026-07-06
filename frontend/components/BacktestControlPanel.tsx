"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type TimeframeOption = {
  value: string;
  max_lookback_days: number;
};

type OptimizationModeOption = {
  value: string;
  description: string;
};

type ConfigSchema = {
  instruments: string[];
  timeframes: TimeframeOption[];
  optimization_modes: OptimizationModeOption[];
  defaults: Record<string, string | number>;
};

export type RuntimeSettings = {
  instrument: string;
  timeframe: string;
  lookback_days: number;
  initial_capital: number;
  optimization_mode: string;
  optimization_iterations: number;
  optimization_seed: number;
};

type BacktestControlPanelProps = {
  busy: boolean;
  onRun: (settings: RuntimeSettings) => Promise<void>;
  onStop: () => Promise<void>;
};

function settingsFromPayload(
  settings: Record<string, unknown>,
  schema: ConfigSchema
): RuntimeSettings {
  const allowed = new Set(schema.instruments);
  const rawInstrument = String(settings.instrument ?? schema.defaults.instrument ?? "SBER");
  const instrument = allowed.has(rawInstrument)
    ? rawInstrument
    : String(schema.defaults.instrument ?? "SBER");

  return {
    instrument,
    timeframe: String(settings.timeframe ?? schema.defaults.timeframe ?? "1h"),
    lookback_days: Number(settings.lookback_days ?? schema.defaults.lookback_days ?? 30),
    initial_capital: Number(settings.initial_capital ?? schema.defaults.initial_capital ?? 100_000),
    optimization_mode: String(
      settings.optimization_mode ?? schema.defaults.optimization_mode ?? "grid"
    ),
    optimization_iterations: Number(
      settings.optimization_iterations ?? schema.defaults.optimization_iterations ?? 16
    ),
    optimization_seed: Number(settings.optimization_seed ?? schema.defaults.optimization_seed ?? 42),
  };
}

export function BacktestControlPanel({ busy, onRun, onStop }: BacktestControlPanelProps) {
  const [schema, setSchema] = useState<ConfigSchema | null>(null);
  const [draft, setDraft] = useState<RuntimeSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/config", { cache: "no-store" });
        const json = (await res.json()) as {
          ok: boolean;
          settings?: Record<string, unknown>;
          schema?: ConfigSchema;
          message?: string;
        };
        if (!res.ok || !json.ok || !json.settings || !json.schema) {
          throw new Error(json.message ?? "Failed to load settings");
        }
        if (!cancelled) {
          setSchema(json.schema);
          setDraft(settingsFromPayload(json.settings, json.schema));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load settings");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedTimeframe = useMemo(
    () => schema?.timeframes.find((item) => item.value === draft?.timeframe),
    [schema, draft?.timeframe]
  );

  const sampleMode = draft?.optimization_mode === "sample";

  const patch = useCallback((partial: Partial<RuntimeSettings>) => {
    setDraft((prev) => (prev ? { ...prev, ...partial } : prev));
    setError(null);
  }, []);

  const handleRun = useCallback(async () => {
    if (!draft) return;
    setError(null);
    try {
      await onRun(draft);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    }
  }, [draft, onRun]);

  const handleStop = useCallback(async () => {
    setError(null);
    try {
      await onStop();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stop failed");
    }
  }, [onStop]);

  if (loading || !draft || !schema) {
    return (
      <section className="control-panel control-panel-loading">
        <p className="control-panel-kicker">Backtest control</p>
        <p className="control-panel-placeholder">Loading settings…</p>
      </section>
    );
  }

  return (
    <section className="control-panel" aria-label="Backtest control panel">
      <div className="control-panel-head">
        <div>
          <p className="control-panel-kicker">Backtest control</p>
          <h2 className="control-panel-title">Run settings</h2>
        </div>
        <div className="control-panel-actions">
          <button className="control-btn control-btn-run" type="button" disabled={busy} onClick={handleRun}>
            {busy ? "Running…" : "Run backtest"}
          </button>
          <button className="control-btn control-btn-stop" type="button" disabled={!busy} onClick={handleStop}>
            Stop
          </button>
        </div>
      </div>

      {error && <div className="control-panel-error">{error}</div>}

      <div className="control-panel-grid">
        <label className="control-field">
          <span className="control-label">Instrument</span>
          <select
            className="control-input"
            value={draft.instrument}
            disabled={busy}
            onChange={(event) => patch({ instrument: event.target.value })}
          >
            {schema.instruments.map((ticker) => (
              <option key={ticker} value={ticker}>
                {ticker}
              </option>
            ))}
          </select>
          <span className="control-hint">MOEX TQBR shares supported by T-Bank adapter</span>
        </label>

        <label className="control-field">
          <span className="control-label">Timeframe</span>
          <select
            className="control-input"
            value={draft.timeframe}
            disabled={busy}
            onChange={(event) => patch({ timeframe: event.target.value })}
          >
            {schema.timeframes.map((item) => (
              <option key={item.value} value={item.value}>
                {item.value}
              </option>
            ))}
          </select>
          <span className="control-hint">
            Min resolution 1m. Max lookback for {draft.timeframe}:{" "}
            {selectedTimeframe?.max_lookback_days ?? "—"} days
          </span>
        </label>

        <label className="control-field">
          <span className="control-label">Lookback days</span>
          <input
            className="control-input"
            type="number"
            min={1}
            max={selectedTimeframe?.max_lookback_days ?? 3600}
            value={draft.lookback_days}
            disabled={busy}
            onChange={(event) => patch({ lookback_days: Number(event.target.value) })}
          />
          <span className="control-hint">History window loaded for the backtest</span>
        </label>

        <label className="control-field">
          <span className="control-label">Initial capital (RUB)</span>
          <input
            className="control-input"
            type="number"
            min={1000}
            step={1000}
            value={draft.initial_capital}
            disabled={busy}
            onChange={(event) => patch({ initial_capital: Number(event.target.value) })}
          />
          <span className="control-hint">Starting portfolio cash for each strategy</span>
        </label>
      </div>

      <div className="control-panel-section">
        <p className="control-section-title">Optimization</p>
        <div className="optimization-mode-list">
          {schema.optimization_modes.map((mode) => (
            <label
              key={mode.value}
              className={`optimization-mode-card${
                draft.optimization_mode === mode.value ? " is-selected" : ""
              }`}
            >
              <input
                type="radio"
                name="optimization_mode"
                value={mode.value}
                checked={draft.optimization_mode === mode.value}
                disabled={busy}
                onChange={() => patch({ optimization_mode: mode.value })}
              />
              <span className="optimization-mode-name">{mode.value}</span>
              <span className="optimization-mode-desc">{mode.description}</span>
            </label>
          ))}
        </div>

        <div className="control-panel-grid control-panel-grid-compact">
          <label className="control-field">
            <span className="control-label">Optimization iterations</span>
            <input
              className="control-input"
              type="number"
              min={1}
              max={10000}
              value={draft.optimization_iterations}
              disabled={busy || !sampleMode}
              onChange={(event) =>
                patch({ optimization_iterations: Number(event.target.value) })
              }
            />
            <span className="control-hint">
              {sampleMode
                ? "Number of random combinations to evaluate"
                : "Ignored in grid mode (all combinations are evaluated)"}
            </span>
          </label>

          <label className="control-field">
            <span className="control-label">Optimization seed</span>
            <input
              className="control-input"
              type="number"
              value={draft.optimization_seed}
              disabled={busy || !sampleMode}
              onChange={(event) => patch({ optimization_seed: Number(event.target.value) })}
            />
            <span className="control-hint">
              {sampleMode
                ? "Fixes the random sample for reproducible runs"
                : "Used only in sample mode"}
            </span>
          </label>
        </div>
      </div>
    </section>
  );
}
