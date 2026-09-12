# Dimer9753172 stopped; SCF-test transfer diagnosis

User requested stop, then asked why Dimer failed although the fixed-geometry test converged. The canonical STOP_JOB gate and executor stopped9753172; scheduler confirmation is EXIT at2026-09-12T12:52:03Z. Existing outputs retained; no retry submitted.

SCF9752745 genuinely converged in96steps toEDIFF1e-7, normal completion, noBRMIX. Dimer9753172 instead exhausted200electronicsteps in its first force evaluation, then diverged again in the second. DIMCAR had no completed row. The reported7516.384017eV/A atomic force is numerically invalid for scientific interpretation. The last monitored stdout was about4.4GB with repeated non-Hermitian DAV subspace warnings.

Both remote POSCAR/POTCAR/KPOINTS hashes match exactly. OUTCAR headers show the same VASP5.4.1 build,80ranks,NCORE1,13irreduciblekpoints,NBANDS320,NELECT376,IALGO38,ISTART0,ICHARG2,NELMDL-5,AMIX0.4,BMIX1,AMIX_MAG1.6,BMIX_MAG1. Runtime differences include assigned nodes, Dimer ionic-method tags and LORBIT0 versus11. No evidence establishes one of these differences as the root cause.

The first10electronicsteps follow nearly the same energy sequence, then separate. At step20 staticSCF is-387.678eV whereas Dimer is-396.491eV; bystep30 staticSCF is-387.358eV whereas Dimer is-13596.196eV. Atstep21 Dimer stdout already reports BRMIX with inconsistent old/new charge density, followed by non-Hermitian subspace warnings. This is before any Dimer center movement. CENTCAR remains the original geometry; the later0.004889Å CONTCAR displacement is a Dimer trial displacement. A changed reaction geometry cannot explain the initial failure.

Both jobs cold-started; LWAVE/LCHARG were false, so no converged electronic restart state was saved or transferred. One successful cold-start static test demonstrated that this geometry can converge, not that every independent cold start or later Dimer geometry is stable. Earlier wording that Normal solved the problem was too broad. Sensitivity of the nonlinear SCF trajectory to initialization/numerical differences is a plausible explanation, not an isolated root cause or proof of faulty nodes.

Next investigation, requiring a new execution request: establish and save a reproducible converged electronic state at the identical original geometry; validate a restart using it before transferring to Dimer, while checking charge/magnetic mixing and effective settings. Do not merely raiseNELM or repeat the identical cold-start job. No further calculation is authorized by this stop request.
