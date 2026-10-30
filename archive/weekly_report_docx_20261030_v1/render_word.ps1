param(
    [Parameter(Mandatory = $true)][string]$InputDocx,
    [Parameter(Mandatory = $true)][string]$OutputPdf
)

$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputPdf) { throw 'Render destination already exists' }
$reportWord = $null
$reportDocument = $null
try {
    $reportWord = New-Object -ComObject Word.Application
    $reportWord.Visible = $false
    $reportWord.DisplayAlerts = 0
    $reportWord.AutomationSecurity = 3
    $reportDocument = $reportWord.Documents.Open($InputDocx, $false, $true, $false)
    $reportDocument.ExportAsFixedFormat($OutputPdf, 17)
    Write-Output "Word exported $($reportDocument.ComputeStatistics(2)) pages"
} finally {
    if ($null -ne $reportDocument) {
        try { $reportDocument.Close(0) } catch { Write-Warning "Word close: $($_.Exception.Message)" }
        try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($reportDocument) } catch { }
    }
    if ($null -ne $reportWord) {
        try { $reportWord.Quit() } catch { Write-Warning "Word quit: $($_.Exception.Message)" }
        try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($reportWord) } catch { }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
