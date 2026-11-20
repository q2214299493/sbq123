# Phase 3.2.3.1 — Fe(110) endpoint thermochemistry evidence audit

**No compatible IS or FS spectrum or precomputed correction was identified in the searched sources.** The original structures and electronic results were verified separately. The existing frequency evidence belongs to TS. Fe(110) MKM remains blocked. The necessity of either new endpoint calculation is undetermined. [Independent endpoint audits, missing fields and reference compatibility](missing_data.md) · [Structure hashes, TS review and intake decisions](endpoint_evidence.json)

## Search and candidate decisions

| Candidate for reuse | Structure identity | For IS | For FS |
|---|---|---|---|
| Native IS and FS relaxation outputs | Each final CONTCAR matches its own target byte for byte. The electronic OUTCARs have IBRION=2 and no frequency rows. | EXACT_MATCH for IS electronic data only; INCOMPATIBLE as an IS thermal source | EXACT_MATCH for FS electronic data only; INCOMPATIBLE as an FS thermal source |
| CHCO Hessian, job 2260 and its mirrors/preparation | Ordered coordinates coincide with the Dimer TS, SHA-256 0157a418…; its frequency input has separately verified SHA-256 c1b035d4… | INCOMPATIBLE | INCOMPATIBLE |
| Five other native Hessian systems/jobs on the VASP host | Independent POSCAR hashes match local evidence. The compositions are Fe45C2OH2 (two jobs), Fe45CH, Fe45CH2 or Fe45CO. | INCOMPATIBLE | INCOMPATIBLE |
| 13 local test copies | Fixture provenance; no assignment to either scientific endpoint | INCOMPATIBLE | INCOMPATIBLE |
| Li et al., Supporting Information, S1–S2, Table S1, reaction 15a | Same chemistry on a p(5×5) surface; the local model uses 3×3. The reported reverse barrier and reaction ZPE shifts (−0.05, −0.03 eV) are differences, not absolute endpoint values. | INCOMPATIBLE | INCOMPATIBLE |
| Published CO insertion on stepped Fe(710) | Different facet and site environment | INCOMPATIBLE | INCOMPATIBLE |

The full candidate table records paths, local input and output hashes, compositions, available active axes, mode counts, imaginary modes, threshold-free coordinate differences and per-endpoint classifications. Remote records are linked to local structures by hash. The current Fe registry was read with SQLite `mode=ro`: 694 calculations, 13,512 file rows, 1,647 results and 7 TS validation rows. The read-only inventory reproduced the prior Fe inventory. No registered endpoint correction was found. The scientific review of a relaxation establishes the electronic record within its scope. [Machine-readable candidate table and source inventory](candidates.json)

- Local file search covered calculations, outputs, data, artifacts, reports and reaction-specific archives. It screened 2,148 INCAR-like and 795 OUTCAR-like filenames, yielding 9 finite-difference/DFPT input hits and 24 outputs with mode/dynamical-matrix markers across 25 directories. Three XML dynamical-matrix hits belong to already-excluded systems. Seven targeted tar archives were checked for VASP and thermal members. The frequency archive contains the reviewed TS OUTCAR by byte hash.
- For exported corrections, 137 local structured/text files matched both a reaction/endpoint identifier and a thermal term. The scientific intake spectrum found there is `TS-spectrum`. The prior workbook's R05 explicitly requests IS/FS frequencies. The row contains no endpoint correction. Its historical registration statement and reversible arrow were not used to assign current barrier or reversibility status.
- Fresh read-only search of `sunboquan-codex:~/sbq/Fe110` inventoried 646 INCARs, 709 OUTCARs and six IBRION 5–8 inputs. All six candidate POSCAR hashes were compared. The additional mode-marker search of 97 OUTCARs without a sibling INCAR returned zero hits.
- Public searches covered reaction/facet terms and site-restricted catalysis/data archive results. The most relevant primary paper's archived 23-page supplement was inspected directly, including the reverse reaction and its geometry illustration. No researcher-supplied correction was attached or located in the scoped inputs. Private data, unindexed deposits, unrelated archives and unlabelled external files remain outside this finding. [Primary Fe(110) paper](https://doi.org/10.1021/acs.jpcc.8b10310) · [Supporting Information](https://doi.org/10.1021/acs.jpcc.8b10310.s001) · [Fe(710) paper](https://doi.org/10.1021/acs.jpcc.8b04265)

## Verification and handoff

The audit rehashed the source structures, electronic OUTCARs, endpoint reviews and TS frequency/review files, and reparsed job 2260's original signed modes. The formal Grade A record, mode 12 exclusion and local ZPE agree with Phase 2.2. Scientific Intake was evaluated for ZPE, thermochemistry and kinetic handoff. Each returns incomplete with independent IS and FS gaps; kinetic handoff returns blocked. The production SQLite file SHA-256 before and after read-only access was `4da73dbbc09fc697933cb6fa191493f78e0fbddb8863eadc66af082700fbe881`.

The 76 Scientific Intake and thermochemistry regression tests passed in each worktree. This audit adds evidence documents and an immutable history event. It changes no scientific code, data, grade, execution gate or registry row. No computation was submitted. The optional research assistant returned no recommendation because its scope argument was interpreted as a missing path. All conclusions above come from the direct audit.

**Next researcher decision.** Provide the intended temperature and surface standard state, and submit any per-endpoint reviewed correction or mapped signed spectrum through Scientific Intake. Review each endpoint independently before deciding whether to request a new frequency calculation.
