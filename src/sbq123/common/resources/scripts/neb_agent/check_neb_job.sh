#!/bin/bash
set -u

usage() {
    echo "Usage: $0 JOB_DIR [--detail [TAIL_LINES]]" >&2
}

if [ "$#" -lt 1 ] || [ "$#" -gt 3 ]; then
    usage
    exit 2
fi

jobdir="$1"
mode="summary"
tail_lines=10
if [ "$#" -ge 2 ]; then
    if [ "$2" != "--detail" ]; then
        usage
        echo "Detailed output now requires the explicit --detail flag." >&2
        exit 2
    fi
    mode="detail"
fi
if [ "$#" -eq 3 ]; then
    case "$3" in
        ''|*[!0-9]*)
            usage
            exit 2
            ;;
        *)
            tail_lines="$3"
            ;;
    esac
fi

cd "$jobdir" || exit 1

images=()
for directory in [0-9][0-9]; do
    [ -d "$directory" ] && images+=("$directory")
done
if [ "${#images[@]}" -lt 3 ]; then
    echo "At least three numbered image directories are required." >&2
    exit 3
fi

incar_value() {
    awk -F= -v key="$1" '
        toupper($1) ~ "^[[:space:]]*" key "[[:space:]]*$" {
            value=$2
            sub(/[!#].*$/, "", value)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' INCAR
}

nelm="$(incar_value NELM)"
ediffg="$(incar_value EDIFFG)"
nelm="${nelm:-60}"
force_target="$(awk -v value="${ediffg:--0.05}" 'BEGIN { value += 0; if (value < 0) value = -value; print value }')"

echo "NEB_STATUS mode=$mode time=$(date '+%F_%T_%Z')"
echo "JOBDIR $jobdir"
echo "PARAMS images=$(incar_value IMAGES) iopt=$(incar_value IOPT) lclimb=$(incar_value LCLIMB) ediff=$(incar_value EDIFF) ediffg=$ediffg nelm=$nelm"

last_index=$((${#images[@]} - 1))
max_neb="-1"
max_image="NA"
high_images=()
rising_images=()
fatal_images=()
converged_images=0

for ((index=1; index<last_index; index++)); do
    image="${images[$index]}"
    oszicar="$image/OSZICAR"
    outcar="$image/OUTCAR"

    steps=0
    scf_last=0
    scf_max=0
    scf_current=0
    energy="NA"
    if [ -s "$oszicar" ]; then
        read -r steps scf_last scf_max scf_current energy < <(
            tr -d '\000' < "$oszicar" | awk '
                $1 ~ /^(DAV|RMM|CGA):$/ {
                    current = $2 + 0
                    if (current > cycle_max) cycle_max = current
                }
                / F=/ {
                    completed += 1
                    last_completed = cycle_max
                    if (cycle_max > overall_max) overall_max = cycle_max
                    energy = $3
                    cycle_max = 0
                }
                END {
                    if (energy == "") energy = "NA"
                    printf "%d %d %d %d %s\n", completed, last_completed, overall_max, cycle_max, energy
                }
            '
        )
    fi

    atomic_force="NA"
    neb_force="NA"
    neb_first="NA"
    trend="unknown"
    required=0
    fatal=0
    if [ -s "$outcar" ]; then
        atomic_force="$(grep 'FORCES: max atom' "$outcar" | tail -n 1 | awk '{print $(NF-1)}')"
        read -r neb_force neb_first trend < <(
            grep 'NEB: forces:' "$outcar" | tail -n 8 | awk -v target="$force_target" '
                {
                    values[++n] = $(NF-1) + 0
                    if (n == 1 || values[n] < min) min = values[n]
                    if (n == 1 || values[n] > max) max = values[n]
                }
                END {
                    if (n == 0) {
                        print "NA NA unknown"
                        exit
                    }
                    first = values[1]
                    last = values[n]
                    if (last <= target) status = "near_target"
                    else if (last <= first * 0.90) status = "falling"
                    else if (last >= first * 1.10) status = "rising"
                    else if ((max - min) > 0.15 * last) status = "oscillating"
                    else status = "plateau"
                    printf "%.6f %.6f %s\n", last, first, status
                }
            '
        )
        required="$(grep -c 'reached required accuracy' "$outcar" || true)"
        fatal="$(grep -Eic 'BRMIX|ZBRENT|VERY BAD NEWS|EDDDAV|segmentation|forrtl|internal error|M_divide' "$outcar" || true)"
    fi

    electronic="normal"
    if [ "$fatal" -gt 0 ]; then
        electronic="fatal"
        fatal_images+=("$image")
    elif [ "$scf_current" -ge "$nelm" ] || [ "$scf_last" -ge "$nelm" ]; then
        electronic="nelm_exhausted"
    fi

    problem="none"
    if [ "$required" -gt 0 ]; then
        converged_images=$((converged_images + 1))
    elif [ "$neb_force" != "NA" ] && awk -v force="$neb_force" -v target="$force_target" 'BEGIN { exit !(force > target) }'; then
        problem="not_converged"
    fi
    if [ "$trend" = "rising" ]; then
        problem="force_rising"
        rising_images+=("$image")
    fi
    if [ "$electronic" != "normal" ]; then
        problem="$electronic"
    fi

    if [ "$neb_force" != "NA" ] && awk -v force="$neb_force" -v max="$max_neb" 'BEGIN { exit !(force > max) }'; then
        max_neb="$neb_force"
        max_image="$image"
    fi
    if [ "$neb_force" != "NA" ] && awk -v force="$neb_force" -v target="$force_target" 'BEGIN { exit !(force > 3 * target) }'; then
        high_images+=("$image")
    fi

    echo "IMAGE $image steps=$steps energy=$energy scf_last=$scf_last scf_max=$scf_max atomic_force=$atomic_force neb_force=$neb_force trend=$trend electronic=$electronic problem=$problem"

    if [ "$mode" = "detail" ]; then
        echo "DETAIL_IMAGE $image"
        tr -d '\000' < "$oszicar" 2>/dev/null | grep ' F=' | tail -n "$tail_lines" || true
        tr -d '\000' < "$oszicar" 2>/dev/null | grep -E '^[[:space:]]*(DAV|RMM|CGA):' | tail -n "$tail_lines" || true
        grep 'FORCES: max atom' "$outcar" 2>/dev/null | tail -n "$tail_lines" || true
        grep 'NEB: forces:' "$outcar" 2>/dev/null | tail -n "$tail_lines" || true
    fi
done

high_csv="$(IFS=,; echo "${high_images[*]-}")"
rising_csv="$(IFS=,; echo "${rising_images[*]-}")"
fatal_csv="$(IFS=,; echo "${fatal_images[*]-}")"
echo "OVERALL max_neb_force=$max_neb max_image=$max_image converged_images=$converged_images high_force_images=$high_csv rising_images=$rising_csv fatal_images=$fatal_csv"

if [ "$mode" = "detail" ] && [ -s vasp.out ]; then
    echo "DETAIL_VASP_FATAL"
    grep -Ein 'BRMIX|ZBRENT|VERY BAD NEWS|EDDDAV|segmentation|forrtl|internal error|M_divide' vasp.out | tail -n "$tail_lines" || true
fi
