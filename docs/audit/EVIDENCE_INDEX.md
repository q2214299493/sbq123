# Evidence index

Original source audit archive SHA-256 d2e2abfd0c59fa88ed43a94bbf4c0ad48c1029e49b6ae5113995d25a473c2028. Original V3.1 closure SHA-256 9e156ed294befc2c6ca99d5dd4538d5bd973bfbd33eb3680f1f5890c4bb938a4. Accepted Candidate 2 independent review SHA-256 b54a02dbf97bbee982318cbcdb63f16b8771a3b33080cbcc8a2ce54d0ea9c5ea.

* [Finding dispositions](FINDINGS.csv) reference original report rows. [All historical zip sites](ZIP_SITES.csv) record role, old expression, active location and treatment.
* [Source manifest](SOURCE_MANIFEST.csv) inventories active role paths, including evidence-only archive members, their assigned physical sources and original frozen identities. [Variant decisions](../../v31/variant-decisions.json) record recovery provenance.
* [Module responsibilities](../architecture/MODULE_MAP.md) and [actual imports](../architecture/IMPORT_EDGES.csv) describe the active projection.
* The detached review ZIP contains the Git patches and raw unsigned payloads, clean-clone and wheel verification, exact role JUnit, import lists, historical-ID comparison, receipt hashes, live Git status inventory and a SHA-256 manifest. It also includes the original source architecture audit for row-by-row comparison. The detached Git file inventory covers the entire proposed repository, including the inherited orchestration tree.

## CI correction artifact and workflow evidence

The release owner identified the uploaded correction ZIP by SHA-256 in the final blocker-closure request. Its digest matches the retained bytes and detached checksum. All 17 payloads and the internal checksum list were read independently. Applying each included patch to its own accepted commit in a fresh Git index produced the corresponding published tree. The earlier declared digest remains in the record; the bytes or reason for that earlier declaration are unknown.

The JSON below is the canonical, portable correction manifest. Hash its UTF-8 bytes with LF line endings, including the final newline inside the block. It binds the three audited CI correction heads. The later packaging commit is independently identified by the final PR and delivery receipt.

Manifest SHA-256: 348521ece1752edb4fe20c9846b3e9c589ef438c44fbe9d3b910818210a4139a.

~~~json
{
  "artifact": "SBQ123-V31-GitHub-CI-correction.zip",
  "authoritative_upload_sha256": "b9c6a38464e3f91249eb9e6c4187c092ce75c1fadead0445aba9593074e7621b",
  "authority": "Release owner identified the uploaded SHA in Final Release Blocker Closure (One-Pass); each patch independently reconstructs the registered remote Git tree.",
  "historical_declared_object": "Retained declaration; original bytes and cause of discrepancy unknown.",
  "historical_declared_sha256": "1555cec1b6afaa2584caf176e6ad902e985e86df6369410bd9b5aafb3017ae6f",
  "member_manifest_sha256": "0fb6badacd67cfdb6a827f765aeb94a0674d2567eba9ea3cb91fe25ff78146ad",
  "payloads": {
    "CI-CORRECTION.md": "36946c20a50064f28780b27d696e7b1159fc749c8983053c345fa1802a85cdbd",
    "evidence/C1.patch": "000d142693303a957ddcfa3c5d46eba401c609748877c8fae375af13f8832545",
    "evidence/C2.patch": "000d142693303a957ddcfa3c5d46eba401c609748877c8fae375af13f8832545",
    "evidence/C3.patch": "e306632efe4b9183d8e683f7cf3ff6cf7e1e76afaa08d0b046e29de9dd527da7",
    "evidence/c1-local.xml": "5b6267a315e28f5c2f82eb423c85a8b97f47ac6119aedee5e1f96c1ae3ac2295",
    "evidence/c3-local.xml": "0c3d9ccfece54a3e4fe419e3b1605c933e568c89b0eedfe9cff3b5f54b068212",
    "evidence/candidates.json": "c13d504675ce2ddef37110e44c52f07b8722b8a9385ba329a35d07eb7f66a6f0",
    "evidence/ci-latest.json": "ad2a964084a0bd1e9e13b68dd5112de77456ccaa710745d780b7297c050ea107",
    "evidence/final-ci.json": "28d00ad268242b41fdcfffbf66cc33025ae049491edac66cf15a663deead0334",
    "evidence/original-ci-failures.json": "e1025091dc149f28c80301fc8ca2c3a97ffbf93c0e9e3bd95c43a4176ea3bdcb",
    "evidence/original-readiness-drift.json": "824d627f5ef5ddb5250e88fc7772cc7f3f04e1bfcc316a633e71a14faf1d2953",
    "evidence/readiness.json": "197bdd22f2df541563f2fccdb01e593b5b12232bd7cbeb819b99bb6bc2534388",
    "evidence/receipt-hashes.csv": "b82e61fce6691a5206ce6013fcb64b4ba05b007106942861658ace5a42b205be",
    "registered/configs/state_handoff.yaml": "eaf6b017cb4014d1f246a7bc6d19faf3928806a2ec4ecc654e8845fed7652b73",
    "registered/docs/DOCUMENT_GOVERNANCE.md": "b42e5b7b7fb9fdeaeb722d4f599ea307a0b05ef85884c7a0ef0f78f9ccd18a11",
    "registered/reports/capability_readiness.json": "9e85971753963be116d58912be9fa1cb872514da4f4e7ef5632d4e6dab123b87",
    "registered/reports/capability_readiness.md": "2e985c5566517c4952b0c9e248eeb6dbfd43852c4230511f875e520c3222cc6b"
  },
  "schema": "sbq123-ci-correction-provenance/1",
  "stages": [
    {
      "accepted_commit": "79a2f353f14d501c024e11f2301707200141deb4",
      "accepted_tree": "e141244314bb3ef026c3bc165d810d202fa373f4",
      "ci_correction_head": "09234d74e5ddbd9d5f194b7d1d6a7f01d5d940d5",
      "parents": [
        "79a2f353f14d501c024e11f2301707200141deb4"
      ],
      "patch_sha256": "000d142693303a957ddcfa3c5d46eba401c609748877c8fae375af13f8832545",
      "pr": 15,
      "reproduced_tree": "b2ad69b1e1f5f9c49d59c4314268a04d871d405a"
    },
    {
      "accepted_commit": "5244831ef2ea7251a19cd580e08380852c2cc88a",
      "accepted_tree": "1b90114d41e2860231b246b86a2f13b0deba528d",
      "ci_correction_head": "fa6e138ab71869829a6cc94c57bbbbba46444c4a",
      "parents": [
        "5244831ef2ea7251a19cd580e08380852c2cc88a",
        "09234d74e5ddbd9d5f194b7d1d6a7f01d5d940d5"
      ],
      "patch_sha256": "000d142693303a957ddcfa3c5d46eba401c609748877c8fae375af13f8832545",
      "pr": 16,
      "reproduced_tree": "07c906e307300b5650ece0f8cc7a78d6e20021f2"
    },
    {
      "accepted_commit": "32142dbd506d8400e4394fd4e7d36b0bebeda734",
      "accepted_tree": "bc4bd6b70770994fa05a692b0cf873898092b89e",
      "ci_correction_head": "205ba3433a71448a7bf3e568f28c13ed248207cc",
      "parents": [
        "2deeefe077ae5b6c2b18b282c5903d03c4d31422"
      ],
      "patch_sha256": "e306632efe4b9183d8e683f7cf3ff6cf7e1e76afaa08d0b046e29de9dd527da7",
      "pr": 17,
      "reproduced_tree": "f5dc62c234dc101070842602119e39493420350b"
    }
  ]
}
~~~

### All workflows on the three CI correction heads

| PR | Event | Workflow run | Successful jobs |
|---|---|---|---:|
| #15 | pull_request | [45841296036](https://github.com/q2214299493/sbq123/actions/runs/45841296036) | 5 |
| #15 | push | [45841287489](https://github.com/q2214299493/sbq123/actions/runs/45841287489) | 5 |
| #16 | pull_request | [45841295541](https://github.com/q2214299493/sbq123/actions/runs/45841295541) | 5 |
| #16 | pull_request | [45841294917](https://github.com/q2214299493/sbq123/actions/runs/45841294917) | 5 |
| #16 | push | [45841287455](https://github.com/q2214299493/sbq123/actions/runs/45841287455) | 5 |
| #17 | pull_request | [45841297751](https://github.com/q2214299493/sbq123/actions/runs/45841297751) | 5 |
| #17 | pull_request | [45841294787](https://github.com/q2214299493/sbq123/actions/runs/45841294787) | 5 |
| #17 | push | [45841287648](https://github.com/q2214299493/sbq123/actions/runs/45841287648) | 5 |

All eight runs completed successfully, with 40 successful jobs. Each had validate, engineering on Ubuntu and Windows, and wheel on Ubuntu and Windows. PR events used GitHub's test merge and push events used the branch tip. The earlier narrative selected six runs and 30 jobs; the other two PR events tested the same merge objects as their respective PR counterparts. This count is scoped to the historical heads above. Later packaging CI and historical scientific regressions have their own evidence.
