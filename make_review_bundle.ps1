# make_review_bundle.ps1
# Automates the packaging of ReviewBundle.zip for external technical audit

param(
    [string]$SourceDir = "$PSScriptRoot\ReviewBundle",
    [string]$DestinationZip = "$PSScriptRoot\ReviewBundle.zip"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  OpenEOS ReviewBundle Packaging Tool" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not (Test-Path $SourceDir)) {
    Write-Error "Source directory '$SourceDir' does not exist."
    exit 1
}

if (Test-Path $DestinationZip) {
    Write-Host "Removing existing archive: $DestinationZip" -ForegroundColor Yellow
    Remove-Item $DestinationZip -Force
}

Write-Host "Compressing bundle files from: $SourceDir" -ForegroundColor White
Compress-Archive -Path "$SourceDir\*" -DestinationPath $DestinationZip -Force

if (Test-Path $DestinationZip) {
    $zipItem = Get-Item $DestinationZip
    Write-Host "Archive created successfully!" -ForegroundColor Green
    Write-Host "Path: $($zipItem.FullName)"
    Write-Host "Size: $([math]::Round($zipItem.Length / 1KB, 2)) KB"
} else {
    Write-Error "Failed to create archive."
    exit 1
}
