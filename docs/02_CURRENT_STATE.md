---
document_class: CURRENT_AUTHORITY
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: CURRENT_CODE_STATE_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Current State

## Authority and scope

This is a source/publication entry point, not a live monitoring report. Governance
is defined in [DOCUMENT_GOVERNANCE.md](DOCUMENT_GOVERNANCE.md). The development
checkout is `C:/Users/86177/Desktop/work`; this branch is an isolated publication
worktree based on B5. No scheduler or production database was queried in B6.

## Active Scientific Branch

The selected protocol is the corrected true Fe(110) five-layer branch,
`true_fe110_5layer_5x5x1`, as recorded in
[method protocol](01_METHOD_PROTOCOL.md) and
[production profile](../configs/true_fe110_production.yaml).
Compatible final OUTCAR TOTEN uses the existing
`fe110_converged_toten_sigma0p20_v1` convention. No thresholds or parameters
were changed. Source configuration establishes the selected method, not a newly
completed calculation or a deployment observation.

## Implemented software and registry scope

CURRENT_CODE_STATE: B1-B5 implementations and 1054 passing software tests at B5
are recorded in the [B5 report](../reports/refactor_audit/B5_completion_report.md).
Execution gates, VASP/contract parsing, evidence/data gates and registry lifecycle
remain separate authorities. [Module status](06_MODULE_MAP.md) owns status;
[derived readiness](../reports/capability_readiness.md) does not own it.
SUPPORTED_CODE_SCHEMA: 9, from [registry schema code](../scripts/registry_schema.py).
production_schema_version: NOT_VERIFIED_IN_B6. HISTORICAL_SCHEMA: version 8
statements and counts are preserved in the chronology, not a deployment claim.

## Latest recorded scientific/workflow gate

LAST_RECORDED_OBSERVATION: the B5 module map records Dimer `9746548` after
ordinary NEB `9745217` review. Last recorded scheduler status: PEND;
observed_at: 2026-09-07T11:15:50Z; source: [module map](06_MODULE_MAP.md).
This is later than the retained managed snapshot below; neither is live evidence.
The [task projection](../tasks/current_task.md) is also a recorded snapshot and
must be reconciled against the development task before any new scientific action.

## Explicitly not established

PRODUCTION_UNVERIFIED: present queue state, production schema/deployment and
current evidence availability. PREDICTION_ONLY: GPU/ML candidates do not establish
accepted TSs, barriers or final adsorption minima. SCIENTIFICALLY_ACCEPTED labels
in older records describe their original reviewed scope only; B6 did not revalidate
them. Software test success does not establish scientific or production readiness.
Planned/Blocked kinetic modules remain as listed in the module map.

## History and provenance

The [preserved chronology](history/current_state_chronology_before_B6_20260909.md)
contains the former long sections, including the UTF-8 C/C2/O site labels.
The earlier [TS history](history/active_fe110_co_dissociation_history_through_20260803.md)
remains canonical for its original period. Root FINAL/PHASE reports are classified
historical snapshots; filenames do not establish authority or freshness.

## Active Transition-State Gate

LAST_RECORDED_OBSERVATION: retained state-manager projection, dated 2026-08-27
(local document date; no exact observation time supplied). This historical managed
block is preserved verbatim for projection compatibility, not selected as the
latest observation. Its scientific claims are not revalidated in B6.

<!-- state-handoff:start active-fe-110-co-dissociation-test-current-gate -->
### Active Gate - 2026-08-27 GPU Job 1327 Failed; Revised Path Design Required

- Held-out VASP jobs `9731537`-`9731543` are `DONE` and quality-passed; frozen MatRIS passed the six-structure primary held-out gate, while AQCat25 remains a force/geometry auditor.
- MZ73 job `1327` produced exit code `1` during restrained preconditioning step `9`, before ordinary MatRIS ML-NEB and before the AQCat25 fixed-path audit.
- The required forming O-H `1.1-1.8 A` coverage fell from five to two internal images; at least three were required, so the geometry guard correctly stopped the run.
- O-H monotonicity, C1-C2 preservation, adjacent RMSD, maximum movable-atom step, minimum pair distance, and periodic-branch checks still passed.
- No complete GPU path, Dimer parent, VASP result, TS, barrier, fine-tuning, automatic retry, or resubmission exists.
- The completed seven-job VASP batch remains accepted held-out evidence; job `1327` is a separate failed GPU path attempt and does not invalidate that batch.

Next action: Prepare and review a revised preconditioning or resampling design that preserves at least three O-H interval images; require new explicit authorization before any rerun.
<!-- state-handoff:end active-fe-110-co-dissociation-test-current-gate -->

### Fe110 random-sampling dataset checkpoint — 2026-10-24

All99 local families sampled;1995frames→292selected(train233/dev30/test29),
including12 reusedDFTlabels.280newstatics now all have native success receipts(264original directories+16human-authorized fresh recovery directories);original16unknown markers retained with resolution mapping.
Latest submission checkpoint2026-10-24T15:07:51+08:00:76new submissions(60original-directory+16fresh-directory) queried13DONE/4RUN/59PEND;accountRUN128/MAX128.Previous204queue states not re-queried.All280inputs/current preflights/gates/native receipts verified;remaining logical unsubmitted0.76jobs registered1453INSERT/0UPDATE;no new result acceptance.Evidence:docs/reviews/fe110_reico_remaining_20261024/README.md.
Completed-label processing2026-10-24:at16:48:16Beijing,136previously unreviewed jobs84DONE/4RUN/48PEND;collect84in20/20/20/20/4batches,82PASS(62train/7dev/13test),1magnetic-review and1SCF-NELM-boundary rejection,bothC3H2Otrain.Cumulative240reviewed/238PASS(186train/27dev/25test).62newtrain pass9018symmetry/permutation comparisons against513reserved geometries,zero conflicts.No newlowforce<=0.05eV/A labels.Frozen366package/prior378view retained;new440jointaudit is current.No training/newDFT.84statuses+681files registered with71reviewed workflow DONE projections;43tests pass in each checkout.Evidence:docs/reviews/fe110_completed_label_qc_20261024/README.md.
Evidence:docs/reviews/fe110_reico_label_qc_20261023/README.md.
Existing-source follow-up:10_B(job9848812) six lateframes264/272/280/288/295/296 pass per-frameSCF/raw-force/intactC2H3 checks;fmax0.019902-0.108471eV/A,4frames<=0.05.All6isolated from513reserved geometries(70same-composition) under actual clean-surface symmetry/all equal-element permutations;minimumadsRMSD1.28274A.10_A stays whole-job heldout.TotalM105.9810-105.9993muB,maxadjacentlatechange0.0034muB;no localmoment tables.Six independent LEGACY_TOTAL_MAGNETIZATION_ONLY force-supplement candidates retained under the existing20261019 trajectory scope,not merged into frozen packages or classified as local-moment-complete newstatics.Three historical C3jobs(9627285/9629858/9629859),458frames,contain no intactC3 frame withfmax<=0.05eV/A;9lowforce frames areCO+C2H2.9627285 finalSCF/ionic/branch/raw-force correspondence pass;localmoments absent and intermediateSCF not all reviewed.
Local evidence:calculations/fe110_reico_pilot300_20261022/status_lowforce_check_20261023_v1/checkpoint_summary.json.
Six-frame supplement:docs/reviews/fe110_10b_lowforce_20261023/README.md.
Combined force data package prepared locally:calculations/fe110_reico_pilot300_20261022/combined_force_package_20261023_v2;366train(248legacy+112statics+6late10_B),78dev,53heldout,16oldobserved-heldout quarantined.48894applicable full-symmetry comparisons against513reserved geometries found0conflicts;original partitions retained.Both manifest and train/dev DBs preserve magnetic tiers;10_B remains total-only.
Independent513label/444DBrow checks and release adapters pass;51primary/44release tests pass.No heldoutDB,executable trainingrequest,GPU,newDFT or training.Force-only/uniform-control recipe retained;C2H3has4lowforce trainingframes,C3H2Ostillnone.V1summary failure retained;v2is current.Evidence:docs/reviews/fe110_combined_force_package_20261023/README.md.
2026-10-24existing-label followup:19newDONE labelsQC PASS(12train/2dev/5test),total156PASS(124/20/12).At00:10:48Beijing,the79previously unadmitted receipt jobs were19DONE/4RUN/56PEND;training12DONE/4RUN/40PEND,65additional traininputs lack success receipts.No retries/newsubmissions.12newtrain labels pass1824symmetry comparisons against513reserved geometries;378frame auditview has284missingjoint types(vs296),fixed-thresholdSOAP gaps366(vs451).Frozen366package unchanged.C3H2O59frames still no lowforce;C2H3lowforce4still1job/1type.2pausedC3source candidates+2isolatedgeometry backups retained,none executed;42tests in each checkout and19real-label replays each pass.Evidence:docs/reviews/fe110_reico_followup_20261024/README.md.
Joint coverage update2026-10-24:378+62isolatedPASS train=440frames against1597trainpool;originalSOAP thresholds/force bins/cutoffs fixed.Joint gaps284to229(C2HO26/C2H2O38/C2H340/C3H2O125);SOAP gaps366to68(1/10/0/57).229groups=40linkedto45unreviewed selectedtrain+2linkedonlytoquarantines+187unselected types.Conditional45pass leaves189,not187;twoquarantinesexcluded.C3H2O84frames stillminfmax0.659006,no<=0.05;C2H3lowforce4stillone10Bjob/type.32tests and440raw-force-bin/8SOAP-distance checks pass in eachcheckout.Original366package and magnetic grades/partitions unchanged;no training/newDFT.Evidence:docs/reviews/fe110_joint_update_20261024/README.md.
Managed sync remains blocked by existing PKG-INFO;paired benchmark unchanged.


### Fe110 C3 source recovery — 2026-10-23

Known relative subdirectories are readable;9629858/9629859 outputs recovered with hashes. Both normal80step exits and finalSCFconverged,but ionicnotconverged,fmax0.860795/0.565336eV/A,bothCO+C2H2. No intactC3 frame below0.05eV/A among160steps. Localmoments missing;no accepted anchor,new job or model run. Evidence:docs/reviews/fe110_c3_source_recovery_20261023/README.md.

### Fe110 C3 targeted preparation — 2026-10-23

Two local revisedC3H2O graphs(05/07) pass geometry/custodian/canonical input gates;80steps,32cores each,LORBIT11,unchanged physical production branch. Local screen80_v2 only;no upload/submission/ML run. Historical two-job reference648-735corehours;real cost and intact near-equilibrium structures unverified. User explicitly asked to hold these two jobs;do not submit or resume without a new request. Evidence:docs/reviews/fe110_c3_targeted_relaxation_20261023/README.md.
