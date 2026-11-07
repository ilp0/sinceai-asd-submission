// lr run opt-test-fine: test-pump predictions of the frozen 3h model at the 10 s stride, on this Mac (MPS).
// Start: lr run optimize/jobs/test-fine.ts     Status: lr status opt-test-fine
// Items (concurrency 1, key order): pump-PUMP-10..12 (one pump each, about 17 min; skipped by the script when its
// parquet file exists), then zz-alerts (alert file results/submission-fine/predictions_test.csv). No test labels are read.
import { execFile } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import type { Job } from './lr-types.ts';

const exec = promisify(execFile);
const OPT = join(dirname(fileURLToPath(import.meta.url)), '..');
const TORCH_PY = join(OPT, '../data_analysis_expriment_1/.venv/bin/python');
const OPT_PY = join(OPT, '.venv/bin/python');

async function py(bin: string, args: string[], timeoutMs: number): Promise<any> {
  try {
    const { stdout } = await exec(bin, ['predict_test_fine.py', ...args], { cwd: OPT, timeout: timeoutMs, maxBuffer: 64 << 20 });
    const lines = stdout.trim().split('\n').filter((l) => l.startsWith('{'));
    return JSON.parse(lines.at(-1)!);
  } catch (e: any) {
    throw new Error(`${args.join(' ')} failed: ${`${e.stdout ?? ''}\n${e.stderr ?? e.message}`.trim().slice(-2500)}`);
  }
}

type P = { action: 'predict' | 'alerts'; asset?: string };

const job: Job<P> = {
  name: 'opt-test-fine',
  version: 'v1',
  config: { concurrency: 1, maxAttempts: 3, leaseSeconds: 3600, batch: 128 },
  async *plan() {
    for (const a of ['PUMP-10', 'PUMP-11', 'PUMP-12']) yield { key: `pump-${a}`, payload: { action: 'predict', asset: a } };
    yield { key: 'zz-alerts', payload: { action: 'alerts' } };
  },
  async handle({ payload: p, config }) {
    if (p.action === 'predict') return py(TORCH_PY, ['predict', '--asset', p.asset!, '--batch', String(config.batch)], 3300000);
    return py(OPT_PY, ['alerts', '--split', 'test'], 600000);
  },
};
export default job;
