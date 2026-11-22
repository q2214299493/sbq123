# Synthetic oxide · Seven-node software fixture

**Usable boundary.** The fixture supports molecular counting, separate inventory balances, explicit graph matching and inspection of candidate Zacros input. Its only archived native initialization failed before state construction. The data describe a software control with an assumed finite graph.

| Project role | Existing record | What can be asserted |
| --- | --- | --- |
| Catalyst identity | Draft `network-definition/1`, project `synthetic-oxide`, material `oxide`, phase `oxide-alpha`, surface `oxide-012`, Miller indices [0,1,2]. | Typed acid and oxygen site owners can be represented without Fe- or Ni-specific code. The structure IDs and lattice are fixture assumptions. |
| Species and reaction | `co2` (gas), `co2-bound` (adsorbed). `fixture-adsorption` consumes one `acid-A` plus one `oxygen-B` per CO₂ molecule. Draft source reversibility is null. | Count each bound CO₂ molecule once. A separately declared reversible software-control event cannot establish reversibility for a physical material. |
| Population and inventory | Two bound molecules in `oxide-counting-cell`, four acid sites and three oxygen sites. | Occupied acid fraction 2/4 and oxygen fraction 2/3. Remaining vacancies 2 and 1. Molecular count is 2 on its declared cell reference. |
| Graph and local events | Finite open chain 1–5–2–6–3–7–4 with six acid–oxygen edges. Seed entities occupy (1,5) and (2,6). | Three simultaneous bridges maximum for the empty graph. In the seeded state (3,7) and (4,7) are each adsorption matches but compete for node 7. Initial desorption patterns refer to complete entities. |
| Candidate native input | Structural mapping plus independently specified synthetic conditions, energetics, rates and controls. The bound bundle has simulation, lattice, mechanism, energetics and state files. | Text generation and structural matching can be exercised offline. Source inventory alone cannot supply edges, barriers, propensities or authorizations. |
| Native qualification | Archived Zacros 4.0 plan, input manifest, consumed approval, execution receipt and validation. One launch, zero retries, process exit 0. | Fatal reader error 1002 on line 2, `temperature 400`. Event loop never reached. Native entity counts, propensities, numerical agreement and trajectory statistics unavailable. Approval consumed; `next_execution_authorized=false`. |
| Corrected serialization | R.2.3 published a separate input manifest and `temperature 400.0`. | New bytes can be inspected as a distinct candidate. The original receipt remains bound to the failed input. Native acceptance of the corrected bundle remains unverified. |

The successful Zacros replays in the B.1 archive belong to other synthetic trajectories. They cannot qualify this seven-node control. [Archived adapter evidence inventory](../../multiphase/stage_b1_4/evidence_inventory.json)

## Source files in this checkout

SHA-256 below covers the exact bytes read in the F1.1 worktree. Domain version IDs are recorded separately.

| Source | File SHA-256 |
| --- | --- |
| [synthetic_oxide_site_network.json](../../../tests/fixtures/multiphase/synthetic_oxide_site_network.json) | `24d5c34d33ec332a131e5f957dcb83ff4816e29c5d4c6ba05c47c854d87c6aa2` |
| [synthetic_oxide_bridge_graph.json](../../../tests/fixtures/multiphase/synthetic_oxide_bridge_graph.json) | `77d0f2fe9ab30743eec527bf412c4f35ed0097dc66fb9514ae0bb541673d0fea` |
| [oxide_observations.json](../../../reports/multiphase/stage_b2_1/oxide_observations.json) | `49d84e1cddf511eeb232002dcb87833c312826a8165d02abf644469b47289d0b` |
| [oxide_validation.json](../../../reports/multiphase/stage_b2_1/oxide_validation.json) | `ab1c981802a6e01423c69656b1e6e2fef8e97b3bcb6d4ac3e673fe5181ed80ce` |
| [mapping.json](../../../reports/multiphase/stage_b2_3_2_2/mapping.json) | `bb0f706fefc969bdf67a5fa44b2c21f8f61ed2e09f1778a76d6b1b6d342e0971` |
| [control.json](../../../reports/multiphase/stage_b2_3_2_4/control.json) | `33276fd1f0ca9bc0edd908896572f612bb3e14c7dd2a1603aee0e99f96869e1e` |
| [execution_plan.json](../../../reports/multiphase/stage_b2_3_2_4/execution_plan.json) | `2c0a012270fec9a6a11e52411c9993742fe6ffc3017db333857fbc4c2dd1b7d8` |
| [input_manifest.json](../../../reports/multiphase/stage_b2_3_2_4/native/input_manifest.json) | `023b40ad208b77a8028d9e03e2131fdc53bd34c2f88f09cdcf2fe19c39f0c285` |
| [execution_receipt.json](../../../reports/multiphase/stage_b2_3_2_4/native_acceptance/execution_receipt.json) | `fdf1fa59f76a8e09c6ecea6aee48f1dadacf0ce513d979936e08f2fbb5a6ae16` |
| [validation.json](../../../reports/multiphase/stage_b2_3_2_4/native_acceptance/validation.json) | `3f104f563db479c90f45f80b494b7b2abe348dc53cb6216d126591fe65b133ce` |
| [input_manifest.json](../../../reports/architecture_repair/stage_r2_3/native/input_manifest.json) | `f475a45a53d91ee3f6a9b5c2277ac0a364d8909381c53227e3ee8e04d721d3d6` |
