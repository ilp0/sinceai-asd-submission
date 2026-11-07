// Shared helpers for the experiment-6 lr job. The lr worker runs on the Mac; every item is one bounded
// SSH action on a RunPod pod (runpod/ssh.sh). Training runs detached on the pod (runpod/start.sh) and
// resumes from runs/<name>/checkpoint.pt; the Mac holds the lr state and the copied logs.
import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const exec = promisify(execFile);
export const EXP = join(dirname(fileURLToPath(import.meta.url)), '..');
export const REMOTE_EXP = '/root/exp6/data_analysis_experiment_6_model';

export async function local(cmd: string, args: string[], timeoutMs: number): Promise<string> {
  try {
    const { stdout } = await exec(cmd, args, { timeout: timeoutMs, maxBuffer: 64 << 20, cwd: EXP });
    return stdout;
  } catch (e: any) {
    throw new Error(`${cmd} ${args.slice(0, 3).join(' ')} failed: ${`${e.stdout ?? ''}\n${e.stderr ?? e.message}`.trim().slice(-3000)}`);
  }
}

/** One command on a pod, run in the experiment folder there. */
export function pod(podName: string, command: string, timeoutMs: number): Promise<string> {
  return local(join(EXP, 'runpod/ssh.sh'), [podName, `cd ${REMOTE_EXP} && export OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 PYTHONUNBUFFERED=1 && ${command}`], timeoutMs);
}

export function lastJson(stdout: string): any {
  const lines = stdout.trim().split('\n').filter((l) => l.trim().startsWith('{'));
  if (!lines.length) throw new Error(`no JSON result in output: ${stdout.slice(-1500)}`);
  return JSON.parse(lines.at(-1)!);
}

export function jsonLines(stdout: string): any[] {
  return stdout.trim().split('\n').filter((l) => l.trim().startsWith('{')).map((l) => JSON.parse(l));
}

/** Copy the run folder back (TensorBoard events, history, JSON/CSV/parquet results, best.pt; no checkpoint.pt). */
export async function pullRun(podName: string, runName: string): Promise<void> {
  const dest = join(EXP, 'runs', runName);
  mkdirSync(dest, { recursive: true });
  await local('rsync', ['-a', '-e', `${join(EXP, 'runpod/ssh.sh')} ${podName}`, '--exclude=checkpoint.pt', '--exclude=*.tmp',
    '--exclude=train.lock', `pod:${REMOTE_EXP}/runs/${runName}/`, `${dest}/`], 900000);
}

/** The worker runs on ilpo-dev; the results must also be visible on the Mac. Copy the run folder to the
 *  Mac worktree (fleet key, WireGuard). Best effort: a sleeping Mac gets the files at the next segment. */
export const MAC = 'ilpo@10.100.0.7';
export const MAC_EXP = '/Users/ilpo/git/SinceAI-BusinessTurku-ASD/.claude/worktrees/timestral-multiclass-prediction-c697e7/data_analysis_experiment_6_model';
export async function pushMac(runName: string, log?: (...a: unknown[]) => void): Promise<boolean> {
  if (process.platform === 'darwin') return true;          // the worker already runs on the Mac
  try {
    await local('rsync', ['-a', '-e', '/usr/bin/ssh -i ' + join(process.env.HOME ?? '', '.ssh/id_ed25519_fleet') +
      ' -o BatchMode=yes -o ConnectTimeout=15', `${join(EXP, 'runs', runName)}/`, `${MAC}:${MAC_EXP}/runs/${runName}/`], 600000);
    return true;
  } catch (e: any) {
    log?.(`Mac copy failed (Mac asleep?): ${String(e.message).slice(-300)}`);
    return false;
  }
}

export function localSummary(runName: string): any | null {
  const f = join(EXP, 'runs', runName, 'summary.json');
  return existsSync(f) ? JSON.parse(readFileSync(f, 'utf8')) : null;
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
