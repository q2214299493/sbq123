# NO constrained-composition reaction order

The accepted Phase 3.0 synthetic Ni/Cu baseline at 400 K has H₂, HNO and NO partial pressures of 1.0, 0.1 and 0.5 bar. Its production and uptake define the same positive net turnover per reference site pair. All four approved HNO-top results and the original gas rejection remain in the preceding checkpoint. [Historical evidence](../phase3_2_2/completion.md)

| Pair | H₂ (bar) | HNO (bar) | NO (bar) | ln(P_NO/0.5) | Native plan |
|---|---:|---:|---:|---:|---|
| Coarse + | 0.98140 | 0.09814 | 0.52046 | +0.0401049375 | [Plan](coarse/plus/plan.json) |
| Coarse − | 1.01780 | 0.10178 | 0.48042 | −0.0399473771 | [Plan](coarse/minus/plan.json) |
| Fine + | 0.99080 | 0.09908 | 0.51012 | +0.0200378937 | [Plan](fine/plus/plan.json) |
| Fine − | 1.00900 | 0.10090 | 0.49010 | −0.0199986465 | [Plan](fine/minus/plan.json) |

The input writer preserves double precision. On MATLAB R2025b, a scalar num2str/str2double round trip followed by MAT serialization reproduced the previous CATKINAS vector, including the 1.600005 bar overshoot. Each new vector survived the same probe unchanged. This establishes representability for these values. Each scientific run must also supply its actual MAT values, checked before acceptance against the exact sum, feed proportions and approved vector. The probe did not invoke CATKINAS. [Machine-readable plans and pressure checks](serialization.json)

The NO response includes the proportional changes in H₂ and HNO at fixed total pressure. Set x = ln(P_NO/P_NO,baseline) from the actual native MAT and y = ln(net TOF). Let D₋ and D₊ be the one-sided slopes from the baseline. At x = 0, the derivative of the interpolating quadratic is (x₊D₋ − x₋D₊)/(x₊ − x₋). The endpoint secant uses (y₊ − y₋)/(x₊ − x₋). Only the quadratic estimate is used for coarse/fine comparison. It assumes a locally smooth response. Each estimate requires a positive turnover and verified samples on both sides. The project tolerance is max(0.002, 0.05 × |fine|).

Run scope is four separate approvals at 210 seconds per run, 840 native seconds and 960 wall-clock seconds, sequentially with zero retries. The first failure stops the campaign. Fe(110) remains blocked.
