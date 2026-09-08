# TODO

Items here are intentionally not implemented in Phase 11.

1. Review and implement non-overwriting dataset promotion from the standalone
   `schemas/kinetic_parameter_handoff.schema.json` contract. The contract and
   validator now exist, but workflow/adapters intentionally do not consume it.
   Phase 3 still leaves `Ea_forward=None`, so the raw workflow remains blocked.
2. Replace bounded static CATKINAS/Zacros adapters with versioned executable
   schemas only after representative software inputs and authoritative format
   contracts are supplied.
3. Add a real end-to-end fixture only when redistributable VASP outputs,
   reviewed kinetic parameters, and a permitted simulator executable are
   available. Never substitute invented scientific values.
4. Select an owner-approved distribution license. The current `LICENSE`
   notice grants no redistribution permission.
5. Consider consolidating repeated adapter validation-status readers, numeric
   formatters, and small JSON writers after stable cross-adapter contracts are
   defined.
