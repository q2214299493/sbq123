# VASP Output Inspection

Use targeted, bounded inspection. File existence or scheduler `DONE` never
proves scientific convergence.

## Inputs

After checking file size and type, preview small VASP inputs with byte caps:

```bash
sed -n '1,160p' INCAR 2>&1 | head -c 4000
sed -n '1,120p' KPOINTS 2>&1 | head -c 4000
sed -n '1,180p' POSCAR 2>&1 | head -c 4000
sed -n '1,180p' CONTCAR 2>&1 | head -c 4000
sed -n '1,120p' POTCAR.spec 2>&1 | head -c 4000
```

Check INCAR, KPOINTS, POSCAR/CONTCAR, job script, POTCAR metadata/order,
Selective Dynamics, atom order, and compatibility with the active method branch.

## Outputs

Never dump full `OUTCAR` or `vasprun.xml`. Use compact tails for small text
outputs and targeted OUTCAR searches:

```bash
tail -n 100 OSZICAR 2>&1 | head -c 4000
tail -n 120 stdout* 2>&1 | head -c 4000
tail -n 120 *.err 2>&1 | head -c 4000
grep -E "reached required accuracy|aborting loop|DAV:|RMM:|F=|E0=|mag|NEB|FORCES|RMS|EDIFF|EDIFFG|ZBRENT|BRIONS" OUTCAR 2>&1 | head -c 4000
```

Verify separately:

- scheduler state;
- electronic convergence and fatal errors;
- ionic step and force convergence;
- final structure existence and geometry;
- reported energy and compatible reference branch;
- scientific validity under the owning module.

## NEB

Follow `modules/transition_state_search/README.md`. Inspect every image without dumping
full outputs:

```bash
find . -maxdepth 2 -type f \( -name "INCAR" -o -name "KPOINTS" -o -name "POSCAR" -o -name "CONTCAR" -o -name "OSZICAR" -o -name "OUTCAR" \) 2>&1 | head -c 4000

for d in 00 01 02 03 04 05 06 07 08 09; do
  if [ -f "$d/OSZICAR" ]; then
    echo "===== $d/OSZICAR ====="
    tail -n 5 "$d/OSZICAR"
  fi
done 2>&1 | head -c 4000
```

Check all images, endpoint constraints, climbing-image use, force and energy
profile, collisions, image jumps, atom order, and fixed-atom drift. Run
`dist.pl` and `nebmovie.pl 0` before approval/submission and `nebmovie.pl 1`
after completion or stopping.

## DIMER

Follow `modules/transition_state_search/README.md`. Check the strategy-approved DIMER INCAR,
DIMCAR progress, final forces and curvature, CENTCAR/NEWMODECAR, inspected mode,
and connection to the intended endpoints. Do not claim success from a
header-only DIMCAR, scheduler completion, or saddle-search convergence alone.
