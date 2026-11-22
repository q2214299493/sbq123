# F1.2 · Read-only research project inspection

A researcher can inspect a project/task YAML pair with the existing Scientific Intake command. The JSON report identifies the objective and catalyst, the scoped network and operating conditions, verified sources, missing evidence, per-observable readiness and the independent MKM/KMC input gates.

```powershell
$case = 'reports/workflow_design/stage_f1_2/fe110'
python -m scripts.scientific_intake --inspect-project "$case/project.yaml" "$case/task.yaml"
```

**Baseline.** The remote F1.1 head was `89d140deecb2dee1cc96796ac2d9e0c831a045b7`. Git confirmed ancestry from `6dbc0fb35223cc832abc2fc19bc0ca6de54f4411`. Work used an isolated descendant branch, `codex/f1-2-project-inspector`.

**Implementation.** The opt-in CLI reads the same human-facing project and task layout used by the historical CO-dissociation project. Explicit named references, optional catalog, and reaction/operating-point contexts are described in the [intake reference](../../../modules/kinetic_data/scientific_intake.md). The positional reaction interface still calls the same implementation. Its functions moved intact into Kinetic Data so that the project CLI can call higher-level domain owners without introducing a reverse import from those owners to the CLI.

A source digest is checked against the exact bytes before reading scientific content. Network and kinetic versions, catalog ownership, source and result identity, archived run/plan bindings, and strict V2.1 rate qualification use their existing owners. The inspector calls the existing balance, thermal-intake, input qualification, bridge topology and receipt checks. It reports the archived values, including nulls, with their source roles. Inspection uses no database connection or native launcher.

## Offline acceptance outputs

| Runnable project/task | Verified boundary | Canonical stdout |
| --- | --- | --- |
| [Fe(110) project](fe110/project.yaml) · [task](fe110/task.yaml) | Recognizes IS, TS and FS with validated structure identities. Electronic energies −385.14767079, −384.17406905 and −384.48836276 eV. Forward, reverse and reaction differences +0.97360174, +0.31429371 and +0.65930803 eV. TS-local ZPE 0.51405165 eV. Missing endpoint corrections, temperature and standard state leave three Gibbs differences unknown. MKM and KMC export blocked. | [Fe evidence and gaps](fe110/inspection.json) |
| [Ni/Cu project](nicu/project.yaml) · [task](nicu/task.yaml) | Synthetic benchmark at 400 K. Native rates retain the reference-site-pair denominator. Archived TOF 81.51277016 s⁻¹ on its declared turnover basis. Stable DRC ranks hydrogenate 0.45025755 and transfer 0.04069045. Rate uncertainty was unmeasured. CATKINAS inputs pass offline qualification. | [Ni/Cu evidence and conditions](nicu/inspection.json) |
| [Synthetic oxide project](oxide/project.yaml) · [task](oxide/task.yaml) | Seven nodes, two bound CO₂ molecules, two of four acid sites and two of three oxygen sites occupied. The consumed original plan failed during native initialization with code 1002. Five native files match the corrected manifest. No successful receipt establishes native qualification of that candidate. | [Oxide topology and receipts](oxide/inspection.json) |

Each output was regenerated twice using the public CLI in the publication-based feature checkout. Replays were byte-identical after normalizing Windows stdout line endings to LF. Fe's raw source files are absent in this checkout. A second read-only inspection with an explicitly declared development evidence base found exact matches for all three CONTCARs and three electronic OUTCARs. That base lacks the later V.1.2.1 prose review, which was reported as a missing local file. Neither inspection searched for replacements.

## State Handoff

The State Manager recorded pending proposal `proposal-aa983f4829d6f1cfc52b1127` for the [F1.2 history event](../../../modules/state_handoff/events/history-f1-2-readonly-project-inspection-20261122.json). It binds the three published acceptance outputs and requests human review of the history projection. The proposal was neither approved nor applied.

The initial repository audit reported pre-existing module-map drift. The end-of-task `sync --safe-only` returned code 2 with `state history source changed before proposal generation`. Its before/after check found identical file sets and SHA-256 values across 354 event/cache and selected projection files. The explicit F1.2 proposal had already been created independently. [Regression, scope and changed files](regression.md)
