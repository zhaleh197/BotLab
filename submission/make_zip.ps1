# Builds BotLab_submission.zip: links, video link, the three PDFs and the full source code.
# Before running, export the three PDFs into this folder (see README in chat):
#   technical.pdf, business_plan.pdf, pitch.pdf
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$repo = Split-Path $here -Parent
$out  = Join-Path $here "BotLab_submission"
$zip  = Join-Path $here "BotLab_submission.zip"

foreach ($f in "technical.pdf", "business_plan.pdf", "pitch.pdf") {
    if (-not (Test-Path (Join-Path $here $f))) { Write-Warning "Missing $f in $here" }
}
if ((Get-Content (Join-Path $here "video_link.txt") -Raw) -match "\[") { Write-Warning "video_link.txt still has the placeholder" }

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory $out | Out-Null
Copy-Item (Join-Path $here "product_link.txt"), (Join-Path $here "video_link.txt") $out
Get-ChildItem $here -Filter *.pdf | Copy-Item -Destination $out

# Source code exactly as committed (no node_modules, .venv, .env or databases).
git -C $repo archive --format=zip -o (Join-Path $out "source_code.zip") HEAD

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $out "*") -DestinationPath $zip
Write-Host "Done: $zip"
