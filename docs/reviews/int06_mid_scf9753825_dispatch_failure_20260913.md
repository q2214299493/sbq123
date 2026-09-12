# SCF9753825: repeated scheduler dispatch failure

This checkpoint supersedes the initial allocation snapshot. SCF9753825 was seen
moving RUN -> PEND -> RUN with changing node allocations. A direct read-only
`ssh sunboquan-codex "bjobs -l 9753825"` returned PEND with the exact reason:
`Failed in talking to server to start the job;`.

The subsequent stored checkpoint is RUN again, allocated gknew0444:32,
gknew0421:32, gknew0447:16. The recorded exclusion remains
`select[hname!=gknew0440] span[ptile=32]`. This is scheduler redispatch of the
same job 9753825; the agent did not submit another job or alter its inputs.

The latest observed state is repeated dispatch/startup failure, not verified
VASP execution. Earlier node checks found zero VASP ranks and no electronic
output; no startup success or SCF convergence is established. The scheduler
explicitly reports a communication failure when starting execution, so CPU
slot shortage alone does not explain the observed behavior. The underlying
cluster daemon/network fault has not been isolated; excluding gknew0440 has
not resolved startup. No further stop, restart or Dimer action was taken.

Next: investigate the cluster scheduler-to-execution-host launch service before
interpreting RUN as scientific progress or changing VASP parameters. Current
user-owned calculation remains submitted. State projection is updated through
review-free events; global repo-state sync remains blocked by the unrelated
classified PKG-INFO drift recorded in the earlier task receipt.
