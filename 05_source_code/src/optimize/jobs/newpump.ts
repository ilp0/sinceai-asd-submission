// lr run opt-newpump-45002: one new generated pump (seed 45002), 3h model at 10 s on this Mac, then the frozen-rule score.
// Start: lr run optimize/jobs/newpump.ts     Status: lr status opt-newpump-45002
import { execFile } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import type { Job } from './lr-types.ts';

const exec = promisify(execFile);
const OPT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SEED = 45002;
async function py(bin: string, args: string[], ms: number) {
  try {
    const { stdout } = await exec(bin, ['newpump.py', ...args, '--seed', String(SEED)], { cwd: OPT, timeout: ms, maxBuffer: 64 << 20 });
    return JSON.parse(stdout.trim().split('\n').filter((l) => l.startsWith('{')).at(-1)!);
  } catch (e: any) { throw new Error(`${args[0]} failed: ${`${e.stdout ?? ''}\n${e.stderr ?? e.message}`.slice(-2500)}`); }
}
const job: Job<{ action: string }> = {
  name: `opt-newpump-${SEED}`,
  version: 'v1',
  config: { concurrency: 1, maxAttempts: 2, leaseSeconds: 3600 },
  async *plan() { yield { key: '1-predict', payload: { action: 'predict' } }; yield { key: '2-score', payload: { action: 'score' } }; },
  async handle({ payload }) {
    return payload.action === 'predict'
      ? py(join(OPT, '../data_analysis_expriment_1/.venv/bin/python'), ['predict'], 3300000)
      : py(join(OPT, '.venv/bin/python'), ['score'], 600000);
  },
};
export default job;
