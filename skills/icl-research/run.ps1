# Locate a Python that can run this skill, then hand off to icl_search.py.
# Prefer a candidate with requests, beautifulsoup4 and pypdf; accept one with
# only the first two and warn, because PDF extraction is optional per query.
$iclCandidates = @(
    (Join-Path $PSScriptRoot 'venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'),
    (Join-Path $env:USERPROFILE '.workbuddy\binaries\python\versions\3.13.12\python.exe')
)
$iclPathPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($iclPathPython) { $iclCandidates += $iclPathPython }

function Get-IclPythonScore {
    param([string]$Candidate)
    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return 0 }
    & $Candidate -c 'import requests, bs4' 2>$null
    if ($LASTEXITCODE -ne 0) { return 0 }
    & $Candidate -c 'import pypdf' 2>$null
    if ($LASTEXITCODE -eq 0) { return 2 }
    return 1
}

$iclPython = $null
$iclBestScore = 0
foreach ($iclCandidate in $iclCandidates) {
    $iclScore = Get-IclPythonScore $iclCandidate
    if ($iclScore -gt $iclBestScore) {
        $iclPython = $iclCandidate
        $iclBestScore = $iclScore
        if ($iclBestScore -eq 2) { break }
    }
}
if (-not $iclPython) {
    throw 'No Python with requests and beautifulsoup4 was found. Install scripts/requirements.txt or run scripts/setup-venvs.ps1.'
}
if ($iclBestScore -lt 2) {
    Write-Warning 'Selected Python lacks pypdf; PDF text extraction may fail. Install scripts/requirements.txt for full functionality.'
}
$iclArguments = foreach ($iclArgument in $args) {
    if ($iclArgument -is [array]) { $iclArgument -join ',' } else { $iclArgument }
}
& $iclPython -X utf8 (Join-Path $PSScriptRoot 'scripts\icl_search.py') $iclArguments
exit $LASTEXITCODE
