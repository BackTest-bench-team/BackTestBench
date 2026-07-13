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

type DataSourceOption = {
  value: string;
  label: string;
  description: string;
  instrument_hint: string;
  token_env: string;
  token_required: boolean;
  token_optional: boolean;
  token_configured: boolean;
  instruments: string[];
  default_instrument: string;
  timeframes: TimeframeOption[];
};

type ConfigSchema = {
  data_sources: DataSourceOption[];
  instruments: string[];
  timeframes: TimeframeOption[];
  optimization_modes: OptimizationModeOption[];
  defaults: Record<string, string | number>;
};

export type RuntimeSettings = {
  data_source: string;
  instrument: string;
  timeframe: string;
  lookback_days: number;
  initial_capital: number;
  optimization_mode: string;
  optimization_iterations: number;
};

type TokenStatus = {
  configured: boolean;
  masked: string | null;
};

type TokenFeedback = {
  status: "ok" | "error";
  message: string;
};

type BacktestControlPanelProps = {
  busy: boolean;
  onRunStart: (settings: RuntimeSettings) => void;
  onRun: (settings: RuntimeSettings) => Promise<void>;
  onStop: () => Promise<void>;
};

async function loadConfigPayload(): Promise<{
  settings: Record<string, unknown>;
  schema: ConfigSchema;
}> {
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
  return { settings: json.settings, schema: json.schema };
}

async function loadTokenStatus(): Promise<Record<string, TokenStatus>> {
  const res = await fetch("/api/tokens", { cache: "no-store" });
  const json = (await res.json()) as {
    ok: boolean;
    tokens?: Record<string, TokenStatus>;
    message?: string;
  };
  if (!res.ok || !json.ok || !json.tokens) {
    throw new Error(json.message ?? "Failed to load token status");
  }
  return json.tokens;
}

function DeferredNumberInput({
  value,
  onCommit,
  min = 1,
  max,
  step,
  disabled,
  className,
}: {
  value: number;
  onCommit: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  className?: string;
}) {
  const [text, setText] = useState(String(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) {
      setText(String(value));
    }
  }, [focused, value]);

  function commit(raw: string) {
    const trimmed = raw.trim();
    if (trimmed === "") {
      onCommit(min);
      setText(String(min));
      return;
    }

    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) {
      setText(String(value));
      return;
    }

    let next = parsed;
    if (min != null) next = Math.max(min, next);
    if (max != null) next = Math.min(max, next);
    onCommit(next);
    setText(String(next));
  }

  return (
    <input
      className={className}
      type="text"
      inputMode="numeric"
      value={focused ? text : String(value)}
      disabled={disabled}
      onFocus={() => {
        setFocused(true);
        setText(String(value));
      }}
      onChange={(event) => setText(event.target.value)}
      onBlur={() => {
        setFocused(false);
        commit(text);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.currentTarget.blur();
        }
      }}
      step={step}
    />
  );
}

function resolveDataSource(schema: ConfigSchema, value: string): DataSourceOption {
  return (
    schema.data_sources.find((item) => item.value === value) ??
    schema.data_sources[0] ?? {
      value: "tbank",
      label: "T-Bank",
      description: "",
      instrument_hint: "",
      token_env: "TINKOFF_TOKEN",
      token_required: true,
      token_optional: false,
      token_configured: false,
      instruments: schema.instruments,
      default_instrument: String(schema.defaults.instrument ?? "SBER"),
      timeframes: schema.timeframes,
    }
  );
}

function settingsFromPayload(
  settings: Record<string, unknown>,
  schema: ConfigSchema
): RuntimeSettings {
  const dataSource = String(settings.data_source ?? schema.defaults.data_source ?? "tbank");
  const source = resolveDataSource(schema, dataSource);
  const allowed = new Set(source.instruments);
  const rawInstrument = String(settings.instrument ?? source.default_instrument);
  const instrument = allowed.has(rawInstrument) ? rawInstrument : source.default_instrument;
  const timeframe = String(settings.timeframe ?? schema.defaults.timeframe ?? "1h");
  const timeframeMeta = source.timeframes.find((item) => item.value === timeframe);
  const maxLookback = timeframeMeta?.max_lookback_days ?? 30;
  const lookbackRaw = Number(settings.lookback_days ?? schema.defaults.lookback_days ?? 30);

  return {
    data_source: source.value,
    instrument,
    timeframe,
    lookback_days: Math.min(Math.max(lookbackRaw, 1), maxLookback),
    initial_capital: Number(settings.initial_capital ?? schema.defaults.initial_capital ?? 100_000),
    optimization_mode: String(
      settings.optimization_mode ?? schema.defaults.optimization_mode ?? "grid"
    ),
    optimization_iterations: Number(
      settings.optimization_iterations ?? schema.defaults.optimization_iterations ?? 16
    ),
  };
}

export function BacktestControlPanel({ busy, onRunStart, onRun, onStop }: BacktestControlPanelProps) {
  const [schema, setSchema] = useState<ConfigSchema | null>(null);
  const [draft, setDraft] = useState<RuntimeSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tokenStatus, setTokenStatus] = useState<Record<string, TokenStatus>>({});
  const [tokenDrafts, setTokenDrafts] = useState({ tinkoff: "", twelvedata: "" });
  const [tokenFeedback, setTokenFeedback] = useState<Record<string, TokenFeedback>>({});
  const [tokenBusy, setTokenBusy] = useState<"TINKOFF_TOKEN" | "TWELVEDATA_TOKEN" | null>(null);

  const refreshPanel = useCallback(async () => {
    const [configPayload, tokens] = await Promise.all([loadConfigPayload(), loadTokenStatus()]);
    setSchema(configPayload.schema);
    setTokenStatus(tokens);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [configPayload, tokens] = await Promise.all([
          loadConfigPayload(),
          loadTokenStatus(),
        ]);
        if (!cancelled) {
          setSchema(configPayload.schema);
          setDraft(settingsFromPayload(configPayload.settings, configPayload.schema));
          setTokenStatus(tokens);
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

  const verifyToken = useCallback(
    async (envKey: "TINKOFF_TOKEN" | "TWELVEDATA_TOKEN") => {
      const draftKey = envKey === "TINKOFF_TOKEN" ? "tinkoff" : "twelvedata";
      const value = tokenDrafts[draftKey].trim();
      if (!value) {
        setTokenFeedback((prev) => ({
          ...prev,
          [envKey]: { status: "error", message: "Enter a token first" },
        }));
        return;
      }

      setTokenBusy(envKey);
      setTokenFeedback((prev) => {
        const next = { ...prev };
        delete next[envKey];
        return next;
      });

      try {
        const body =
          envKey === "TINKOFF_TOKEN"
            ? { tinkoff_token: value, verify: true }
            : { twelvedata_token: value, verify: true };
        const res = await fetch("/api/tokens", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const json = (await res.json()) as {
          ok: boolean;
          tokens?: Record<string, TokenStatus & { valid?: boolean; message?: string }>;
          message?: string;
        };
        const tokenResult = json.tokens?.[envKey];
        if (!res.ok || !json.ok) {
          setTokenFeedback((prev) => ({
            ...prev,
            [envKey]: {
              status: "error",
              message: tokenResult?.message ?? json.message ?? "Token verification failed",
            },
          }));
          return;
        }

        setTokenDrafts((prev) => ({ ...prev, [draftKey]: "" }));
        setTokenFeedback((prev) => ({
          ...prev,
          [envKey]: {
            status: "ok",
            message: tokenResult?.message ?? `${envKey} configured`,
          },
        }));
        await refreshPanel();
      } catch (err) {
        setTokenFeedback((prev) => ({
          ...prev,
          [envKey]: {
            status: "error",
            message: err instanceof Error ? err.message : "Token verification failed",
          },
        }));
      } finally {
        setTokenBusy(null);
      }
    },
    [refreshPanel, tokenDrafts]
  );

  const selectedSource = useMemo(
    () => (schema && draft ? resolveDataSource(schema, draft.data_source) : null),
    [schema, draft]
  );

  const selectedTimeframe = useMemo(
    () => selectedSource?.timeframes.find((item) => item.value === draft?.timeframe),
    [selectedSource, draft?.timeframe]
  );

  const patch = useCallback((partial: Partial<RuntimeSettings>) => {
    setDraft((prev) => {
      if (!prev || !schema) return prev;
      const next = { ...prev, ...partial };
      if (partial.data_source && partial.data_source !== prev.data_source) {
        const source = resolveDataSource(schema, partial.data_source);
        const allowed = new Set(source.instruments);
        if (!allowed.has(next.instrument)) {
          next.instrument = source.default_instrument;
        }
        const tfMeta = source.timeframes.find((item) => item.value === next.timeframe);
        if (tfMeta) {
          next.lookback_days = Math.min(next.lookback_days, tfMeta.max_lookback_days);
        }
      }
      if (partial.timeframe) {
        const tfMeta = selectedSource?.timeframes.find((item) => item.value === partial.timeframe);
        if (tfMeta) {
          next.lookback_days = Math.min(next.lookback_days, tfMeta.max_lookback_days);
        }
      }
      return next;
    });
    setError(null);
  }, [schema, selectedSource]);

  const handleRun = useCallback(async () => {
    if (!draft || busy) return;
    setError(null);
    onRunStart(draft);
    try {
      await onRun(draft);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    }
  }, [busy, draft, onRun, onRunStart]);

  const handleStop = useCallback(async () => {
    setError(null);
    try {
      await onStop();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stop failed");
    }
  }, [onStop]);

  const isRunning = busy;

  if (loading || !draft || !schema || !selectedSource) {
    return (
      <section className="control-panel control-panel-loading">
        <p className="control-panel-kicker">Backtest control</p>
        <p className="control-panel-placeholder">Loading settings…</p>
      </section>
    );
  }

  const tokenReady = selectedSource.token_configured;
  const runDisabled = isRunning || (selectedSource.token_required && !tokenReady);

  return (
    <section className="control-panel" aria-label="Backtest control panel">
      <div className="control-panel-head">
        <div>
          <p className="control-panel-kicker">Backtest control</p>
          <h2 className="control-panel-title">Run settings</h2>
        </div>
        <div className="control-panel-actions">
          <button
            className={`control-btn control-btn-run${isRunning ? " is-running" : ""}`}
            type="button"
            disabled={runDisabled}
            aria-busy={isRunning}
            onClick={handleRun}
          >
            {isRunning ? (
              <>
                <span className="control-btn-spinner" aria-hidden="true" />
                Running…
              </>
            ) : (
              "Run backtest"
            )}
          </button>
          <button
            className="control-btn control-btn-stop"
            type="button"
            disabled={!isRunning}
            onClick={handleStop}
          >
            Stop
          </button>
        </div>
      </div>

      {error && <div className="control-panel-error">{error}</div>}

      <div className="control-panel-section">
        <p className="control-section-title">Data source</p>
        <div className="data-source-list">
          {schema.data_sources.map((source) => (
            <button
              key={source.value}
              type="button"
              className={`data-source-card${
                draft.data_source === source.value ? " is-selected" : ""
              }`}
              disabled={isRunning}
              onClick={() => patch({ data_source: source.value })}
            >
              <span className="data-source-name">{source.label}</span>
              <span className="data-source-desc">{source.description}</span>
              <span
                className={`data-source-token${
                  source.token_configured ? " is-ready" : " is-missing"
                }`}
              >
                {source.token_optional
                  ? "No token required"
                  : source.token_configured
                    ? `${source.token_env} configured`
                    : `Set ${source.token_env} below`}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="control-panel-section">
        <p className="control-section-title">API tokens</p>
        <p className="control-section-hint">
          Tokens are verified against the provider, then saved to <code>.env</code> in the
          repository root.
        </p>
        <div className="api-token-list">
          <div className="api-token-row">
            <label className="control-field api-token-field">
              <span className="control-label">T-Bank API token</span>
              <input
                className="control-input"
                type="password"
                autoComplete="off"
                placeholder={
                  tokenStatus.TINKOFF_TOKEN?.configured
                    ? `Configured (${tokenStatus.TINKOFF_TOKEN.masked ?? "saved"})`
                    : "Paste Tinkoff Invest API token"
                }
                value={tokenDrafts.tinkoff}
                disabled={isRunning || tokenBusy === "TINKOFF_TOKEN"}
                onChange={(event) =>
                  setTokenDrafts((prev) => ({ ...prev, tinkoff: event.target.value }))
                }
              />
            </label>
            <button
              className="control-btn control-btn-verify"
              type="button"
              disabled={isRunning || tokenBusy === "TINKOFF_TOKEN"}
              onClick={() => verifyToken("TINKOFF_TOKEN")}
            >
              {tokenBusy === "TINKOFF_TOKEN" ? "Verifying…" : "Verify & save"}
            </button>
            {tokenFeedback.TINKOFF_TOKEN && (
              <p
                className={`api-token-feedback is-${tokenFeedback.TINKOFF_TOKEN.status}`}
              >
                {tokenFeedback.TINKOFF_TOKEN.message}
              </p>
            )}
          </div>

          <div className="api-token-row">
            <label className="control-field api-token-field">
              <span className="control-label">Twelve Data API token</span>
              <input
                className="control-input"
                type="password"
                autoComplete="off"
                placeholder={
                  tokenStatus.TWELVEDATA_TOKEN?.configured
                    ? `Configured (${tokenStatus.TWELVEDATA_TOKEN.masked ?? "saved"})`
                    : "Paste Twelve Data API key"
                }
                value={tokenDrafts.twelvedata}
                disabled={isRunning || tokenBusy === "TWELVEDATA_TOKEN"}
                onChange={(event) =>
                  setTokenDrafts((prev) => ({ ...prev, twelvedata: event.target.value }))
                }
              />
            </label>
            <button
              className="control-btn control-btn-verify"
              type="button"
              disabled={isRunning || tokenBusy === "TWELVEDATA_TOKEN"}
              onClick={() => verifyToken("TWELVEDATA_TOKEN")}
            >
              {tokenBusy === "TWELVEDATA_TOKEN" ? "Verifying…" : "Verify & save"}
            </button>
            {tokenFeedback.TWELVEDATA_TOKEN && (
              <p
                className={`api-token-feedback is-${tokenFeedback.TWELVEDATA_TOKEN.status}`}
              >
                {tokenFeedback.TWELVEDATA_TOKEN.message}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="control-panel-grid">
        <label className="control-field">
          <span className="control-label">Instrument</span>
          <select
            className="control-input"
            value={draft.instrument}
            disabled={isRunning}
            onChange={(event) => patch({ instrument: event.target.value })}
          >
            {selectedSource.instruments.map((ticker) => (
              <option key={ticker} value={ticker}>
                {ticker}
              </option>
            ))}
          </select>
          <span className="control-hint">{selectedSource.instrument_hint}</span>
        </label>

        <label className="control-field">
          <span className="control-label">Timeframe</span>
          <select
            className="control-input"
            value={draft.timeframe}
            disabled={isRunning}
            onChange={(event) => patch({ timeframe: event.target.value })}
          >
            {selectedSource.timeframes.map((item) => (
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
          <DeferredNumberInput
            className="control-input"
            min={1}
            max={selectedTimeframe?.max_lookback_days ?? 3600}
            value={draft.lookback_days}
            disabled={isRunning}
            onCommit={(lookback_days) => patch({ lookback_days })}
          />
          <span className="control-hint">History window loaded for the backtest</span>
        </label>

        <label className="control-field">
          <span className="control-label">Initial capital (RUB)</span>
          <DeferredNumberInput
            className="control-input"
            min={1000}
            step={1000}
            value={draft.initial_capital}
            disabled={isRunning}
            onCommit={(initial_capital) => patch({ initial_capital })}
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
                disabled={isRunning}
                onChange={() => patch({ optimization_mode: mode.value })}
              />
              <span className="optimization-mode-name">{mode.value}</span>
              <span className="optimization-mode-desc">{mode.description}</span>
              {mode.value === "sample" && draft.optimization_mode === "sample" && (
                <div
                  className="optimization-trials-inline"
                  onClick={(event) => event.stopPropagation()}
                >
                  <span className="control-label">Trials</span>
                  <DeferredNumberInput
                    className="control-input"
                    min={1}
                    max={10000}
                    value={draft.optimization_iterations}
                    disabled={isRunning}
                    onCommit={(optimization_iterations) => patch({ optimization_iterations })}
                  />
                </div>
              )}
            </label>
          ))}
        </div>
      </div>
    </section>
  );
}
