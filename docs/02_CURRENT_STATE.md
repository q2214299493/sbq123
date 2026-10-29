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
Submission completion2026-10-25:all280native jobs finished(prior250reviewed+final30DONE at10:56:42Beijing);12reused labels separate,unsubmitted0.Preserve264original+16human-authorized fresh directories and old unknown-marker resolution.Evidence:docs/reviews/fe110_reico_remaining_20261024/README.md.
Completed-label processing2026-10-25:all292selected labels reviewed,290PASS(train231/dev30/test29),two oldquarantines unchanged.Final30nativeQCPASS,registration279INSERT/30DONEprojectionUPDATE and30case readbacks pass;55related tests/30raw-label replays pass percheckout.No remaining unreviewed original labels;new joint auditview now485frames,original366trainingpackage unchanged.No DFT/GPU/training.Evidence:docs/reviews/fe110_final30_qc_20261025/README.md.
Evidence:docs/reviews/fe110_reico_label_qc_20261023/README.md.
Existing-source follow-up:10_B(job9848812) six lateframes264/272/280/288/295/296 pass per-frameSCF/raw-force/intactC2H3 checks;fmax0.019902-0.108471eV/A,4frames<=0.05.All6isolated from513reserved geometries(70same-composition) under actual clean-surface symmetry/all equal-element permutations;minimumadsRMSD1.28274A.10_A stays whole-job heldout.TotalM105.9810-105.9993muB,maxadjacentlatechange0.0034muB;no localmoment tables.Six independent LEGACY_TOTAL_MAGNETIZATION_ONLY force-supplement candidates retained under the existing20261019 trajectory scope,not merged into frozen packages or classified as local-moment-complete newstatics.Three historical C3jobs(9627285/9629858/9629859),458frames,contain no intactC3 frame withfmax<=0.05eV/A;9lowforce frames areCO+C2H2.9627285 finalSCF/ionic/branch/raw-force correspondence pass;localmoments absent and intermediateSCF not all reviewed.
Local evidence:calculations/fe110_reico_pilot300_20261022/status_lowforce_check_20261023_v1/checkpoint_summary.json.
Six-frame supplement:docs/reviews/fe110_10b_lowforce_20261023/README.md.
Combined force data package2026-10-27:local combined_force_package_20261027_v3 prepared;512train=366prior+119later-reviewed original statics+27recommended(11targeted SP+16trajectory),78dev/53heldout/16observed-heldout quarantine unchanged.659source labels and590ASE train/dev rows verified;publication adapter659/590checks PASS;65primary/33publication tests PASS.Magtiers258local-positive/248legacy-source/6total-only10B preserved;uniform1/512sampling;force-only energy_loss_coefficient=0;8hash-bound isolation proofs retained,513reserved geometries/0conflicts;no newgeometry/SOAP computation.Original366package/485audit hashes unchanged.Manifest ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee.No heldout.db/trainingrequest/newDFT/GPU/continuation/training.Jointcoverage now audited separately:178types/4SOAPoutliers;see2026-10-27coverage checkpoint.Evidence:docs/reviews/fe110_force_package_20261027/README.md.
Independent513label/444DBrow checks and release adapters pass;51primary/44release tests pass.No heldoutDB,executable trainingrequest,GPU,newDFT or training.Force-only/uniform-control recipe retained;C2H3has4lowforce trainingframes,C3H2Ostillnone.V1summary failure retained;v2is current.Evidence:docs/reviews/fe110_combined_force_package_20261023/README.md.
2026-10-24existing-label followup:19newDONE labelsQC PASS(12train/2dev/5test),total156PASS(124/20/12).At00:10:48Beijing,the79previously unadmitted receipt jobs were19DONE/4RUN/56PEND;training12DONE/4RUN/40PEND,65additional traininputs lack success receipts.No retries/newsubmissions.12newtrain labels pass1824symmetry comparisons against513reserved geometries;378frame auditview has284missingjoint types(vs296),fixed-thresholdSOAP gaps366(vs451).Frozen366package unchanged.C3H2O59frames still no lowforce;C2H3lowforce4still1job/1type.2pausedC3source candidates+2isolatedgeometry backups retained,none executed;42tests in each checkout and19real-label replays each pass.Evidence:docs/reviews/fe110_reico_followup_20261024/README.md.
Joint coverage update2026-10-27:512train against1597fixed trainpool;prior SOAP thresholds/forcebins/cutoffs unchanged.Joint gaps189to178(C2HO20/C2H2O25/C2H339/C3H2O94),11newly covered;65robust groups(79prior);175unselected+2quarantine-only+1failed targeted-label category.SOAP outliers4unchanged(1/0/0/3).C3H2O126train,minfmax0.0905703,0lowforce<=0.05;C2H3lowforce4still10B/onejointtype,total-only grade preserved.Reused1851caches/16newCPUdescriptors,4cache replays identical;512raw-force/1597pool/8nearest checks and58tests in each checkout PASS.Frozen512package,old366/485views,splits/magnetic tiers unchanged;no DFT/GPU/training.178types are diagnostic gaps,not178required calculations.One0099C3continuation now submitted separately as9924387;current512coverage unchanged.Evidence:docs/reviews/fe110_joint_update512_20261027/README.md.
C3 continuation submitted2026-10-27:human confirmed exact1job/32cores/max300additional steps/unchangedEDIFFG-0.02 andhistorical1526-2595corehourreference(notcap).NativeSUBMIT_VASP gate/executor succeeded once:job9924387,Gkn_normal,remote~/sbq/Fe110/reico_c3_continue_20261027_v1/family_0099_step020_from9922624.FirstexactIDLSFcheckpoint2026-10-27T04:34:19Z:PEND;noSCF/force/geometry/magnetic validity reviewed.Frozenpreparedbundleaa89bca075e3c6f3218971a4c2c938aadbf36cc35f58646ac10cf071aa794ef8 preserved;source9922624CONTCAR exact.Noautomaticretry/continuation/training.26metadataINSERT/0UPDATE,26readbacks/0scientificresults;207primary/192publicationtests PASS.512package/splits/magneticgrades unchanged.Next:user-requested checkpoint then completed-trajectory QC.Evidence:docs/reviews/fe110_c3_submission_20261027/README.md.
PairedDFT4 comparison2026-10-28:existing four jobs only;client recovery through18:24Beijing.10_Aold/new9925060/9925063 bothDONE80,finalfmax0.102388/0.035274,no0.02convergence;849/871SCF,433.812/577.779allocatedcorehours.Samegeometry MLfmax0.090451/0.088025 becomesDFT0.239860/0.226764;maxforceonmovableFe.C3fragmentdiagnosticsold9925062DONE80 fmax0.035146/722SCF/401.825corehours,new9925065RUN25auditedprefix fmax0.115549/281SCF;not intactC3success.All265frameSCF/local-positiveFe checks and4handoffcoordinate/rawvector checks PASS;40independentscalarchecks/47relatedtests PASS.No demonstratedfew-dozen-stepDFTconvergence orspeedup;no pureDFTbaseline/same-minimum proof.No continuation/retry/newcompute/training/promotion;512/78/53/magtiers unchanged.Next:existing train/dev near-equilibrium movable-Fe/adsorbate error diagnosis before a training-adjustment proposal;comparison data remain isolated.Evidence:docs/reviews/fe110_pair2_cost_comparison_20261028/README.md.
Grouped supplement QC2026-10-26:14jobs DONE/recovered;172frames reviewed,171PASS/1excluded(family_0021_step004,9922612,NELM200).All160trajectory frames pass per-frameSCF/localmoments/coordinate-force checks;both80step parents unconverged.2already-labelled starts excluded;169eligible/27recommended/142backup.171PASSvs513reserved:24120comparisons,0conflicts.138metadataINSERT/14DONEprojectionUPDATE,152readbacks/0acceptedresults;202primary/198publicationtests PASS.27recommended now included in new512frame package;oldrawQC/evidence unchanged.No retry/continuation/newcompute/training.Evidence:docs/reviews/fe110_grouped_qc_20261026/README.md;newpackage docs/reviews/fe110_force_package_20261027/README.md.
Scratch512 terminal review2026-10-28:sequence ended21:26Beijing/controllernotalive,NequIPproducerexit0;FTexit1/producer-15 at1800sbudget,not completed20epochs/no retry.23returned files hashverified;GPU1 UUIDGPU-450609b3-d1fd-ac33-d03a-79891be402da actualCUDA forboth,all savedmodeltensors finite.78dev role-weightedforcevectorMAE NequIP0.3190777691 versuspartialFT0.05564634551eV/A.NequiPbest/lastsavedepoch33/globalstep4352(finalepoch/stopreasonunestablished);FTlastsavedepoch9/step4608(bestepochunknown).902.185132/1802.071767s recordedarmspans,sequence2711.264202s<1GPUhour;FT30minspanoverrun2.071767sincludingdetection/exit.No autoextension.512/78/53+16isolation/magtiers unchanged,no modelpromotion/heldoutinference/newDFT.62relatedtests pass/1skip separatelyPASSinCPUenv;syntax/RuffPASS.Frozen candidates now selected for user-requested same-start speed pilot below;development lowforce/direction grouping remains backlog.Independentaccuracy/DFTspeedup unverified.Evidence:docs/reviews/fe110_scratch512_20261028/README.md.
Managed sync remains blocked by existing PKG-INFO;paired benchmark unchanged.


### Fe110 C3 source recovery — 2026-10-23

Known relative subdirectories are readable;9629858/9629859 outputs recovered with hashes. Both normal80step exits and finalSCFconverged,but ionicnotconverged,fmax0.860795/0.565336eV/A,bothCO+C2H2. No intactC3 frame below0.05eV/A among160steps. Localmoments missing;no accepted anchor,new job or model run. Evidence:docs/reviews/fe110_c3_source_recovery_20261023/README.md.

### Fe110 C3 targeted preparation — 2026-10-23

Two local revisedC3H2O graphs(05/07) pass geometry/custodian/canonical input gates;80steps,32cores each,LORBIT11,unchanged physical production branch. Local screen80_v2 only;no upload/submission/ML run. Historical two-job reference648-735corehours;real cost and intact near-equilibrium structures unverified. User explicitly asked to hold these two jobs;do not submit or resume without a new request. Evidence:docs/reviews/fe110_c3_targeted_relaxation_20261023/README.md.
Scratch512 speedpilot completed2026-10-28:userapprovedexact4ML/600sGPU1exclusive;newauthorizedrequestSHAce9d2fd5d34389824a01947d77879da9c8a9c5608074822d9387cce2a36a4e2d,24inputhashes/nativepreflightPASS.Onecontroller1413223/producer1413238,bothexit0,57.622616s;actualCUDAonGPU1.NequiPC2/C3=34/41steps,MLfmax0.094231/0.094423;partialFT=60/65steps,0.069361/0.077344.AllmeetML0.10only.C2initialgraphretained;bothC3fragmentCO+C2H2.MLpairadsorbateRMSD0.816039/0.944118A,notsameDFTminimumproof.29files/204frames/200steps/rawforce/fixedmask/source/endPOSCARauditPASS;maxfixed1.9e-15A,maxstep0.20A,mincontact>=1.0514A.All4diagnosticgeometryeligible,noscientificacceptance.PostrunGPU1free24065MiB/nocompute/ownedidentitiesgone,weightsunchanged.55relatedtestsPASS,syntax/RuffPASS.Original512/78/53+16/magtiersunchanged,noDFT/training/promotion/retry.Historical9848811useddifferentPOSCAR,114stepsnotexactbaseline.C2three-armDFTinputsnowpreparedbelow;C3diagnosticonly.NoDFTsubmissionauthorityoractualspeedupproof.Evidence:docs/reviews/fe110_scratch512_speed2_20261028/README.md.
C2three-armDFTcheckpoint2026-10-29:read-onlycheckat03:26:25Z(11:26Beijing);9926805directRUN/42completedionicsteps/861SCF/latestmovablefmax0.277208eV-A;9926806NequiPRUN/41steps/634SCF/0.393425;9926807FTDONE/69steps/586SCF/0.0183064,normalfooterandionicaccuracymarker,38937.788VASPseconds/346.113671allocatedcorehours(32ranks;queue/ML/trainingexcluded).NinePOSCAR-INCAR-KPOINTShashesunchanged.Tail6/6/7forceframespasscanonicalSCFandpositiveFelocalmomentreview;allcompletedOSZICARcyclesbelowNELM200.FullOUTCARtrajectorySCF/magneticreviewnotcompleted;notacceptedscientificresults.All3CONTCARsnapshotsretainC2H3graph/fixedFe0-17;FTfinalcoordinatesmatchrawforceprintingprecision.CC1.492512/1.437097/1.432212A.Latesttotalmoments107.1995/105.7614/105.4407muB;globalmagneticgroundstateunverified.Noaccelerationspeedupclaimuntilmatchedfinalminimareviewandcompletedcostcomparison.NoVASP/GPU/training/retry/continuation/otherjobchanges.Firstbroadreadtimedout;boundedtailsrecovered,remoteclockskewrecorded/localtransporttimeused.Evidence:calculations/fe110_reico_pilot300_20261022/c2_three_arm_submission_20261028_v1/tail_checkpoint_20261029T032549Z/audit.json.Next:remaining2on-demandcheckpoint,thenfullcompletion/same-minimum/costreview.

Fe110 11–15 NSW300 update2026-10-29:all15current VASP input bundles/90hashes verified;11_C/12_A RUN headers NSW300,other13PEND at 2026-10-29T07:23:43.403287+00:00. 13queued jobs retain IDs after held/exact-byte amendment/backup/readback/resume.11_A/11_B parents9927512/9927513 stopped normally at8/4steps;reviewed CONTCAR continuations9927793/9927794 useNSW300.EDIFFG-0.02/32ranks/allother physical settings unchanged.106release+11primaryrelatedtests PASS;213registryreadbacks/0scientificresults.Old parents needs_review;DFT convergence/minima unverified.No automatic retry.Next:on-demand DFT convergence/geometry review.Evidence:docs/reviews/fe110_c2_11_15_ft512_20261029/nsw300_update.md.
