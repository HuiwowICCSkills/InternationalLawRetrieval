# Locate a Python that can run this skill, then hand off to gil_research.py.
# Prefer a candidate with the headless Cloudflare fallback dependencies, then
# PDF extraction, then basic search. Missing browser dependencies disable the
# ICJ/HUDOC/SSRN fallbacks; the remaining channels keep working.
$gilCandidates = @(
    (Join-Path $PSScriptRoot 'venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'),
    (Join-Path $env:USERPROFILE '.workbuddy\binaries\python\versions\3.13.12\python.exe')
)
$gilPathPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($gilPathPython) { $gilCandidates += $gilPathPython }

function Get-GilPythonScore {
    param([string]$Candidate)
    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return 0 }
    & $Candidate -c 'import requests, bs4' 2>$null
    if ($LASTEXITCODE -ne 0) { return 0 }
    & $Candidate -c 'import pypdf' 2>$null
    if ($LASTEXITCODE -ne 0) { return 1 }
    & $Candidate -c 'import DrissionPage, curl_cffi, psutil' 2>$null
    if ($LASTEXITCODE -eq 0) { return 3 }
    return 2
}

$gilPython = $null
$gilBestScore = 0
foreach ($gilCandidate in $gilCandidates) {
    $gilScore = Get-GilPythonScore $gilCandidate
    if ($gilScore -gt $gilBestScore) {
        $gilPython = $gilCandidate
        $gilBestScore = $gilScore
        if ($gilBestScore -eq 3) { break }
    }
}
if (-not $gilPython) {
    throw 'No Python with requests and beautifulsoup4 was found. Install requirements.txt or run scripts/setup-venvs.ps1.'
}
if ($gilBestScore -lt 3) {
    Write-Warning 'Selected Python lacks headless browser dependencies; ICJ, HUDOC and SSRN Cloudflare fallbacks are unavailable. Install requirements.txt for full functionality.'
}
if ($gilBestScore -lt 2) {
    Write-Warning 'Selected Python lacks pypdf; PDF text extraction may fail.'
}
$gilArguments = foreach ($gilArgument in $args) {
    if ($gilArgument -is [array]) { $gilArgument -join ',' } else { $gilArgument }
}
& $gilPython -X utf8 (Join-Path $PSScriptRoot 'gil_research.py') $gilArguments
exit $LASTEXITCODE
