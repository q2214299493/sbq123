# Project Skill Routing

`configs/skill_routing.yaml` is the machine-readable authority for skill ownership.

| Skill | Role |
|---|---|
| `catalysis-data-retrieval` | Sole pre-calculation external structure/path/data retrieval owner |
| `vasp-catalysis-workflow` | Routes VASP tasks to repository modules |
| `surface-adsorption-builder` | Builds reviewable adsorption candidates from accepted/local evidence |
| `fe110-adsorbate-pilot-builder` | Builds and checks small true Fe(110) adsorption pilot batches before full expansion |
| `chemical-plausibility-gate` | Classifies the final chemical species/event before result promotion |
| `dataset-compatibility-gate` | Decides whether results are comparable, promotable to registry/Excel, or blocked |
| `neb-path-builder` | Builds and checks NEB paths from accepted/local evidence |
| `fe-vasp-incar-custodian` | Reviews INCAR only after scientific geometry/path gates pass |

General literature, paper-reading, and academic-writing skills are explicit scholarly tools. They are not calculation inputs or automatic fallbacks.
