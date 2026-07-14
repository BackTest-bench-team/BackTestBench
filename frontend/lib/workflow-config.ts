"use client";

import { useCallback, useEffect, useState } from "react";

export type WorkflowTimeframeOption = {
  value: string;
  max_lookback_days: number;
};

export type WorkflowDataSource = {
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
  timeframes: WorkflowTimeframeOption[];
};

export type WorkflowConfigSchema = {
  data_sources: WorkflowDataSource[];
  instruments: string[];
  timeframes: WorkflowTimeframeOption[];
  defaults: Record<string, string | number>;
};

export type WorkflowMarketSelection = {
  brokerSource: string;
  instrument: string;
  dataSource: string;
};

export const WORKFLOW_MARKET_DEFAULTS_KEY = "backtestbench.workflow.market.v1";
export const EXPLORE_TIMEFRAME = "1d";

const REMOTE_MAX_LOOKBACK_DAYS = 3650;
const TBANK_MAX_BY_TF: Record<string, number> = {
  "1m": 1,
  "5m": 7,
  "15m": 24,
  "30m": 25,
  "1h": 100,
  "1d": 2400,
  "1w": 2100,
  "1M": 3600,
};

function timeframesForSource(source: string): WorkflowTimeframeOption[] {
  const values = ["1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"];
  return values.map((value) => ({
    value,
    max_lookback_days: source === "tbank" ? (TBANK_MAX_BY_TF[value] ?? 30) : REMOTE_MAX_LOOKBACK_DAYS,
  }));
}

const CRYPTO_INSTRUMENTS = [
  "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
  "BNBUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
];

/** Used when /api/config is unavailable so Explore/Bot buttons still work on the VM. */
export function workflowSchemaFallback(): WorkflowConfigSchema {
  const timeframes = timeframesForSource("tbank");
  return {
    data_sources: [
      {
        value: "tbank",
        label: "T-Bank",
        description: "MOEX TQBR shares via Tinkoff Invest API",
        instrument_hint: "Russian equities on MOEX (SBER, GAZP, …)",
        token_env: "TINKOFF_TOKEN",
        token_required: true,
        token_optional: false,
        token_configured: false,
        instruments: [
          "SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "VTBR",
          "YDEX", "OZON", "MGNT", "MTSS", "CHMF", "NLMK", "ALRS", "PLZL",
        ],
        default_instrument: "SBER",
        timeframes,
      },
      {
        value: "twelvedata",
        label: "Twelve Data",
        description: "Global equities, FX and crypto via Twelve Data API",
        instrument_hint: "US stocks, FX and crypto (AAPL, BTC/USD, …)",
        token_env: "TWELVEDATA_TOKEN",
        token_required: true,
        token_optional: false,
        token_configured: false,
        instruments: ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "SPY", "BTC/USD", "ETH/USD"],
        default_instrument: "AAPL",
        timeframes: timeframesForSource("twelvedata"),
      },
      {
        value: "bybit",
        label: "Bybit",
        description: "Crypto spot pairs via Bybit public kline API",
        instrument_hint: "Crypto spot pairs (BTCUSDT, ETHUSDT, …)",
        token_env: "BYBIT_TOKEN",
        token_required: false,
        token_optional: true,
        token_configured: true,
        instruments: CRYPTO_INSTRUMENTS,
        default_instrument: "BTCUSDT",
        timeframes: timeframesForSource("bybit"),
      },
      {
        value: "binance",
        label: "Binance",
        description: "Crypto spot pairs via Binance public kline API",
        instrument_hint: "Crypto spot pairs (BTCUSDT, ETHUSDT, …)",
        token_env: "BINANCE_TOKEN",
        token_required: false,
        token_optional: true,
        token_configured: true,
        instruments: CRYPTO_INSTRUMENTS,
        default_instrument: "BTCUSDT",
        timeframes: timeframesForSource("binance"),
      },
    ],
    instruments: [
      "SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "VTBR",
      "YDEX", "OZON", "MGNT", "MTSS", "CHMF", "NLMK", "ALRS", "PLZL",
    ],
    timeframes,
    defaults: {
      data_source: "tbank",
      instrument: "SBER",
      timeframe: "1h",
      lookback_days: 30,
      initial_capital: 100_000,
      optimization_mode: "grid",
      optimization_iterations: 16,
    },
  };
}

export const BOT_POLL_SECONDS: Record<string, number> = {
  "1m": 30,
  "5m": 60,
  "15m": 120,
  "1h": 180,
  "4h": 300,
  "1d": 600,
};

export function sourceDisplayName(source: string): string {
  const map: Record<string, string> = {
    tbank: "T-Bank",
    twelvedata: "Twelve Data",
    bybit: "Bybit",
    binance: "Binance",
  };
  return map[source.toLowerCase()] ?? source;
}

export function pollSecondsForTimeframe(timeframe: string): number {
  return BOT_POLL_SECONDS[timeframe] ?? 120;
}

export function resolveDataSource(schema: WorkflowConfigSchema, value: string): WorkflowDataSource {
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

export function normalizeInstrument(source: WorkflowDataSource, instrument: string): string {
  const allowed = new Set(source.instruments);
  return allowed.has(instrument) ? instrument : source.default_instrument;
}

export function marketSelectionFromSource(
  schema: WorkflowConfigSchema,
  brokerSource: string,
  instrument?: string
): WorkflowMarketSelection {
  const source = resolveDataSource(schema, brokerSource);
  const ticker = normalizeInstrument(source, instrument ?? source.default_instrument);
  return {
    brokerSource: source.value,
    instrument: ticker,
    dataSource: source.label,
  };
}

export function loadWorkflowMarketDefaults(schema: WorkflowConfigSchema): WorkflowMarketSelection {
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(WORKFLOW_MARKET_DEFAULTS_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { brokerSource?: string; instrument?: string };
        if (parsed.brokerSource) {
          return marketSelectionFromSource(schema, parsed.brokerSource, parsed.instrument);
        }
      }
    } catch {
      // ignore
    }
  }
  const firstSource = schema.data_sources[0]?.value ?? "tbank";
  return marketSelectionFromSource(schema, firstSource);
}

export function saveWorkflowMarketDefaults(selection: Pick<WorkflowMarketSelection, "brokerSource" | "instrument">) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      WORKFLOW_MARKET_DEFAULTS_KEY,
      JSON.stringify({
        brokerSource: selection.brokerSource,
        instrument: selection.instrument,
      })
    );
  } catch {
    // ignore quota errors
  }
}

export function exploreDateLimits(schema: WorkflowConfigSchema, brokerSource: string) {
  const source = resolveDataSource(schema, brokerSource);
  const tf =
    source.timeframes.find((item) => item.value === EXPLORE_TIMEFRAME) ?? source.timeframes[0];
  const maxDays = tf?.max_lookback_days ?? 365;
  const now = new Date();
  const earliest = new Date(now);
  earliest.setUTCDate(earliest.getUTCDate() - maxDays);
  return {
    min_date: earliest.toISOString().slice(0, 10),
    max_date: now.toISOString().slice(0, 10),
    max_days: maxDays,
    explore_timeframe: EXPLORE_TIMEFRAME,
    data_source: source.label,
    broker_source: source.value,
  };
}

export function botRollingWindowMaxDays(
  schema: WorkflowConfigSchema,
  brokerSource: string,
  timeframe: string
): number {
  const source = resolveDataSource(schema, brokerSource);
  const tf = source.timeframes.find((item) => item.value === timeframe) ?? source.timeframes[0];
  return tf?.max_lookback_days ?? 30;
}

async function loadConfigSchema(): Promise<WorkflowConfigSchema> {
  const res = await fetch("/api/config", { cache: "no-store" });
  const json = (await res.json()) as {
    ok: boolean;
    schema?: WorkflowConfigSchema;
    message?: string;
  };
  if (!res.ok || !json.ok || !json.schema) {
    throw new Error(json.message ?? "Failed to load config schema");
  }
  return json.schema;
}

export function useWorkflowConfig() {
  const [schema, setSchema] = useState<WorkflowConfigSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const next = await loadConfigSchema();
      setSchema(next);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load workflow config";
      setSchema(workflowSchemaFallback());
      setError(`Using offline workflow defaults (${message})`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { schema, loading, error, reload };
}
