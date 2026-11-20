# Network DRC pilot

All TOFs are positive net overall turnovers per reference site pair per second.

| Reaction | TS | Forward / reverse barrier (eV) | Source | Baseline / plus / minus TOF | DRC | Stability |
|---|---|---|---|---|---:|---|
| ads | fixture-ts-ads | 0.4 / 0.5 | new | 81.51277 / 78.73449 / 84.174095 | 0.230275515 | untested |
| transfer | fixture-ts-transfer | 0.76 / 0.74 | reused | 81.51277 / 80.998016 / 81.959849 | 0.0406904512 | stable |
| hydrogenate | fixture-ts-hydrogenate | 0.78 / 0.88 | reused | 81.51277 / 76.194773 / 86.827068 | 0.450257552 | stable |
| desorb | fixture-ts-desorb | 0.8 / 0.74 | new | 81.51277 / 78.109781 / 84.705504 | 0.279426659 | untested |

## Ranked, step-size-stable results

1. hydrogenate — 0.450257552
2. transfer — 0.0406904512

## Missing evidence and scope

- ads: Independent step-size stability confirmation required
- desorb: Independent step-size stability confirmation required

## Execution budget

Native invocations: 4 of 4. Measured native seconds: 408.539086. Batch wall seconds: 409.56429649845813.

## Response matrices

Changes are relative to the common baseline. Coverage and site utilization are fractions. Elementary flux changes are events per reference site per second.

| Perturbed TS | Sign | Quantity | Species, site or step | Change |
|---|---|---|---|---:|
| ads | plus | coverage | HNO-top | -0.00177383304 |
| ads | plus | coverage | H2-top | -0.00915903801 |
| ads | plus | coverage | H2-bridge | -0.0165702767 |
| ads | plus | vacancies | top-Ni | 0.010932871 |
| ads | plus | vacancies | bridge-Cu | 0.0165702767 |
| ads | plus | occupied | top-Ni | -0.010932871 |
| ads | plus | occupied | bridge-Cu | -0.0165702767 |
| ads | plus | forward_flux | ads | -5.0370493 |
| ads | plus | reverse_flux | ads | -2.25876895 |
| ads | plus | net_flux | ads | -2.77828035 |
| ads | plus | forward_flux | transfer | 5.76320588 |
| ads | plus | reverse_flux | transfer | 8.54148622 |
| ads | plus | net_flux | transfer | -2.77828035 |
| ads | plus | forward_flux | hydrogenate | -5.67742589 |
| ads | plus | reverse_flux | hydrogenate | -0.120865193 |
| ads | plus | net_flux | hydrogenate | -5.55656069 |
| ads | plus | forward_flux | desorb | -1.23099341 |
| ads | plus | reverse_flux | desorb | 4.32556728 |
| ads | plus | net_flux | desorb | -5.55656069 |
| ads | minus | coverage | HNO-top | 0.00169916109 |
| ads | minus | coverage | H2-top | 0.00877347567 |
| ads | minus | coverage | H2-bridge | 0.0156731729 |
| ads | minus | vacancies | top-Ni | -0.0104726368 |
| ads | minus | vacancies | bridge-Cu | -0.0156731729 |
| ads | minus | occupied | top-Ni | 0.0104726368 |
| ads | minus | occupied | bridge-Cu | 0.0156731729 |
| ads | minus | forward_flux | ads | 5.35866941 |
| ads | minus | reverse_flux | ads | 2.69734461 |
| ads | minus | net_flux | ads | 2.6613248 |
| ads | minus | forward_flux | transfer | -6.39736526 |
| ads | minus | reverse_flux | transfer | -9.05869006 |
| ads | minus | net_flux | transfer | 2.6613248 |
| ads | minus | forward_flux | hydrogenate | 5.43842681 |
| ads | minus | reverse_flux | hydrogenate | 0.115777206 |
| ads | minus | net_flux | hydrogenate | 5.32264961 |
| ads | minus | forward_flux | desorb | 1.17917304 |
| ads | minus | reverse_flux | desorb | -4.14347656 |
| ads | minus | net_flux | desorb | 5.32264961 |
| transfer | plus | coverage | HNO-top | -0.000328652237 |
| transfer | plus | coverage | H2-top | -0.00169696824 |
| transfer | plus | coverage | H2-bridge | 0.00374833569 |
| transfer | plus | vacancies | top-Ni | 0.00202562048 |
| transfer | plus | vacancies | bridge-Cu | -0.00374833569 |
| transfer | plus | occupied | top-Ni | -0.00202562048 |
| transfer | plus | occupied | bridge-Cu | 0.00374833569 |
| transfer | plus | forward_flux | ads | -0.516943294 |
| transfer | plus | reverse_flux | ads | -0.00218906904 |
| transfer | plus | net_flux | ads | -0.514754225 |
| transfer | plus | forward_flux | transfer | -55.9574231 |
| transfer | plus | reverse_flux | transfer | -55.4426688 |
| transfer | plus | net_flux | transfer | -0.514754225 |
| transfer | plus | forward_flux | hydrogenate | -1.05190211 |
| transfer | plus | reverse_flux | hydrogenate | -0.0223936613 |
| transfer | plus | net_flux | hydrogenate | -1.02950845 |
| transfer | plus | forward_flux | desorb | -0.228075997 |
| transfer | plus | reverse_flux | desorb | 0.801432454 |
| transfer | plus | net_flux | desorb | -1.02950845 |
| transfer | minus | coverage | HNO-top | 0.000285444211 |
| transfer | minus | coverage | H2-top | 0.00147386723 |
| transfer | minus | coverage | H2-bridge | -0.00329384353 |
| transfer | minus | vacancies | top-Ni | -0.00175931144 |
| transfer | minus | vacancies | bridge-Cu | 0.00329384353 |
| transfer | minus | occupied | top-Ni | 0.00175931144 |
| transfer | minus | occupied | bridge-Cu | -0.00329384353 |
| transfer | minus | forward_flux | ads | 0.447687518 |
| transfer | minus | reverse_flux | ads | 0.000608212852 |
| transfer | minus | net_flux | ads | 0.447079306 |
| transfer | minus | forward_flux | transfer | 64.6728806 |
| transfer | minus | reverse_flux | transfer | 64.2258013 |
| transfer | minus | net_flux | transfer | 0.447079306 |
| transfer | minus | forward_flux | hydrogenate | 0.91360817 |
| transfer | minus | reverse_flux | hydrogenate | 0.0194495587 |
| transfer | minus | net_flux | hydrogenate | 0.894158611 |
| transfer | minus | forward_flux | desorb | 0.198090765 |
| transfer | minus | reverse_flux | desorb | -0.696067846 |
| transfer | minus | net_flux | desorb | 0.894158611 |
| hydrogenate | plus | coverage | HNO-top | -0.0167953699 |
| hydrogenate | plus | coverage | H2-top | 0.0193722845 |
| hydrogenate | plus | coverage | H2-bridge | 0.0113387973 |
| hydrogenate | plus | vacancies | top-Ni | -0.00257691465 |
| hydrogenate | plus | vacancies | bridge-Cu | -0.0113387973 |
| hydrogenate | plus | occupied | top-Ni | 0.00257691465 |
| hydrogenate | plus | occupied | bridge-Cu | 0.0113387973 |
| hydrogenate | plus | forward_flux | ads | -4.31365912 |
| hydrogenate | plus | reverse_flux | ads | 1.00433764 |
| hydrogenate | plus | net_flux | ads | -5.31799676 |
| hydrogenate | plus | forward_flux | transfer | 3.28415685 |
| hydrogenate | plus | reverse_flux | transfer | 8.60215361 |
| hydrogenate | plus | net_flux | transfer | -5.31799676 |
| hydrogenate | plus | forward_flux | hydrogenate | -15.3171872 |
| hydrogenate | plus | reverse_flux | hydrogenate | -4.68119369 |
| hydrogenate | plus | net_flux | hydrogenate | -10.6359935 |
| hydrogenate | plus | forward_flux | desorb | -11.6555443 |
| hydrogenate | plus | reverse_flux | desorb | -1.01955083 |
| hydrogenate | plus | net_flux | desorb | -10.6359935 |
| hydrogenate | minus | coverage | HNO-top | 0.0166010244 |
| hydrogenate | minus | coverage | H2-top | -0.018855751 |
| hydrogenate | minus | coverage | H2-bridge | -0.0116069263 |
| hydrogenate | minus | vacancies | top-Ni | 0.00225472654 |
| hydrogenate | minus | vacancies | bridge-Cu | 0.0116069263 |
| hydrogenate | minus | occupied | top-Ni | -0.00225472654 |
| hydrogenate | minus | occupied | bridge-Cu | -0.0116069263 |
| hydrogenate | minus | forward_flux | ads | 4.35177528 |
| hydrogenate | minus | reverse_flux | ads | -0.962522695 |
| hydrogenate | minus | net_flux | ads | 5.31429797 |
| hydrogenate | minus | forward_flux | transfer | -4.07716429 |
| hydrogenate | minus | reverse_flux | transfer | -9.39146226 |
| hydrogenate | minus | net_flux | transfer | 5.31429797 |
| hydrogenate | minus | forward_flux | hydrogenate | 16.2038826 |
| hydrogenate | minus | reverse_flux | hydrogenate | 5.57528669 |
| hydrogenate | minus | net_flux | hydrogenate | 10.6285959 |
| hydrogenate | minus | forward_flux | desorb | 11.5206737 |
| hydrogenate | minus | reverse_flux | desorb | 0.892077783 |
| hydrogenate | minus | net_flux | desorb | 10.6285959 |
| desorb | plus | coverage | HNO-top | 0.0193491032 |
| desorb | plus | coverage | H2-top | -0.00885275785 |
| desorb | plus | coverage | H2-bridge | 0.001202797 |
| desorb | plus | vacancies | top-Ni | -0.0104963453 |
| desorb | plus | vacancies | bridge-Cu | -0.001202797 |
| desorb | plus | occupied | top-Ni | 0.0104963453 |
| desorb | plus | occupied | bridge-Cu | 0.001202797 |
| desorb | plus | forward_flux | ads | -3.7422127 |
| desorb | plus | reverse_flux | ads | -0.339223644 |
| desorb | plus | net_flux | ads | -3.40298906 |
| desorb | plus | forward_flux | transfer | -15.4463346 |
| desorb | plus | reverse_flux | transfer | -12.0433455 |
| desorb | plus | net_flux | transfer | -3.40298906 |
| desorb | plus | forward_flux | hydrogenate | -5.48757157 |
| desorb | plus | reverse_flux | hydrogenate | 1.31840655 |
| desorb | plus | net_flux | hydrogenate | -6.80597812 |
| desorb | plus | forward_flux | desorb | -25.9808353 |
| desorb | plus | reverse_flux | desorb | -19.1748572 |
| desorb | plus | net_flux | desorb | -6.80597812 |
| desorb | minus | coverage | HNO-top | -0.0181492816 |
| desorb | minus | coverage | H2-top | 0.00830626162 |
| desorb | minus | coverage | H2-bridge | -0.00105778818 |
| desorb | minus | vacancies | top-Ni | 0.00984302003 |
| desorb | minus | vacancies | bridge-Cu | 0.00105778818 |
| desorb | minus | occupied | top-Ni | -0.00984302003 |
| desorb | minus | occupied | bridge-Cu | -0.00105778818 |
| desorb | minus | forward_flux | ads | 3.51118894 |
| desorb | minus | reverse_flux | ads | 0.318455217 |
| desorb | minus | net_flux | ads | 3.19273373 |
| desorb | minus | forward_flux | transfer | 14.4809395 |
| desorb | minus | reverse_flux | transfer | 11.2882057 |
| desorb | minus | net_flux | transfer | 3.19273373 |
| desorb | minus | forward_flux | hydrogenate | 5.14881417 |
| desorb | minus | reverse_flux | hydrogenate | -1.23665328 |
| desorb | minus | net_flux | hydrogenate | 6.38546745 |
| desorb | minus | forward_flux | desorb | 28.9030519 |
| desorb | minus | reverse_flux | desorb | 22.5175845 |
| desorb | minus | net_flux | desorb | 6.38546745 |
