# Exporterar spelets maskiner till en zip-fil för fordon_katalog.py på servern.
#
# Tar bara med maskinernas XML-filer (namn, märke, kategori, pris, mått) och butiksbilderna
# (store_*.dds), inga modeller eller texturer. Filerna stannar på dina egna datorer.
#
# Kör i PowerShell på Windows-datorn:
#   powershell -ExecutionPolicy Bypass -File fordon_export.ps1
#   powershell -ExecutionPolicy Bypass -File fordon_export.ps1 -Spel "D:\SteamLibrary\steamapps\common\Farming Simulator 25" -UtanBilder
#
# Kopiera sedan zip-filen till servern:
#   scp "$env:USERPROFILE\Downloads\FS25_fordon_data.zip" root@ClaudeVM:~/FS_sweden_map/data/fordon/
param(
    [string]$Spel = "D:\SteamLibrary\steamapps\common\Farming Simulator 25",
    [string]$Ut = "$env:USERPROFILE\Downloads\FS25_fordon_data.zip",
    [switch]$UtanBilder
)
$ErrorActionPreference = "Stop"
$fordon = Join-Path $Spel "data\vehicles"
if (-not (Test-Path $fordon)) { throw "Hittar inte $fordon. Ange spelets mapp med -Spel." }

$tmp = Join-Path $env:TEMP "FS25_fordon_data"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
$filter = @("*.xml")
if (-not $UtanBilder) { $filter += "store*.dds" }
$filer = Get-ChildItem $fordon -Recurse -File -Include $filter
foreach ($f in $filer) {
    $rel = $f.FullName.Substring($Spel.Length).TrimStart('\')        # data\vehicles\...
    $mal = Join-Path $tmp $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $mal) | Out-Null
    Copy-Item $f.FullName $mal
}
if (Test-Path $Ut) { Remove-Item $Ut -Force }
Compress-Archive -Path (Join-Path $tmp "data") -DestinationPath $Ut
Remove-Item $tmp -Recurse -Force
$mb = [math]::Round((Get-Item $Ut).Length / 1MB, 1)
Write-Host "Skrev $Ut ($($filer.Count) filer, $mb MB)."
Write-Host "Kopiera den till servern: scp `"$Ut`" root@ClaudeVM:~/FS_sweden_map/data/fordon/"
