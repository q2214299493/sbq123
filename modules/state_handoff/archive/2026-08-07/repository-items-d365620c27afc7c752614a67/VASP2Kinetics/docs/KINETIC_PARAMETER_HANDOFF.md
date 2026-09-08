# Reviewed Kinetic Parameter Handoff Contract

## Purpose

This contract records an already calculated and manually reviewed reaction
energy and forward/reverse activation barrier. It is the proposed boundary
between scientific result acceptance and later CATKINAS/Zacros conversion.

It does not calculate energies, identify a transition state, alter a kinetic
dataset, or make a simulator input executable.

Normative schema:
`schemas/kinetic_parameter_handoff.schema.json` (Draft 2020-12, version 1.0.0).

Blank non-eligible template:
`examples/kinetic_parameter_handoff.template.json`.

## Lifecycle

```text
DRAFT -> REVIEW_PENDING -> APPROVED
                         -> REJECTED
APPROVED -> SUPERSEDED
```

Only an `APPROVED` handoff whose validator result has `eligible: true` may be
considered by a future adapter-import step. Every other state is blocked.

## Required scientific content

An approved handoff contains:

- exact kinetic-dataset file SHA-256 and canonical reaction-record SHA-256;
- one energy basis (`ELECTRONIC_ENERGY` or `GIBBS_FREE_ENERGY`);
- explicit `eV` unit and reference/energy convention;
- initial, final, verified transition-state, reaction, forward-barrier, and
  reverse-barrier values;
- per-value source IDs and extraction method;
- VASP version, XC, pseudopotential family/specification hash, ENCUT, KPOINTS,
  spin, smearing, EDIFF, slab, fixed-mask hash, dipole, vacuum, and
  compatibility fingerprint;
- hashed initial/final/TS energy files, frequency evidence, connectivity
  evidence, automated validation report, and manual review evidence;
- separate electronic, ionic, geometry, and scientific states for IS/FS/TS;
- Grade-A TS, passed frequency/connectivity/method compatibility, and an
  identified human reviewer with timestamp and rationale.

For `GIBBS_FREE_ENERGY`, positive temperature and pressure are mandatory. For
`ELECTRONIC_ENERGY`, both fields must be null so that a temperature-dependent
quantity cannot be implied.

## Energy invariants

All six values use the same basis, unit, reference convention, and compatible
method fingerprint. The validator checks within `consistency_tolerance_eV`:

```text
reaction           = final - initial
activation_forward = transition_state - initial
activation_reverse = transition_state - final
```

NaN and Infinity are always invalid.

## Hash and path rules

- SHA-256 strings are lowercase 64-character hexadecimal values.
- Relative paths resolve from the handoff JSON directory.
- `LOCAL` files are rehashed and their byte sizes are checked.
- `REMOTE` and `ARCHIVE` sources must carry verified hashes but cannot be
  independently rehashed by the local validator; this produces a warning.
- Reaction-record hashing uses UTF-8 canonical JSON with sorted keys, compact
  separators, `ensure_ascii=false`, and `allow_nan=false`.

## Validation command

```powershell
python -m src.kinetics.handoff path\to\kinetic_parameter_handoff.json
```

Exit codes:

- `0`: approved and eligible;
- `1`: structurally valid but not approved/eligible;
- `2`: invalid contract, hash mismatch, evidence failure, or read error.

## Integration boundary

The current workflow and adapters do not consume this file. A later,
separately reviewed integration must:

1. revalidate the handoff immediately before use;
2. reject every result except `eligible: true`;
3. bind the import to the exact dataset and reaction-record hashes;
4. write a new auditable dataset version rather than overwrite an old record;
5. preserve the full handoff and validation result with adapter outputs.

The handoff is an upstream evidence envelope, not a replacement for formal
kinetic-data tables. Promotion must create accepted species/energy/reaction/
barrier records with units and provenance before any MKM/KMC export. A handoff
that is merely `APPROVED` but has not been promoted remains unusable by
CATKINAS or Zacros.

Native CATKINAS/Zacros input contracts, rate prefactors, rate laws, lattice
models, and thermochemical calculations remain separate unresolved work.
