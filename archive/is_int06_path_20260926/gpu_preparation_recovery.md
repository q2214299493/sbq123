# Local GPU package preparation recovery

The first preparation stopped with `KeyError: indexed_bond_changes`. The normalized
reaction contract actually owns `broken_bonds` and `formed_bonds`; this H site
migration has both lists empty. The executor's `indexed_bond_changes=[]` is now
derived explicitly after checking that condition, not inferred for arbitrary reactions.

Inspection found only `path_review.user_accepted.json` in the new destination.
No request, structures, remote payload or model execution existed. A bounded
`--resume-review-only` option preserves that review and resumes only this exact
partial inventory after canonical review validation. All other existing destinations
still reject preparation. No geometry or scientific setting changed.
