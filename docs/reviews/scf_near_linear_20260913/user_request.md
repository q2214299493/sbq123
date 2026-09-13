# Approved fixed-geometry SCF near-linear-mixing control

2026-09-13: User requested "继续提交" after review of this exact proposal:
retain SCF9754110 AMIX=0.2 and AMIX_MAG=0.8, change only BMIX and BMIX_MAG
from effective defaults 1.0 to 0.0001. Preserve geometry, physical settings,
ALGO Normal, EDIFF=1e-7, NELM=200, 80 MPI ranks and existing node exclusion.
Use a fresh cold-start directory and save WAVECAR/CHGCAR. Submit one
diagnostic_static job on sunboquan-codex through the current bound gate.
No subsequent retry, restart-validation calculation or Dimer is authorized.

Scientific rationale: SCF9754110 approached the successful SCF9752745 energy
before late divergence. Runtime headers agree on VASP build, ranks, band
distribution, NBANDS and initialization; full runtime environment equivalence
and root cause remain unproven. This is a controlled hypothesis, not a claim
of guaranteed convergence. Official source: https://vasp.at/wiki/index.php/AMIX_MAG
Completion requires EDIFF, normal termination, valid saved state and comparison
of energy, force and magnetic state with SCF9752745. Do not use failed outputs
as new input structures or electronic restart files.
