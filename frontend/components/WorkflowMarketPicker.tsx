"use client";

import {
  marketSelectionFromSource,
  normalizeInstrument,
  resolveDataSource,
  saveWorkflowMarketDefaults,
  type WorkflowConfigSchema,
  type WorkflowMarketSelection,
} from "@/lib/workflow-config";

export function WorkflowMarketPicker({
  schema,
  brokerSource,
  instrument,
  disabled,
  onChange,
}: {
  schema: WorkflowConfigSchema;
  brokerSource: string;
  instrument: string;
  disabled?: boolean;
  onChange: (selection: WorkflowMarketSelection) => void;
}) {
  const source = resolveDataSource(schema, brokerSource);
  const allowed = source.instruments;
  const displayInstrument = normalizeInstrument(source, instrument);

  const commit = (nextSource: string, nextInstrument: string) => {
    const selection = marketSelectionFromSource(schema, nextSource, nextInstrument);
    saveWorkflowMarketDefaults(selection);
    onChange(selection);
  };

  return (
    <div className="workflow-market-picker">
      <label>
        Data source
        <select
          value={source.value}
          disabled={disabled}
          onChange={(event) => commit(event.target.value, displayInstrument)}
        >
          {schema.data_sources.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Instrument
        <select
          value={displayInstrument}
          disabled={disabled}
          onChange={(event) => commit(source.value, event.target.value)}
        >
          {allowed.map((ticker) => (
            <option key={ticker} value={ticker}>
              {ticker}
            </option>
          ))}
        </select>
      </label>
      <span className="workflow-market-hint">{source.instrument_hint}</span>
    </div>
  );
}
