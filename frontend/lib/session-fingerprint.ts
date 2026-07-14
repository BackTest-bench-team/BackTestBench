export function stableParamsKey(params: Record<string, number>) {
  const sorted = Object.keys(params)
    .sort()
    .map((key) => [key, params[key]] as const);
  return JSON.stringify(sorted);
}

export function exploreSessionFingerprint(session: {
  strategyId: string;
  params: Record<string, number>;
  fromDate: string;
  toDate: string;
  instrument: string;
  brokerSource: string;
}) {
  return `explore:${session.strategyId}:${stableParamsKey(session.params)}:${session.instrument}:${session.brokerSource}:${session.fromDate}:${session.toDate}`;
}

export function botSessionFingerprint(session: {
  strategyId: string;
  params: Record<string, number>;
  instrument: string;
  timeframe: string;
  daysToFetch: number;
  brokerSource: string;
}) {
  return `bot:${session.strategyId}:${stableParamsKey(session.params)}:${session.instrument}:${session.brokerSource}:${session.timeframe}:${session.daysToFetch}`;
}

function sessionPriority(status: string) {
  if (status === "running" || status === "queued") return 3;
  if (status === "completed") return 2;
  if (status === "error") return 1;
  return 0;
}

export function dedupeByFingerprint<T extends { status: string; jobId?: string; id: string }>(
  sessions: T[],
  fingerprint: (session: T) => string
) {
  const byFingerprint = new Map<string, T>();

  for (const session of sessions) {
    const key = fingerprint(session);
    const existing = byFingerprint.get(key);
    if (!existing) {
      byFingerprint.set(key, session);
      continue;
    }

    const nextPriority = sessionPriority(session.status);
    const existingPriority = sessionPriority(existing.status);
    if (nextPriority > existingPriority) {
      byFingerprint.set(key, session);
      continue;
    }

    if (nextPriority === existingPriority) {
      const nextStamp = session.jobId ?? session.id;
      const existingStamp = existing.jobId ?? existing.id;
      if (nextStamp.localeCompare(existingStamp) > 0) {
        byFingerprint.set(key, session);
      }
    }
  }

  return Array.from(byFingerprint.values());
}
