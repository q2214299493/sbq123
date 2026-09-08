# Fe(110) C/C2/O candidate retrieval review

- Query: `bcc Fe(110) C* O* coadsorption, C2*, CCO/C2O*, and C2*+O* relaxed adsorption structures`
- Exact current-model match: `NO_WHITELIST_MATCH`.
- C+O: one elemental-Fe CO-dissociation record exists on Fe(211), but it has no transferable site-labelled Fe(110) endpoint. It is used only to confirm the dissociated product class.
- C2: `NO_WHITELIST_MATCH` for bare intact C2 adsorption. Use the user-reviewed `eta2(C,C)/h-lb-h` template, with the two C atoms in hollow-like positions straddling a long bridge.
- C2O: three Catalysis-Hub Cu(100) structures independently retain an upright terminal-C-bound C-C-O chain. Their C-C range is 1.293-1.318 A and C-O range is 1.171-1.184 A. This supports one intact upright connectivity template, not Cu energies or Cu site rankings.
- C2+O: `NO_WHITELIST_MATCH`. Keep the same `eta2(C,C)/h-lb-h` C2 template and place O at the nearest geometrically valid unoccupied long bridge; this remains a screening candidate.
- Local Fe(110) evidence: Step 12A C hollow migrated to long bridge, while O hollow remained the preferred high-coordination class. These local results determine the Fe(110) anchor classes.
- User-selected minimal set: C+O one; C2 one `h-lb-h`; C2O two (`kappa-Calpha/lb_tilted` and `eta2(Calpha,Cbeta)/h-lb-h`); C2+O one. No blind four-site sweep and no global-minimum claim.
