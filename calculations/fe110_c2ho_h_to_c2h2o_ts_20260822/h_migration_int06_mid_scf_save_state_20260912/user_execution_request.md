# User-authorized step1: save converged electronic state

2026-09-12 user: 按照这个思路开始吧

The preceding plan proposes starting with one original-center fixed-atom SCF using ALGO=Normal and unchanged physical settings/accuracy, saving WAVECAR and CHGCAR. Authorize this one80core diagnostic submission with EDIFF1e-7,NELM200,NSW0,IBRION-1. Compared with successfulSCF9752745, only LWAVE and LCHARG become true. The new directory cold-starts. Require electronic convergence and saved-state integrity before deciding restart verification; no automatic retry or long Dimer submission.
