# Phase 3.2.2 native approval plan

The researcher selected a 1.600 bar composition experiment. The simulation temperature is 400 K. Each of the eight signed points requires individual approval. All approvals are checked before the first launch. The baseline is reused. [Feed decision](feed_decision.json) · [Immutable study](study.json)

| Order | Pair | Sign | H₂ / NO / HNO (bar) | Plan SHA-256 |
|---:|---|---|---|---|
| 1 | intermediate_G-coarse | plus | 1.000000000 / 0.500000000 / 0.100000000 | [411df9e825ce8b55ac3234b84ca49690d585a089ade2e2be8d672a93da327712](intermediate_G-coarse/plus/plan.json) |
| 2 | intermediate_G-coarse | minus | 1.000000000 / 0.500000000 / 0.100000000 | [f08c7b42c1624a5b969491e5410628ed313534325c21ff5c827a94bb882dce66](intermediate_G-coarse/minus/plan.json) |
| 3 | intermediate_G-fine | plus | 1.000000000 / 0.500000000 / 0.100000000 | [3a154f3589d0b1655bc071cb09df14bdb7f3c9b35086f52bf168c34e866b35f7](intermediate_G-fine/plus/plan.json) |
| 4 | intermediate_G-fine | minus | 1.000000000 / 0.500000000 / 0.100000000 | [96b203ec06eeb7e7064203f1cc5d39f8c315b06794b4808b22a685479e9fc778](intermediate_G-fine/minus/plan.json) |
| 5 | gas_order-coarse | plus | 0.981449648 / 0.520405387 / 0.098144965 | [19ade985875f354f4d77905d225c3b724332ccb7760fca904009211d08a9cbb6](gas_order-coarse/plus/plan.json) |
| 6 | gas_order-coarse | minus | 1.017822982 / 0.480394720 / 0.101782298 | [493ce2e6f385c33fee31803314ce64cef7418434d39ef01844ff6768b092b314](gas_order-coarse/minus/plan.json) |
| 7 | gas_order-fine | plus | 0.990817573 / 0.510100670 / 0.099081757 | [8a35691cb639c10392204873be717d3bbe9b9a0f123333ed2372a8b67891f9b3](gas_order-fine/plus/plan.json) |
| 8 | gas_order-fine | minus | 1.009000603 / 0.490099337 / 0.100900060 | [139f423959990f72694d60ed365b641632e3753a75c3c9439de009ebc4ccccfc](gas_order-fine/minus/plan.json) |

HNO-top steps are 0.010 and 0.005 eV. NO natural-log pressure steps are 0.04 and 0.02 with proportional redistribution of remaining pressure. The limits are one native process, 210 s per run, 1680 s total native time, 1920 s wall time, zero retries. A failed member stops subsequent launches.

Study SHA-256: f790c84103dda4b855a29a8241d2fc91c08c0b1d974d0049bdf1943c81d80be9.
