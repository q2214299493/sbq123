# Context-Safe Shell Inspection

Use these recipes for bounded inspection. They protect model context; they do
not prove that the underlying command succeeded.

## Output and exit status

Default inspection pattern:

```bash
COMMAND 2>&1 | head -c 4000
```

Line limits alone are insufficient because one line may contain megabytes.
When success matters, capture the original command's exit status separately;
never treat the truncating command's status as the original status.

Before reading an unknown file:

```bash
ls -lh FILE
file FILE
```

On PowerShell, use `Get-Item` for size and a targeted reader with a bounded
output budget.

## Never dump directly

Do not print full `OUTCAR`, `vasprun.xml`, `WAVECAR`, `CHGCAR`, `CHG`, `DOSCAR`,
`EIGENVAL`, `XDATCAR`, `PCDAT`, `REPORT`, databases, binaries, archives,
backups, or large `.log`, `.out`, `.err`, `.json`, `.jsonl`, or `.csv` files.

If a file exceeds 200 KB, use targeted extraction. If it exceeds 1 MB, use only
a bounded parser, targeted search, or a small tail after checking its type.

## Repository exploration

Start shallow and inspect only the owning area:

```bash
pwd
ls -lah 2>&1 | head -c 4000
find . -maxdepth 2 -type f 2>&1 | head -c 4000
find . -maxdepth 2 -type d 2>&1 | head -c 4000
```

Focused examples:

```bash
find . -maxdepth 3 -type f \( -name "*.py" -o -name "README*" -o -name "pyproject.toml" \) 2>&1 | head -c 4000
find . -maxdepth 3 -type f \( -name "*.sh" -o -name "*.pbs" -o -name "*.slurm" -o -name "submit*" \) 2>&1 | head -c 4000
find . -maxdepth 4 -type f \( -name "INCAR" -o -name "KPOINTS" -o -name "POSCAR" -o -name "CONTCAR" -o -name "POTCAR.spec" -o -name "*.sh" -o -name "*.py" \) 2>&1 | head -c 4000
```

Do not recursively inspect `archive/`, old job directories, backups, or large
calculation trees unless the task explicitly requires them.

## Search

Prefer `rg` and cap unknown output:

```bash
rg "pattern" . 2>&1 | head -c 4000
rg "ENCUT|EDIFF|EDIFFG|IBRION|IOPT|IMAGES|LCLIMB|ISPIN|MAGMOM|ISMEAR|SIGMA" . 2>&1 | head -c 4000
rg "error|failed|aborted|not converged|ZBRENT|BRIONS|EDDDAV|segmentation|walltime" . 2>&1 | head -c 4000
```

Avoid searching directly through large VASP outputs, archives, old jobs, and
backups. Target filenames or use a parser instead.

## Small previews and diffs

After confirming a text file is small:

```bash
sed -n '1,160p' FILE 2>&1 | head -c 4000
git diff -- FILE 2>&1 | head -c 8000
git diff --stat 2>&1 | head -c 4000
```

Raw diffs are for local verification. Show them to the user only when requested.

