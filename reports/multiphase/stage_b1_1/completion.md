# Stage B.1.1 · Versioned kinetic rate output

The new `kinetic-rate-output/2` reader accepts schema version `2.0.0`. The V1 and V2 readers are independent entry points. A V2 document binds its project, dataset and network versions, parameter set for each reaction, engine version, operating point, native rate basis, validity range, provenance and review status. The schemas reuse the existing reaction counts, artifact references, validation record and validity range.

## Meaning of the reported rates

One document uses one declared native denominator, including its quantity, unit, reference identity and definition. Each row carries nonnegative forward and reverse progress rates and their signed difference. For every named species, the validator reconstructs net production by summing the product-minus-reactant coefficient times net progress across the reactions. For every named site inventory it uses vacancies released minus consumed. Both retain the native time unit and denominator. Independent inventories keep their own IDs. Known cancellation produces an explicit zero.

The synthetic example has dissociation at net progress +2 and transfer at −1 per second per reference site pair. Its H2-g, H-alpha and H-beta sources are −2, +5 and −1. Its alpha and beta vacancy sources are −5 and +1. This example tests sign, multiplicity and independent inventories. Checking contract arithmetic and the presence of hash-bearing references grants no scientific or execution approval. File authentication and any conversion between normalization bases require separate evidence.

## Verification on Windows

The publication checkout started at `b463f4d01d0dff22a5319f6a9507bd1cb74821b6`. The development checkout retained its independent history at `233d5a6c589560094a0e942b6d48708b1fd5a847` and existing local changes.

| Check | Development | Publication |
| --- | ---: | ---: |
| V1 contract suite before the change | 76 passed | 76 passed |
| V2 contract | 56 passed | 56 passed |
| V1 multiphase contract | 76 passed | 76 passed |
| Kinetic parameters | 35 passed | 35 passed |
| Reaction network | 42 passed | 42 passed |
| MKM analysis | 29 passed | 29 passed |
| B7 release packaging | 17 passed | 17 passed |
| Maintained runtime graph acyclicity | 1 passed | 1 passed |
| Post-change focused suite, total | 256 passed in 18.92 s | 256 passed in 18.61 s |
| Modified Python files, py_compile and Ruff | Passed | Passed |
| Installed wheel check, four reader/input combinations | 4 expected exits | 4 expected exits |

Both focused suites had zero failures and zero skips. The full repository suite was outside this checkpoint. The V2 tests exercise missing or unknown versions, crossed and hybrid documents, duplicate JSON keys, unknown fields, incomplete provenance, signed arithmetic, small finite rates and zero cancellation. Both schemas passed Draft 2020-12 metaschema checks. Both installed wheels contained the source schema bytes. From an unrelated directory, the installed V1 and V2 readers each returned exit 0 for their own example and exit 1 for the other version.

Nine existing files in both trees matched the publication baseline byte-for-byte: the bundle, parameter, run, reaction, species and common schemas, the V1 reader and both V1 positive and negative fixtures. The task exercised synthetic contracts and packaging locally. It changed no native adapters, archived scientific results or production database.

## Changed files

- `configs/kinetics/rate_output_v2.schema.json` and `configs/kinetics/rate_source_terms_v2.schema.json` define the output document and its embedded source terms.
- `scripts/rate_output_v2.py` provides the V2 reader, read-only CLI and stoichiometric projection.
- `tests/test_rate_output_v2.py` and `tests/fixtures/multiphase/rate_output_v2.json` cover the new contract and version isolation.
- `MANIFEST.in` and `configs/release_resources.json` include the schemas in release packages.
- `modules/kinetic_data/multiphase_contracts.md` documents the fields, units and entry point.
- `reports/multiphase/stage_b1_1/completion.md`, `reports/multiphase/stage_b1_1/handoff.md` and `modules/state_handoff/events/history-stage-b1-1-kinetic-rate-output-v2-20261121.json` record the checkpoint and its pending review.

[Contract and CLI](../../../modules/kinetic_data/multiphase_contracts.md) · [State Handoff receipts](handoff.md)
