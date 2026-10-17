# User authorization — MatRIS adsorption trial, 2026-10-18

User request: “要不你把Matls做为主模型 试试他的gpu加速在这上面的效果”.
Bounded proposal: original MatRIS Fe–C–O–H checkpoint; six candidates
06_C, 07_B, 07_C, 08_A, 09_A, 10_A; the same original seeds and LBFGS
settings as the previous AQCat25 run; maximum 80 steps per candidate,
fmax=0.10 eV/Å; serial execution on idle MZ73 GPU 2, maximum 30 minutes.
Slurm is down. Explicit approval to run directly on idle GPU 2:
“你尝试一下 授权”.

This authorizes only this six-candidate, single-launch GPU trial. No VASP,
training, model promotion, global default-model change, automatic retry,
shared-service modification, or stopping another process is authorized.
Keep all original AQCat25 and VASP inputs and results intact. Return every
MatRIS candidate through work for scientific review. No speedup is claimed.
