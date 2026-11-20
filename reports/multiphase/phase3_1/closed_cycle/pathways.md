# Reaction network

Edges carry stoichiometric coefficients. Bidirectional arrows denote confirmed reversibility. Each reaction node joins all participants in that event.

```mermaid
flowchart LR
    s0["H2-g · gas"]
    s1["H2-bridge · surface"]
    s2["H2-top · surface"]
    s3["NO-g · gas"]
    s4["HNO-g · gas"]
    s5["HNO-top · surface"]
    r0{"ads · reversible"}
    s0 <-->|1| r0
    r0 <-->|1| s2
    r0 <-->|1| s1
    r1{"transfer · reversible"}
    s1 <-->|1| r1
    r1 <-->|1| s2
    r2{"hydrogenate · reversible"}
    s2 <-->|1| r2
    s3 <-->|1| r2
    r2 <-->|1| s5
    r3{"desorb · reversible"}
    s5 <-->|1| r3
    r3 <-->|1| s4
```
