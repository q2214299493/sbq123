#!/bin/bash
set -euo pipefail
cd "$HOME/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_is_a_int06_ci9808511_review_20261002"
vtst="$HOME/soft/qvasp-v2.2/exefile/Tools/USERTooLs/vtstscripts"
: > dist.dat
for i in $(seq 0 9); do
    left=$(printf '%02d' "$i")
    right=$(printf '%02d' "$((i+1))")
    printf '%s %s ' "$left" "$right" >> dist.dat
    perl "$vtst/dist.pl" "$left/POSCAR" "$right/POSCAR" >> dist.dat
done
perl "$vtst/nebmovie.pl" 0
test -s movie
test -s dist.dat
printf 'VTST dist.pl and nebmovie.pl 0 completed\n'
