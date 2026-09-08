# Fe(110) Database Layer Review

- Query: `bcc Fe(110) database slab layer count adsorption reaction calculations`
- Exact whitelist match: one unique periodic Fe-only Fe(110) slab in the first 100 Catalysis-Hub Fe(110) reaction records.
- Verified geometry: 28 Fe atoms, seven layers, four Fe atoms per layer.
- Constraint: 12 fixed Fe atoms, corresponding to three fixed layers.
- Transferability: the database uses a smaller lateral cell, Quantum ESPRESSO, and BEEF-vdW. It supports seven layers as a database-scale thickness but does not validate its high-coverage lateral cell for isolated CO dissociation.
- Local implication: reduce cost first with a five-layer 3x3 screening branch while retaining the 3x3 lateral cell; keep seven layers for final matched energies/barriers.
