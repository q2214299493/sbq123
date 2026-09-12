# User-authorized bounded SCF diagnosis

2026-09-12 user: 继续这个解决方案

Accepted preceding proposal: one fixed-geometry SCF diagnosis at the original Dimer9749920 center using ALGO=Normal, preserving EDIFF=1e-7 and the physical branch; compare converged atom-resolved forces before considering transverse relaxation or Dimer. Submit one 80-rank VASP diagnostic on sunboquan-codex, NELM=200. NSW=0 and IBRION=-1 disable geometry optimization; Dimer-only tags removed. LORBIT=11 adds local magnetic projections. No automatic retry or Dimer restart.
