# User authorization for the first Fe110 REICO DFT probes

Date: 2026-10-22 (Asia/Shanghai).

The user's exact instruction is: 可以按照这个执行

It accepts the preceding recommendation: first establish DFT energy/force references on a small representative subset of the99 random Fe110 configurations; compare the existing model on identical geometries; use the evidence to decide whether ML sampling is appropriate.

Operational scope under that instruction: six training-family fixed-geometry DFT probes,threeC2 and threeC3,selected geometrically before DFT/model results; each uses the existing32-rank canonical force-label profile on sunboquan-codex. These six count within the original approximately300-label pilot cap. Current frozen model inference may evaluate these same structures only.

No ionic optimization,automatic retry,remaining93 random-structure submissions,new model training,checkpoint promotion,old-job mutation or automatic expansion is included in this first execution stage. Subsequent DFT short optimization or training must be concretely scoped after examining these references. This document records the accepted workflow and the agent's bounded implementation; it is not a claim that the user named the six hashes before selection.
