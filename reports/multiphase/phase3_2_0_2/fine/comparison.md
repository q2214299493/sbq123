# Hydrogenate TS sensitivity at 400 K

The symmetric displacement holds both endpoints, prefactors, pressures and normalization fixed.

| Observable | Baseline | +0.005 eV | -0.005 eV |
|---|---:|---:|---:|
| Net turnovers / (reference pair s) | 81.51277016 | 76.1947734 | 86.82706813 |
| Native invocation (s) | 192.292314 | 127.645215 | 72.160791 |
| coverage / HNO-top | 0.4012122084 | 0.3844168385 | 0.4178132328 |
| coverage / H2-top | 0.3071012426 | 0.3264735271 | 0.2882454917 |
| coverage / H2-bridge | 0.696679479 | 0.7080182764 | 0.6850725527 |
| vacancies / top-Ni | 0.291686549 | 0.2891096343 | 0.2939412755 |
| vacancies / bridge-Cu | 0.303320521 | 0.2919817236 | 0.3149274473 |
| site_residuals / top-Ni | 0 | 0 | 0 |
| site_residuals / bridge-Cu | 0 | 0 | 0 |
| ads kf (bar^-1 s^-1) | 1062.533451 | 1062.533451 | 1062.533451 |
| ads kr (s^-1) | 58.39820737 | 58.39820737 | 58.39820737 |
| ads forward_flux (events per reference site per second) | 94.00713284 | 89.69347372 | 98.35890811 |
| ads reverse_flux (events per reference site per second) | 12.49436267 | 13.49870031 | 11.53183998 |
| ads net_flux (events per reference site per second) | 81.51277016 | 76.1947734 | 86.82706813 |
| transfer kf (s^-1) | 2214.727138 | 2214.727138 | 2214.727138 |
| transfer kr (s^-1) | 3956.47883 | 3956.47883 | 3956.47883 |
| transfer forward_flux (events per reference site per second) | 450.0592041 | 453.343361 | 445.9820398 |
| transfer reverse_flux (events per reference site per second) | 368.5464339 | 377.1485876 | 359.1549717 |
| transfer net_flux (events per reference site per second) | 81.51277016 | 76.1947734 | 86.82706813 |
| hydrogenate kf (bar^-1 s^-1) | 1239.742838 | 1072.344808 | 1433.272482 |
| hydrogenate kr (s^-1) | 68.13786357 | 58.93745216 | 78.77450215 |
| hydrogenate forward_flux (events per reference site per second) | 190.363283 | 175.0460958 | 206.5671657 |
| hydrogenate reverse_flux (events per reference site per second) | 27.33774272 | 22.65654903 | 32.91302941 |
| hydrogenate net_flux (events per reference site per second) | 163.0255403 | 152.3895468 | 173.6541363 |
| desorb kf (s^-1) | 693.9736631 | 693.9736631 | 693.9736631 |
| desorb kr (bar^-1 s^-1) | 3956.47883 | 3956.47883 | 3956.47883 |
| desorb forward_flux (events per reference site per second) | 278.4307059 | 266.7751616 | 289.9513797 |
| desorb reverse_flux (events per reference site per second) | 115.4051656 | 114.3856148 | 116.2972434 |
| desorb net_flux (events per reference site per second) | 163.0255403 | 152.3895468 | 173.6541363 |

Central finite-difference DRC = 0.4502575521 (dimensionless).
Independent product-based estimate = 0.4502575521.
Pair elapsed 200.16 s of 480 s.

A finite displacement samples curvature; the estimates use a symmetric energy interval.

## Step-size convergence

| Step (eV) | Central DRC | Positive side | Negative side |
|---:|---:|---:|---:|
| 0.01 | 0.4504407132 | 0.480097412 | 0.4207840144 |
| 0.005 | 0.4502575521 | 0.4651073076 | 0.4354077966 |

Stable within the project tolerance. Absolute difference 0.0001831610903, tolerance 0.02251287761.

| Change from baseline or validation residual | +0.01 | -0.01 | +0.005 | -0.005 |
|---|---:|---:|---:|---:|
| coverage / HNO-top (fraction) | -0.0336562225 | 0.0328846957 | -0.0167953699 | 0.0166010244 |
| coverage / H2-top (fraction) | 0.0391164235 | -0.037065398 | 0.0193722845 | -0.018855751 |
| coverage / H2-bridge (fraction) | 0.0223432956 | -0.0234087324 | 0.0113387973 | -0.0116069263 |
| vacancies / top-Ni (fraction) | -0.00546020097 | 0.00418070223 | -0.00257691465 | 0.00225472654 |
| vacancies / bridge-Cu (fraction) | -0.0223432956 | 0.0234087324 | -0.0113387973 | 0.0116069263 |
| ads / forward_flux (events/reference site/s) | -8.55491468 | 8.70636731 | -4.31365912 | 4.35177528 |
| ads / reverse_flux (events/reference site/s) | 2.04319287 | -1.87714608 | 1.00433764 | -0.962522695 |
| ads / net_flux (events/reference site/s) | -10.5981075 | 10.5835134 | -5.31799676 | 5.31429797 |
| transfer / forward_flux (events/reference site/s) | 5.73886729 | -8.88829322 | 3.28415685 | -4.07716429 |
| transfer / reverse_flux (events/reference site/s) | 16.3369748 | -19.4718066 | 8.60215361 | -9.39146226 |
| transfer / net_flux (events/reference site/s) | -10.5981075 | 10.5835134 | -5.31799676 | 5.31429797 |
| hydrogenate / forward_flux (events/reference site/s) | -29.7961965 | 33.3631705 | -15.3171872 | 16.2038826 |
| hydrogenate / reverse_flux (events/reference site/s) | -8.5999814 | 12.1961437 | -4.68119369 | 5.57528669 |
| hydrogenate / net_flux (events/reference site/s) | -21.1962151 | 21.1670268 | -10.6359935 | 10.6285959 |
| desorb / forward_flux (events/reference site/s) | -23.356532 | 22.8211128 | -11.6555443 | 11.5206737 |
| desorb / reverse_flux (events/reference site/s) | -2.16031695 | 1.65408599 | -1.01955083 | 0.892077783 |
| desorb / net_flux (events/reference site/s) | -21.1962151 | 21.1670268 | -10.6359935 | 10.6285959 |
| Maximum surface steady-state residual | 1.42108547e-13 | 1.13686838e-13 | 5.68434189e-14 | 5.68434189e-14 |
| site_balance / top-Ni | 0 | 0 | 0 | 0 |
| site_balance / bridge-Cu | 0 | 0 | 0 | 0 |
| element_balance / H | 0 | 0 | 0 | 0 |
| element_balance / N | 0 | 0 | 0 | 0 |
| element_balance / O | 0 | 0 | 0 | 0 |
| detailed_balance / ads | -3.34023295e-06 | -3.34023295e-06 | -3.34023295e-06 | -3.34023295e-06 |
| detailed_balance / transfer | 6.68046591e-07 | 6.68046591e-07 | 6.68046591e-07 | 6.68046591e-07 |
| detailed_balance / hydrogenate | -3.34023295e-06 | -3.34023295e-06 | -3.34023295e-06 | -3.34023295e-06 |
| detailed_balance / desorb | 2.00413977e-06 | 2.00413977e-06 | 2.00413977e-06 | 2.00413977e-06 |
