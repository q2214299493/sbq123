# Scientific Problem Compiler · integration boundary

The inspected sibling checkout is `q2214299493/scientific-problem-compiler`. Its HEAD and remote main were both `44101f4752aadee459a7469b5b4d9e7b0d97d224`. Its working copy also contains unpublished changes, including models, workflow service, FT adapter and domain pack. The inventory below binds the actual working files. No SPC file, plan, run or export was created or modified.

## On-disk export

`GenericExportService.export` validates the domain/version, question plan, validation record, handoff and approvals. It refuses an existing destination, writes a staging package, verifies it and renames it into place. The root contains the following artifacts.

| Path | Exact payload or purpose |
|---|---|
| selected-plan.yaml, handoff-package.yaml | ScientificQuestionPlan and AgentHandoffPackage |
| task-graph.yaml | plan_id, plan_hash, tasks (ordered task IDs). Dependency edges live on individual tasks. |
| tasks/<task_id>.yaml | DAGTask fields plus source_plan_id, source_plan_hash, target_capability_binding, intent_fingerprint_ref, system_fingerprint_ref, method_fingerprint_ref, execution_policy and runnable set to false |
| fingerprints/<fingerprint_id>.yaml | Intent, system and method objects, each stored separately |
| approvals/plan-review.yaml, plan-validation.yaml, plan-gate.yaml, project-trust-policy.yaml (all in approvals/) | ApprovalVerdict, PlanValidationRecord, GateVerdict, ProjectTrustPolicy |
| approvals/approval-review-input.yaml, approvals/approval-review-record.yaml, approvals/independent-approval-receipt.yaml; provenance/plan-compilation-receipt.yaml | Conditional artifacts in the writer. A future SBQ123 intake must require proof of independent approval under its own trust policy. |
| capability-bindings.yaml, execution-policy.yaml | List of CapabilityBinding and one ExecutionPolicy, whose default mode is planning_only |
| evidence-manifest.jsonl, decisions.jsonl | Plan evidence references and human_selected decision with plan_id, plan_version and plan_hash |
| manifest.yaml, checksums.json | ExportManifest lists payload files before manifest creation. Checksums cover each file including manifest.yaml and exclude checksums.json itself. Plan content hashes and file-byte hashes have different domains. |

`workflow/service.py` owns planning, revision, approvals and recovery. `workflow/repository.py` handles locks, immutable/exclusive artifacts and safe path resolution. `downstream/adapter.py` defines map_capability, input_bindings, reconcile_outputs and resource_requirements. The inspected FTAgentAdapter targets ft-agent in ft-agent-staging, adapter version 1.1.0. The Fischer–Tropsch domain pack profile declares 1.0.2 and includes capabilities, workflow patterns and expert cases.

ResultEvidenceIntakeService verifies parent authority, submission artifact hashes and context, records an assessment, then materializes eligible evidence through curation and a receipt. Execution outcome, scientifically_admissible, materialization and successor planning are distinct. A future intake would check selected plan/version/hash, all payload checksums, passed gate and independent receipt, human selection, dependency closure, registered capabilities and planning-only payload. A future feedback sender would bind the accepted source artifacts and parent/task context. Neither adapter is installed by this work.

## Source identities

SHA-256 values below describe local bytes on the audit date.

- `src/spc/models.py` · `7fc5ba422f6842e3a325acb824e69d8ff1ea777ff70aeb6987641b4f45f15a4b`
- `src/spc/export.py` · `759932e85bf3535f171c22e6fdfb09ca1572715c23091bc8cf1885d5afc8ac16`
- `src/spc/workflow/service.py` · `e0d7103559d97942e108e2a720f3d9967bb408eaecd0efffc9f40815775bef83`
- `src/spc/workflow/repository.py` · `a03de84cf40a0eb2c291b93f9c8904807ecff95359adb2a0b0b674e1ebbbe7c0`
- `src/spc/result_feedback/service.py` · `9314a2369dc5314b68fd2480a44e359c9a231bb4b2b24aae70e6df05062582cd`
- `src/spc/downstream/adapter.py` · `49bf69db81a111d4c2e3cd7bd0394c2709bf73e57ac7484e2e0fb9771a7c0132`
- `src/spc/adapters/ft_agent.py` · `a1534f0eacedcdc6b5111cb65ce1d8f5e8eff18f6b0190455c62002c32935966`
- `src/spc/domain_packs/fischer_tropsch/capabilities.yaml` · `c94a70f61ae4c697ba016c7d786155f0873ee933c205917950926e208f5f0836`
- `src/spc/domain_packs/fischer_tropsch/expert_cases.yaml` · `1558103a36ee30630b0f1392352e18c1ed93cb55814070d4ce8fc81bd7f4fc79`
- `src/spc/domain_packs/fischer_tropsch/profile.yaml` · `1a5d72300117258ba13aa34466b6632137407adf5c501e3a4ef8e77d4e94923a`
- `src/spc/domain_packs/fischer_tropsch/workflow_patterns.yaml` · `140861f881dc9b2ba6ed03f9a545179be1fbcdbabe9b3dcdb96b3348bdb0a9f3`

## Model signatures

Declarations below come directly from the inspected model definitions. The digest for each full JSON Schema includes nested types, enums, required fields and constraints. To reproduce, call the named SPC model's `model_json_schema()`, serialize with Python `json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()` and take SHA-256. Executable cross-field checks remain in the pinned working sources.

### DAGTask

`models.py:482` · schema SHA-256 `0f540e1b290cdc21c3ac08973615e0a075adb4fad93a4fc39f32babe1dcf0062`

```python
task_id: str
scientific_objective: NonBlankStr
capability_id: str
inputs: dict[str, Any] = Field(default_factory=dict)
outputs: tuple[NonBlankStr, ...] = ()
depends_on: tuple[str, ...] = ()
success_criteria: tuple[NonBlankStr, ...] = ()
falsification_relevance: NonBlankStr
evidence_refs: tuple[str, ...] = ()
release_gates: tuple[str, ...] = ()
failure_policy: NonBlankStr
provenance_requirements: tuple[NonBlankStr, ...] = ()
cost_estimate: NonBlankStr = 'unknown'
runnable: bool = False
```

### ScientificQuestionPlan

`models.py:499` · schema SHA-256 `00e9e68d7bd969182cc28752e47d947eba2113a2d473be1dcb386595a888ac06`

```python
plan_id: str
version: str
domain: str
domain_pack_version: str
original_question: NonBlankStr
original_comment_id: str | None = None
latent_concern: NonBlankStr
atomic_questions: tuple[ScientificQuestion, ...]
hypothesis: Hypothesis
model: ModelDefinition
observables: tuple[ObservableDefinition, ...]
comparison_baselines: tuple[ComparisonBaseline, ...]
acceptance_criteria: tuple[AcceptanceCriterion, ...]
falsification_criteria: tuple[FalsificationCriterion, ...]
intent_fingerprint: IntentFingerprint
system_fingerprint: SystemFingerprint
method_fingerprint: MethodFingerprint
fingerprint_differences: tuple[FingerprintDifference, ...] = ()
evidence_refs: tuple[EvidenceReference, ...] = ()
assumptions: tuple[AssumptionRecord, ...] = ()
defaults: tuple[GroundedStatement, ...] = ()
unknowns: tuple[UnknownRecord, ...] = ()
proposed_deviations: tuple[ProposedDeviation, ...] = ()
scientific_capability_ids: tuple[str, ...]
tasks: tuple[DAGTask, ...]
distinguishing_axis: NonBlankStr | None = None
cost_tier: str
risks: tuple[NonBlankStr, ...] = ()
limitations: tuple[NonBlankStr, ...] = ()
required_human_decisions: tuple[RequiredHumanDecision, ...] = ()
source_query_manifest: tuple[NonBlankStr, ...] = ()
target_agent_capability_requirements: tuple[str, ...] = ()
wave_id: str = 'wave-1'
follow_up_of: str | None = None
source_proposal: str | None = None
```

### ApprovalVerdict

`models.py:713` · schema SHA-256 `964614fda08f0dbc8bef6473d745f679802d15b0e569ed0346e00379bf8696b7`

```python
verdict_id: str
candidate_id: str
candidate_version: str
candidate_content_hash: str = Field(pattern='^[0-9a-f]{64}$')
scores: ApprovalScores
hard_red_flags: tuple[NonBlankStr, ...] = ()
required_fixes: tuple[RequiredFix, ...] = ()
fix_resolutions: tuple[FixResolution, ...] = ()
human_decisions_required: tuple[str, ...] = ()
human_decision_resolutions: tuple[HumanDecisionResolution, ...] = ()
decision: ApprovalDecision
approver_id: str
created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### ApprovalReviewRecord

`models.py:4943` · schema SHA-256 `a4a9e1773fc39855d86231634486577841c0af53e33fd12b8e66c5e4d65f9ed6`

```python
review_id: NonBlankStr
review_input_id: NonBlankStr
review_input_hash: Sha256Str
provider_id: NonBlankStr
provider_version: NonBlankStr
provider_config: FrozenDict = Field(default_factory=FrozenDict)
response: ApprovalLLMResponse | RevisionApprovalLLMResponse
policy_decision: ApprovalDecision
policy_reasons: tuple[NonBlankStr, ...] = ()
content_hash: Sha256Str
```

### PlanValidationRecord

`models.py:729` · schema SHA-256 `bda30c1b9d02b11874aa9c387b03654fb705b8f7a1bb28c704002ad4b9abe4f0`

```python
validation_id: str
plan_id: str
plan_version: str
plan_content_hash: str = Field(pattern='^[0-9a-f]{64}$')
domain: str
domain_pack_version: str
valid: bool
issue_codes: tuple[str, ...] = ()
validator_version: str = '2.1.0'
```

### ProjectTrustPolicy

`models.py:741` · schema SHA-256 `f322da0771561a9fb7cbc06ec5543470c650010b81fe4e11472b6906e3a8f9f3`

```python
approval_mode: ApprovalMode
policy_version: NonBlankStr
```

### PlanCompilationReceipt

`models.py:4720` · schema SHA-256 `4a38a2f91afeb5adfbac3ff3ee27e77ae3ec219af2a7377c25ed4b0c0df9b79a`

```python
receipt_id: NonBlankStr
plan_id: NonBlankStr
plan_hash: Sha256Str
planning_input_id: NonBlankStr
planning_input_hash: Sha256Str
planning_proposal_id: NonBlankStr
planning_proposal_hash: Sha256Str
materializer_version: NonBlankStr
origin: NonBlankStr = 'phase2c_grounded_compiler'
content_hash: Sha256Str
```

### IndependentApprovalReceipt

`models.py:4971` · schema SHA-256 `f4c3f99126ffc501450d838843693ae32b8300f4d50963f5f9ad12bf9cc99e91`

```python
receipt_id: NonBlankStr
review_id: NonBlankStr
review_hash: Sha256Str
review_input_id: NonBlankStr
review_input_hash: Sha256Str
verdict_id: NonBlankStr
verdict_hash: Sha256Str
candidate_id: NonBlankStr
candidate_version: NonBlankStr
candidate_hash: Sha256Str
approver_id: NonBlankStr
provider_id: NonBlankStr
provider_version: NonBlankStr
content_hash: Sha256Str
```

### GateVerdict

`models.py:746` · schema SHA-256 `50e0f03f18f4008949531549b5249b234d5501542934f1672508a319956823f4`

```python
gate_id: str
candidate_id: str
candidate_version: str
candidate_content_hash: str = Field(pattern='^[0-9a-f]{64}$')
approval_verdict_id: str
approval_verdict_hash: str = Field(pattern='^[0-9a-f]{64}$')
plan_validation_id: str
plan_validation_hash: str = Field(pattern='^[0-9a-f]{64}$')
independent_approval_receipt_id: str | None = None
independent_approval_receipt_hash: str | None = Field(default=None, pattern='^[0-9a-f]{64}$')
trust_policy_version: str | None = None
trust_policy_hash: str | None = Field(default=None, pattern='^[0-9a-f]{64}$')
plan_compilation_receipt_id: str | None = None
plan_compilation_receipt_hash: str | None = Field(default=None, pattern='^[0-9a-f]{64}$')
passed: bool
reasons: tuple[NonBlankStr, ...] = ()
```

### CapabilityBinding

`models.py:3016` · schema SHA-256 `72ac0cde4b3c4f6c9002f45637188f36486023a0a30178c164a17fadec56d828`

```python
scientific_capability_id: str
target_capability_id: str | None = None
status: str
reason: NonBlankStr | None = None
```

### ExecutionPolicy

`models.py:3023` · schema SHA-256 `fa475fc8ad6822f98a336ca0aae19ace7438a0a04a908278bcf44aca31f4cf75`

```python
mode: str = 'planning_only'
runnable: bool = False
prohibited_actions: tuple[str, ...] = ('generate_execution_inputs', 'submit_jobs', 'execute_scientific_software')
```

### AgentHandoffPackage

`models.py:3033` · schema SHA-256 `ce74d4c66263db2ae072c7be0a41efbb4887afd9fff8eb218ce785c3cf913a91`

```python
export_id: str
target_agent: str
source_plan_id: str
source_plan_version: str
source_plan_hash: str = Field(pattern='^[0-9a-f]{64}$')
capability_bindings: tuple[CapabilityBinding, ...]
execution_policy: ExecutionPolicy
```

### ExportManifest

`models.py:3043` · schema SHA-256 `19ca3d0cea55716be0ae6cc3ad6d84b7a5f33cbe41559ecb53e0e92ec2d8e7c9`

```python
export_id: str
target_agent: str
source_plan_id: str
source_plan_version: str
source_plan_hash: str
files: tuple[str, ...]
```

### ResultArtifactManifestEntry

`models.py:5885` · schema SHA-256 `bdbdc50181d62047b017091888e3c0ec74accadce30ea1a12798c360eb40d67e`

```python
relative_path: NonBlankStr
sha256: Sha256Str
size_bytes: int = Field(ge=0)
media_type: NonBlankStr = 'application/octet-stream'
```

### ReportedObservable

`models.py:5892` · schema SHA-256 `08aa6141b97fe3bd9d3b0841accd4d66258bc9f05b8262eed69a82ba24a24cb2`

```python
observable_key: NonBlankStr
quantity: NonBlankStr
value: float | None = Field(default=None, allow_inf_nan=False)
qualitative_value: NonBlankStr | None = None
unit: NonBlankStr | None = None
uncertainty: NonBlankStr | None = None
result_status: ResultStatus
```

### ResultEvidenceSubmission

`models.py:5912` · schema SHA-256 `57757695e4a98786dc84b89060abfbdbbc3e40cf1d3e011b72f6e3920c2ad174`

```python
submission_id: NonBlankStr
parent_run_id: NonBlankStr
parent_plan_id: NonBlankStr
parent_plan_version: NonBlankStr
parent_plan_hash: Sha256Str
task_id: NonBlankStr
capability_id: NonBlankStr
export_id: NonBlankStr | None = None
export_manifest_hash: Sha256Str | None = None
execution_proposal_id: NonBlankStr | None = None
execution_proposal_hash: Sha256Str | None = None
executor_id: NonBlankStr
executor_version: NonBlankStr
result_type: ResultEvidenceType
system_fingerprint: SystemFingerprint
method_fingerprint: MethodFingerprint
declared_deviations: tuple[FingerprintDifference, ...] = ()
source_artifact_manifest: tuple[ResultArtifactManifestEntry, ...] = Field(min_length=1)
raw_artifact_checksums: FrozenDict
reported_observables: tuple[ReportedObservable, ...] = ()
uncertainty_metadata: FrozenDict = Field(default_factory=FrozenDict)
convergence_metadata: FrozenDict = Field(default_factory=FrozenDict)
execution_outcome: ResultExecutionOutcome
untrusted_interpretation: NonBlankStr | None = None
provenance_timestamp: datetime
content_hash: Sha256Str
```

### ResultContextComparison

`models.py:5994` · schema SHA-256 `4675d7f23354daef44b4d9783edbc376587bc64754fac92edc1762d7912229e9`

```python
comparison_id: NonBlankStr
submission_id: NonBlankStr
submission_hash: Sha256Str
parent_plan_id: NonBlankStr
parent_plan_hash: Sha256Str
status: ResultContextComparisonStatus
differences: tuple[FingerprintDifference, ...] = ()
approved_deviation_refs: tuple[NonBlankStr, ...] = ()
content_hash: Sha256Str
```

### ResultEvidenceAssessment

`models.py:6027` · schema SHA-256 `1af54052c45c47c49102dfc994695a03c096fe5f034f83fe28ce36eef5baf915`

```python
assessment_id: NonBlankStr
submission_id: NonBlankStr
submission_hash: Sha256Str
parent_run_id: NonBlankStr
parent_plan_id: NonBlankStr
parent_plan_hash: Sha256Str
task_id: NonBlankStr
capability_id: NonBlankStr
parent_authority_origin: NonBlankStr | None = Field(default=None, exclude_if=lambda value: value is None)
parent_authority_ref: NonBlankStr | None = Field(default=None, exclude_if=lambda value: value is None)
content_bound: bool
plan_bound: bool
context_compatible: bool
scientifically_admissible: bool
context_comparison: ResultContextComparison | None = None
issues: tuple[ResultIntakeIssue, ...] = ()
status: ResultEvidenceIntakeStatus
content_hash: Sha256Str
```

### ResultEvidenceMaterializationReceipt

`models.py:6076` · schema SHA-256 `66840f954544d8e13d2acf08fba493ddc3bdee93a4068fad511526c9469d17c1`

```python
receipt_id: NonBlankStr
submission_id: NonBlankStr
submission_hash: Sha256Str
assessment_id: NonBlankStr
assessment_hash: Sha256Str
curation_id: NonBlankStr
curation_hash: Sha256Str
parent_run_id: NonBlankStr
parent_plan_id: NonBlankStr
parent_plan_hash: Sha256Str
task_id: NonBlankStr
parent_authority_origin: NonBlankStr | None = Field(default=None, exclude_if=lambda value: value is None)
parent_authority_ref: NonBlankStr | None = Field(default=None, exclude_if=lambda value: value is None)
source_id: NonBlankStr
source_version: NonBlankStr
accepted_evidence_ids: tuple[NonBlankStr, ...]
reported_result_hashes: dict[NonBlankStr, Sha256Str] = Field(default_factory=dict)
reported_observation_hashes: dict[NonBlankStr, Sha256Str] = Field(default_factory=dict, exclude_if=lambda value: not value)
method_fact_hashes: dict[NonBlankStr, Sha256Str] = Field(default_factory=dict)
model_fact_hashes: dict[NonBlankStr, Sha256Str] = Field(default_factory=dict)
missing_observables: tuple[NonBlankStr, ...] = ()
content_hash: Sha256Str
```
