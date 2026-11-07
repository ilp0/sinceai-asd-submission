export type ItemStatus = "pending" | "running" | "done" | "failed" | "skipped";

export type RunState = "running" | "paused" | "stopped";

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type JobConfig = {
  concurrency?: number;
  maxAttempts?: number;
  leaseSeconds?: number;
  delayMs?: number;
  [key: string]: JsonValue | undefined;
};

export type PlannedItem<P = JsonValue> = {
  key: string;
  payload?: P;
};

export type ItemContext<P = JsonValue> = {
  run: string;
  key: string;
  payload: P;
  attempt: number;
  config: Required<Pick<JobConfig, "concurrency" | "maxAttempts" | "leaseSeconds" | "delayMs">> & JobConfig;
  log: (...args: unknown[]) => void;
  skip: (reason: string) => never;
  fail: (reason: string) => never;
};

export type PlanContext = {
  run: string;
  config: JobConfig;
  log: (...args: unknown[]) => void;
};

export type Job<P = JsonValue, R = JsonValue> = {
  name: string;
  version: string;
  config?: JobConfig;
  watch?: string[];
  plan?: (ctx: PlanContext) => AsyncIterable<PlannedItem<P>> | Iterable<PlannedItem<P>>;
  handle: (ctx: ItemContext<P>) => Promise<R | void> | R | void;
};

export type Item = {
  id: number;
  run: string;
  key: string;
  status: ItemStatus;
  payload: JsonValue;
  result: JsonValue;
  error: string | null;
  attempts: number;
  version: string | null;
  worker: string | null;
  leaseUntil: number | null;
  createdAt: number;
  updatedAt: number;
};

export type Run = {
  name: string;
  jobFile: string | null;
  state: RunState;
  config: JobConfig;
  generation: number;
  plannedAt: number | null;
  heartbeatAt: number | null;
  createdAt: number;
};
