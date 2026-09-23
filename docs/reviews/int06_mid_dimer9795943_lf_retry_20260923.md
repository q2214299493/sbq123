# Dimer9795943: LF-only authorized retry

User request: 修正重新提交. One replacement for failed launcher9795633.

9795633 exited before VASP. Its 84-byte output identifies `/home_gkx/env/intel/intel2016.sh` with a trailing carriage return as missing. No OUTCAR, OSZICAR, DIMCAR or CONTCAR existed. This is a launcher-format error, not scientific path/SCF evidence.

Original files and failed remote directory remain unchanged. The new directory is `h_migration_int06_mid_vasp_bowed_20260921/dimer_peak03_lf_retry_20260923` under the same local calculation and remote TS roots. Only script.lsf changed by CRLF-to-LF conversion; all nine other preflight inputs/reviews retain their exact hashes. The preparation writer now explicitly requests LF. No geometry, MODECAR, MPI layout or VASP parameter change.

Local and remote bash syntax checks pass. Remote script has no CRLF marker; the Intel environment file exists. Script SHA256: `a25cd3c460ef7bf1e4724a1bf1c1a38bee10d5d0cd992bf6914e58efa121107d`. Canonical preflight passes; new file-bound gate permits START_DIMER for bundle `38778b926fab1c5bb303f6c56e7474f9d3e67b1e4f4a9be8e0b940dbaa3830b5`.

Executor returned9795943; first live checkpoint PEND. 80 ranks, ALGO Fast, EDIFF1e-7, EDIFFG-0.02, SIGMA0.20 and NSW300 unchanged. No pilot or extra job. Provenance registration covers new submission and old EXIT, not a scientific result. Next: verify actual launch/electronic progress after allocation. No guarantee of Dimer convergence is implied.
