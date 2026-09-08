# Alpha-Fe Bulk K-Mesh Whitelist Review

- Query: `alpha-Fe bcc Fe2 bulk VASP PBE Monkhorst-Pack k-point mesh`
- Source: NOMAD public API, restricted to pure `Fe2`, bulk, space group 229, and VASP.
- Population: 651 matching metadata records; 74 PBE non-band-path candidates after filename filtering; six records exposed a usable three-dimensional Monkhorst-Pack grid through the current archive parser.
- Parsed distribution: `18x18x18` in four records from three uploads; `5x5x5` in two records from two uploads.
- Interpretation: `18x18x18` is the modal high-density mesh in this bounded whitelist sample. The records are benchmark/convergence data and are not six independent publications.
- Local implication: the project-validated `15x15x15` mesh remains a defensible balanced production value because its own convergence error is the governing evidence. The NOMAD sample supports the general dense-mesh range but does not require replacing `15x15x15` with `18x18x18`.
