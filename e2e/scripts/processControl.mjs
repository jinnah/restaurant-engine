// Tracked child-tree termination (M2F correction F5): one policy,
// injectable for deterministic tests.
//
// Windows: `taskkill /pid <tracked-pid> /T /F` kills exactly the
// recorded process tree — never a name or port match.
// POSIX: long-lived children are spawned detached, making each the
// leader of its own process group; termination signals the tracked
// group (`kill(-pid)`) — graceful SIGTERM, bounded wait, then SIGKILL —
// so grandchildren (e.g. a bundler helper) go with their parent. The
// orchestrator's own group is never a target because a detached child's
// group id is the child's own pid, and only recorded handles are ever
// passed in. Short-lived foreground commands stay in the orchestrator's
// group and are simply awaited to completion.

/**
 * @param deps injectable primitives:
 *   platform      process.platform (e.g. 'win32', 'linux')
 *   signalProcess (pid, signal) => void   — process.kill
 *   runTaskkill   (args: string[]) => void — spawnSync('taskkill', args)
 *   wait          (ms) => Promise<void>
 */
export function createChildTerminator({
  platform,
  signalProcess,
  runTaskkill,
  wait,
}) {
  return async function terminate(handle) {
    const child = handle.child;
    const pid = child.pid;
    if (!Number.isInteger(pid) || pid <= 0) {
      return; // never actually spawned (spawn error): nothing to target
    }
    if (child.exitCode !== null || child.signalCode !== null) {
      return; // already exited: not a failure, nothing to do
    }

    signalTree('SIGTERM');
    const grace = await Promise.race([
      handle.exited.then(() => 'exited'),
      wait(5000).then(() => 'timeout'),
    ]);
    if (grace === 'timeout') {
      signalTree('SIGKILL');
      await Promise.race([handle.exited, wait(5000)]);
    }

    function signalTree(signal) {
      if (platform === 'win32') {
        // /F is already forceful; the escalation round is a no-op guard.
        runTaskkill(['/pid', String(pid), '/T', '/F']);
      } else {
        try {
          signalProcess(-pid, signal); // the tracked detached group
        } catch (error) {
          if (error.code !== 'ESRCH') {
            throw error; // a real failure must surface in cleanup
          }
          // ESRCH: the group is already gone — success, not a failure.
        }
      }
    }
  };
}
