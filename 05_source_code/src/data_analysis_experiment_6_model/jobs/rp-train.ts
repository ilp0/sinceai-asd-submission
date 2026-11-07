// lr runs exp6-rp-<ctx>-<lora> (workers on ilpo-dev, /ilpo/sinceai-exp6; results copied to the Mac worktree): the six experiment-6 runs on three RunPod pods (one pod per context, two LoRA
// settings per GPU). Start: lr run jobs/rp-3h-r32.ts (one per run)   Status: lr runs | grep exp6-rp
//
// Items of one lr run (concurrency 1). Before v2 one lr run held all six; its six slots then all waited on
// the slowest runs and nobody restarted a stopped faster run.
//   00-boot                sync code+data, setup, cache, start this run (idempotent)
//   seg-NNN                 wait until the run reaches step NNN*segmentSteps (one evaluation), restart a dead
//                          process (resume from checkpoint.pt), then copy the run folder to the Mac
//   zz-1-evaluate    best checkpoint: full validation + organizer benchmark at all thresholds
//   zz-2-benchmark   best checkpoint: benchmark JSON / alerts CSV / predictions named by step
//   zz-3-pull        final copy of the run folder (best.pt included, checkpoint.pt excluded)
// Knobs (live with `lr set`): segmentSteps, maxSteps (must equal train.max_steps), pollMs.
import type { Job } from './lr-types.ts';
import { jsonLines, lastJson, local, localSummary, pod, pullRun, pushMac, sleep } from './runpod.ts';

const CONTEXTS = ['3h', '6h', '12h'];
const LORA = ['r32', 'r64'];
// prefix 'rp' = round 1 (27 training pumps), 'rp2' = round 2 (full experiment-4 training data).
const runName = (ctx: string, r: string, prefix = 'rp') => `${prefix}-${ctx}-${r}-v1`;
const configOf = (ctx: string, r: string, prefix = 'rp') => `configs/${prefix}-${ctx}-${r}.yaml`;

type P = { action: 'boot' | 'segment' | 'evaluate' | 'benchmark' | 'pull'; ctx: string; lora?: string; n?: number; prefix?: string };

async function handle({ payload: p, config, log, skip }: any) {
  const deadline = Date.now() + (Number(config.leaseSeconds) - 180) * 1000;
  if (p.action === 'boot') {
    await local('bash', ['runpod/sync.sh', p.ctx], 1200000);
    await pod(p.ctx, 'bash runpod/setup.sh 3.5', 900000);
    const prep = await pod(p.ctx, `python run.py prepare --config ${configOf(p.ctx, p.lora!, p.prefix)} | tail -1`, 1200000);
    const started = lastJson(await pod(p.ctx, `bash runpod/start.sh ${configOf(p.ctx, p.lora!, p.prefix)}`, 120000));
    return { cache: prep.trim(), started };
  }
  const run = runName(p.ctx, p.lora!, p.prefix);
  const cfg = configOf(p.ctx, p.lora!, p.prefix);
  const status = async () => jsonLines(await pod(p.ctx, 'bash runpod/status.sh', 120000)).find((r) => r.run === run);
  // Every later action needs a completed training run.
  const waitCompleted = async () => {
    for (;;) {
      const s = await status();
      if (s?.completed) return s;
      if (s && !s.alive) await pod(p.ctx, `bash runpod/start.sh ${cfg}`, 120000);
      if (Date.now() > deadline) throw new Error(`${run} not completed yet (step ${s?.step ?? 0}); retry later`);
      await sleep(Number(config.pollMs));
    }
  };
  if (p.action === 'segment') {
    const target = p.n! * Number(config.segmentSteps);
    if (localSummary(run)?.completed) skip('training already completed');
    for (;;) {
      const st = lastJson(await pod(p.ctx, `bash runpod/start.sh ${cfg}`, 120000));   // restarts a dead process
      if (st.state === 'started') log(`started ${run} at step ${st.step}`);
      const s = await status();
      if (s && (s.step >= target || s.completed)) {
        await pullRun(p.ctx, run); await pushMac(run, log);
        if (s.completed && s.step < target) skip(`run completed at step ${s.step} (early stop)`);
        return { step: s.step, step_s: s.step_s, eval: s.last_eval };
      }
      if (Date.now() > deadline) throw new Error(`${run} at step ${s?.step ?? 0} < ${target}; retry later`);
      await sleep(Number(config.pollMs));
    }
  }
  await waitCompleted();
  if (p.action === 'evaluate') {
    const out = await pod(p.ctx, `python run.py evaluate --config ${cfg} --checkpoint best 2>&1 | tail -3`, 2400000);
    await pullRun(p.ctx, run); await pushMac(run, log);
    return lastJson(out);
  }
  if (p.action === 'benchmark') {
    const out = await pod(p.ctx, `python run.py benchmark --config ${cfg} --checkpoint best 2>&1 | tail -3`, 2400000);
    await pullRun(p.ctx, run); await pushMac(run, log);
    return lastJson(out);
  }
  await pullRun(p.ctx, run); await pushMac(run, log);
  return { pulled: run, summary: localSummary(run) };
}

/** One lr run per training run (concurrency 1): its segments are processed in order, so a stopped
 *  process is always restarted by the item that waits for it. Files: jobs/rp-<ctx>-<lora>.ts. */
export function trainJob(ctx: string, lora: string, prefix = 'rp', maxSteps = 5000): Job<P> {
  return {
    name: `exp6-${runName(ctx, lora, prefix).replace(/-v1$/, '')}`,
    version: 'v2',
    watch: ['./runpod.ts', './rp-train.ts'],
    config: { concurrency: 1, maxAttempts: 60, leaseSeconds: 2700, segmentSteps: 250, maxSteps, pollMs: 30000 },
    async *plan({ config }) {
      yield { key: '00-boot', payload: { action: 'boot', ctx, lora, prefix } };
      const segs = Math.ceil(Number(config.maxSteps) / Number(config.segmentSteps));
      for (let n = 1; n <= segs; n++) yield { key: `seg-${String(n).padStart(3, '0')}`, payload: { action: 'segment', ctx, lora, n, prefix } };
      yield { key: 'zz-1-evaluate', payload: { action: 'evaluate', ctx, lora, prefix } };
      yield { key: 'zz-2-benchmark', payload: { action: 'benchmark', ctx, lora, prefix } };
      yield { key: 'zz-3-pull', payload: { action: 'pull', ctx, lora, prefix } };
    },
    handle,
  };
}


