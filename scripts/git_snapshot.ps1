[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Message,

    [string]$PathList,

    [switch]$Push,

    [ValidateRange(1, 100)]
    [int]$MaxFileSizeMB = 10
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot

try {
    if ((git rev-parse --is-inside-work-tree 2>$null) -ne 'true') {
        throw "Not a Git repository: $repoRoot"
    }

    $preExistingStaged = @(git -c core.quotePath=false diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect the current Git index.'
    }
    if ($preExistingStaged.Count -gt 0) {
        throw 'Snapshot stopped because the Git index already contains staged changes.'
    }

    $selectedPaths = [System.Collections.Generic.List[string]]::new()
    if ($PathList) {
        foreach ($item in ($PathList -split ';')) {
            if ($item.Trim()) {
                $selectedPaths.Add($item.Trim())
            }
        }
        if ($selectedPaths.Count -eq 0) {
            throw '-PathList did not contain any usable repository-relative paths.'
        }
        foreach ($relativePath in $selectedPaths) {
            if ([System.IO.Path]::IsPathRooted($relativePath)) {
                throw "Snapshot paths must be repository-relative: $relativePath"
            }
            $candidate = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $relativePath))
            if (-not $candidate.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Snapshot path escapes the repository: $relativePath"
            }
        }
        git add -- $selectedPaths
    }
    else {
        git add --all
    }
    if ($LASTEXITCODE -ne 0) {
        throw 'git add failed.'
    }
    $staged = @(git -c core.quotePath=false diff --cached --name-only --diff-filter=ACMR)
    if ($LASTEXITCODE -ne 0) {
        git reset --quiet
        throw 'Unable to inspect staged files.'
    }

    if ($staged.Count -eq 0) {
        Write-Output 'No versioned changes to commit.'
        return
    }

    $blockedNames = @(
        'POTCAR', 'WAVECAR', 'WAVEDER', 'CHG', 'CHGCAR', 'CHGCAR_sum',
        'vasprun.xml', 'OUTCAR', 'OSZICAR', 'XDATCAR', 'CONTCAR',
        'DOSCAR', 'EIGENVAL', 'PROCAR', 'LOCPOT', 'ELFCAR',
        'AECCAR0', 'AECCAR1', 'AECCAR2'
    )
    $problems = [System.Collections.Generic.List[string]]::new()

    foreach ($relativePath in $staged) {
        $leaf = Split-Path -Leaf $relativePath
        if ($blockedNames -contains $leaf) {
            $problems.Add("blocked VASP file: $relativePath")
            continue
        }

        if ($relativePath -match '(^|/)(\.env($|\.)|.*\.(pem|key|ppk)$)') {
            $problems.Add("possible credential file: $relativePath")
            continue
        }

        $fullPath = Join-Path $repoRoot $relativePath
        if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
            $sizeMB = (Get-Item -LiteralPath $fullPath).Length / 1MB
            if ($sizeMB -gt $MaxFileSizeMB) {
                $problems.Add(("file exceeds {0} MB: {1} ({2:N2} MB)" -f $MaxFileSizeMB, $relativePath, $sizeMB))
            }
        }
    }

    if ($problems.Count -gt 0) {
        git reset --quiet
        throw "Snapshot blocked:`n - $($problems -join "`n - ")"
    }

    git diff --cached --check
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'The staged diff contains whitespace warnings; scientific files were not rewritten automatically.'
    }
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) {
        throw 'git commit failed.'
    }

    if ($Push) {
        $origin = git remote get-url origin 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $origin) {
            throw 'Commit created locally, but no origin remote is configured.'
        }
        git push origin HEAD
        if ($LASTEXITCODE -ne 0) {
            throw 'git push failed; the local commit is preserved.'
        }
    }
}
finally {
    Pop-Location
}
