# MM-002 Extracted Notes

## Verified Directly

- CO bridge/hollow/top and C+O coadsorption OUTCAR files reached required accuracy; final TOTEN values match the workflow reference.
- Molecular A endpoint and dissociated D endpoint have non-empty CONTCAR files and reached required accuracy.
- Active NEB 00/09 endpoint checks report `0.000 A` maximum geometry deviation.
- Bulk/slab ENCUT and k-mesh CSV summaries match the recorded `<=1 meV/atom` recommendations.
- Smearing, vacuum, and thickness summary rows are marked finished.

## Qualified Records

- Clean Fe(110) and gas CO reference energies are retained from the workflow reference, but their raw OUTCAR directories were not found during this batch.
- Adsorption energies were recalculated consistently from the retained references, but inherit the clean/gas verification limitation.
- Extra convergence total energies alone do not justify a final smearing or slab-thickness choice; thickness requires normalized surface-energy analysis.

## Excluded

- transient submission status
- unverified intermediate energies
- conclusions not supported by the copied CSV summaries
