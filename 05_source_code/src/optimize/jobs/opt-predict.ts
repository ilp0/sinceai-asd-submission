// lr run opt-predict: fine-stride validation probabilities of the two frozen experiment-6 checkpoints on one RunPod
// A100 (user approval 7 Nov 2026: 1 x A100 SXM 80GB, $1.79/h, stop guard 1.5 h, terminate after the copy back).
// Start: lr run optimize/jobs/opt-predict.ts     Status: lr status opt-predict
//
// Items (concurrency 1, processed in key order; every item is idempotent):
//   00-pod        create pod "opt" (exp6-opt) unless one is running; start the Mac-side stop guard
//   01-sync       experiment-6 code + data (no test telemetry), the two checkpoints, predict_val.py; pod setup
//   02-start      start both predictions on the pod (detached; a finished or running one is not started again)
//   10-wait-<m>   wait for <out>/<run>/DONE on the pod (restart a dead process), then copy the files to the Mac
//   99-terminate  terminate the pod after both prediction sets are complete on the Mac
import { execFile, spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import type { Job } from './lr-types.ts';

const exec = promisify(execFile);
const OPT = join(dirname(fileURLToPath(import.meta.url)), '..');
const EXP = join(OPT, '../.claude/worktrees/timestral-multiclass-prediction-c697e7/data_analysis_experiment_6_model');
const POD = 'opt';
const REMOTE = '/root/exp6';
const MODELS: Record<string, { run: string; checkpoint: string }> = {
  '3h': { run: 'rp3-3h-r32-v1', checkpoint: 'checkpoint_last_step11500' },
  '6h': { run: 'rp3-6h-r32-v1', checkpoint: 'checkpoint_last_step14750' },
};

async function local(cmd: string, args: string[], timeoutMs: number): Promise<string> {
  try {
    const { stdout } = await exec(cmd, args, { timeout: timeoutMs, maxBuffer: 64 << 20, cwd: EXP });
    return stdout;
  } catch (e: any) {
    throw new Error(`${cmd} ${args.slice(0, 3).join(' ')} failed: ${`${e.stdout ?? ''}\n${e.stderr ?? e.message}`.trim().slice(-3000)}`);
  }
}
const ssh = (command: string, timeoutMs: number) =>
  local(join(EXP, 'runpod/ssh.sh'), [POD, `export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4; ${command}`], timeoutMs);
const rsh = `${join(EXP, 'runpod/ssh.sh')} ${POD}`;
const podRecord = () => {
  const f = join(EXP, 'runpod/pods.json');
  return existsSync(f) ? JSON.parse(readFileSync(f, 'utf8'))[POD] : undefined;
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const doneLocal = (m: string) => existsSync(join(OPT, 'predictions', MODELS[m].run, 'DONE'));

type P = { action: 'pod' | 'sync' | 'start' | 'wait' | 'terminate'; model?: string };

const startCmd = (m: string, batch: number) => {
  const { run, checkpoint } = MODELS[m];
  const log = `${REMOTE}/optimize/logs/${run}.log`;
  return `cd ${REMOTE}/optimize && mkdir -p logs && if [ -f predictions/${run}/DONE ]; then echo '{"state":"done"}'; ` +
    `elif [ -f logs/${run}.pid ] && kill -0 $(cat logs/${run}.pid) 2>/dev/null; then echo '{"state":"running"}'; ` +
    `else setsid nohup python predict_val.py --exp ${REMOTE}/data_analysis_experiment_6_model --run ${run} ` +
    `--checkpoint ${checkpoint} --batch ${batch} --workers 6 >> ${log} 2>&1 < /dev/null & echo $! > logs/${run}.pid; sleep 2; echo '{"state":"started"}'; fi`;
};

async function handle({ payload: p, config, log }: any) {
  if (p.action === 'pod') {
    const rec = podRecord();
    if (!rec || ['TERMINATED', 'GONE'].includes(rec.status)) {
      log('creating pod exp6-opt');
      await local('python3', ['runpod/pods.py', 'create', POD, '--gpu', config.gpu, '--disk', '60', '--min-vcpu', '16'], 900000);
    } else {
      await local('python3', ['runpod/pods.py', 'refresh'], 120000);
    }
    // Mac-side cost guard: stops every pod in pods.json older than guardHours; exits when none runs.
    const g = spawn('nohup', ['python3', 'runpod/pods.py', 'guard', '--hours', String(config.guardHours)],
      { cwd: EXP, detached: true, stdio: ['ignore', 'ignore', 'ignore'] });
    g.unref();
    for (let i = 0; i < 20; i++) {
      try { return { pod: podRecord(), uname: (await ssh('nvidia-smi --query-gpu=name,memory.total --format=csv,noheader', 60000)).trim() }; }
      catch (e) { await sleep(15000); }
    }
    throw new Error('pod SSH not reachable yet');
  }
  if (p.action === 'sync') {
    await local('bash', ['runpod/sync.sh', POD], 1800000);
    for (const m of Object.values(MODELS)) {
      await ssh(`mkdir -p ${REMOTE}/data_analysis_experiment_6_model/runs/${m.run}`, 60000);
      await local('rsync', ['-a', '-e', rsh, join(EXP, 'runs', m.run, `${m.checkpoint}.pt`),
        `pod:${REMOTE}/data_analysis_experiment_6_model/runs/${m.run}/`], 1800000);
    }
    await ssh(`mkdir -p ${REMOTE}/optimize`, 60000);
    await local('rsync', ['-a', '-e', rsh, join(OPT, 'predict_val.py'), `pod:${REMOTE}/optimize/`], 300000);
    const setup = await ssh(`cd ${REMOTE}/data_analysis_experiment_6_model && bash runpod/setup.sh ${config.guardHours}`, 900000);
    return { setup: setup.trim().split('\n').slice(-4) };
  }
  if (p.action === 'start') {
    const out: Record<string, string> = {};
    for (const m of Object.keys(MODELS)) out[m] = (await ssh(startCmd(m, Number(config.batch)), 120000)).trim();
    return out;
  }
  if (p.action === 'wait') {
    const { run } = MODELS[p.model];
    const deadline = Date.now() + (Number(config.leaseSeconds) - 120) * 1000;
    for (;;) {
      const st = JSON.parse((await ssh(startCmd(p.model, Number(config.batch)), 120000)).trim().split('\n').at(-1)!);   // restarts a dead process
      if (st.state === 'started') log(`(re)started ${run}`);
      if (st.state === 'done') break;
      if (Date.now() > deadline) {
        const tail = await ssh(`tail -n 3 ${REMOTE}/optimize/logs/${run}.log`, 60000);
        throw new Error(`${run} not done yet: ${tail.trim().slice(-500)}`);
      }
      await sleep(Number(config.pollMs));
    }
    await local('rsync', ['-a', '-e', rsh, `pod:${REMOTE}/optimize/predictions/${run}/`, join(OPT, 'predictions', run) + '/'], 1800000);
    await local('rsync', ['-a', '-e', rsh, `pod:${REMOTE}/optimize/logs/${run}.log`, join(OPT, 'predictions', run) + '/'], 300000);
    if (!doneLocal(p.model)) throw new Error(`DONE marker missing on the Mac for ${run}`);
    return JSON.parse(readFileSync(join(OPT, 'predictions', run, 'DONE'), 'utf8'));
  }
  // terminate
  const missing = Object.keys(MODELS).filter((m) => !doneLocal(m));
  if (missing.length) throw new Error(`predictions not complete on the Mac: ${missing.join(', ')}`);
  const rec = podRecord();
  if (rec && !['TERMINATED', 'GONE'].includes(rec.status)) await local('python3', ['runpod/pods.py', 'terminate', POD], 120000);
  const after = podRecord();
  const iso = (t: string) => Date.parse(t.replace(/([+-]\d\d)(\d\d)$/, '$1:$2'));
  const hours = (iso(after?.terminated_at ?? new Date().toISOString()) - iso(after?.created)) / 3.6e6;
  return { terminated: after?.terminated_at, hours: Math.round(hours * 100) / 100, cost_usd: Math.round(hours * (after?.cost_per_hr ?? 0) * 100) / 100 };
}

const job: Job<P> = {
  name: 'opt-predict',
  version: 'v2',
  config: { concurrency: 1, maxAttempts: 40, leaseSeconds: 1800, pollMs: 30000, guardHours: 1.5, batch: 64, gpu: 'NVIDIA A100-SXM4-80GB' },
  async *plan() {
    yield { key: '00-pod', payload: { action: 'pod' } };
    yield { key: '01-sync', payload: { action: 'sync' } };
    yield { key: '02-start', payload: { action: 'start' } };
    yield { key: '10-wait-3h', payload: { action: 'wait', model: '3h' } };
    yield { key: '11-wait-6h', payload: { action: 'wait', model: '6h' } };
    yield { key: '99-terminate', payload: { action: 'terminate' } };
  },
  handle,
};
export default job;
