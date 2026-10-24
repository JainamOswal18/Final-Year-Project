"""The Windows helper: one click on "Open in Power BI" downloads the project and opens it in Power BI Desktop.

A browser cannot start Power BI Desktop. The helper is a small PowerShell script registered once as the handler for
locallens:// links. It only accepts links that point at the LocalLens server it was installed from, and it only
downloads from the single-use path the server creates (see links.py). Built here so the server's own address is
written into the config at download time."""
from __future__ import annotations

import io
import json
import zipfile
from urllib.parse import urlsplit

OPEN_SCRIPT = r"""# LocalLens: open a chart in Power BI Desktop. Started by the locallens:// link handler.
param([Parameter(Position = 0)][string]$Link)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Web
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Fail([string]$Message) {
    [System.Windows.MessageBox]::Show($Message, 'LocalLens', 'OK', 'Warning') | Out-Null
    exit 1
}

try {
    $root = Join-Path $env:LOCALAPPDATA 'LocalLens'
    $cfg = Get-Content (Join-Path $root 'config.json') -Raw | ConvertFrom-Json

    # browsers may rewrite locallens://open?u=... as locallens://open/?u=... or drop the slashes
    $Link = "$Link".Trim().Trim('"')
    if ($Link -notmatch '^locallens:(//)?open/?\?') { Fail ('This is not a LocalLens link. Received: ' + $Link) }
    $query = [System.Web.HttpUtility]::ParseQueryString($Link.Substring($Link.IndexOf('?') + 1))
    if (-not $query['u']) { Fail 'The link has no download address.' }
    $u = [Uri]$query['u']

    # only the server this helper was installed for, and only the one-time download path
    $origin = $u.GetLeftPart([UriPartial]::Authority)
    if ($origin -ne $cfg.server) {
        Fail "This link points to $origin, not to your LocalLens server ($($cfg.server)). Nothing was downloaded."
    }
    if ($u.AbsolutePath -notmatch '^/api/export/dl/[A-Za-z0-9_-]{20,}$') { Fail 'Unexpected link. Nothing was downloaded.' }

    $zip = Join-Path ([IO.Path]::GetTempPath()) ('locallens-' + [Guid]::NewGuid().ToString('N') + '.zip')
    Invoke-WebRequest -Uri $u.AbsoluteUri -OutFile $zip -UseBasicParsing

    # a new folder per click; folders older than two weeks are removed
    $exports = Join-Path $root 'exports'
    New-Item -ItemType Directory -Path $exports -Force | Out-Null
    Get-ChildItem $exports -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    $dest = Join-Path $exports (Get-Date -Format 'yyyyMMdd-HHmmss')
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    $destFull = [IO.Path]::GetFullPath($dest) + [IO.Path]::DirectorySeparatorChar

    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        foreach ($e in $archive.Entries) {
            $target = [IO.Path]::GetFullPath((Join-Path $dest $e.FullName))
            if (-not $target.StartsWith($destFull, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'The download contained an unsafe file path.'
            }
            if ($e.FullName.EndsWith('/')) { New-Item -ItemType Directory -Path $target -Force | Out-Null; continue }
            New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target, $true)
        }
    } finally {
        $archive.Dispose()
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
    }

    $pbip = Get-ChildItem -Path $dest -Filter *.pbip -Recurse | Select-Object -First 1
    if (-not $pbip) { Fail 'The download did not contain a Power BI project.' }
    Start-Process -FilePath $pbip.FullName
} catch {
    Fail ('Could not open the chart in Power BI: ' + $_.Exception.Message)
}
"""

INSTALL_SCRIPT = r"""# LocalLens helper: run once per Windows user (no administrator rights needed).
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Join-Path $env:LOCALAPPDATA 'LocalLens'
New-Item -ItemType Directory -Path $root -Force | Out-Null
Copy-Item (Join-Path $here 'locallens-open.ps1') $root -Force
Copy-Item (Join-Path $here 'config.json') $root -Force
Unblock-File (Join-Path $root 'locallens-open.ps1') -ErrorAction SilentlyContinue

$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$cmd = '"' + $ps + '" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $root 'locallens-open.ps1') + '" "%1"'
$key = 'HKCU:\Software\Classes\locallens'
New-Item -Path $key -Force | Out-Null
Set-ItemProperty -Path $key -Name '(default)' -Value 'URL:LocalLens'
New-ItemProperty -Path $key -Name 'URL Protocol' -Value '' -Force | Out-Null
New-Item -Path "$key\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "$key\shell\open\command" -Name '(default)' -Value $cmd
$server = (Get-Content (Join-Path $root 'config.json') -Raw | ConvertFrom-Json).server
Write-Host "Done. Open in Power BI now works from $server in your browser."
Write-Host 'The first time, your browser asks whether to open LocalLens: allow it.'
"""

UNINSTALL_SCRIPT = r"""# LocalLens helper: remove it.
Remove-Item -Path 'HKCU:\Software\Classes\locallens' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path (Join-Path $env:LOCALAPPDATA 'LocalLens') -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'LocalLens helper removed.'
"""

BAT = '@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0{script}"\r\npause\r\n'

README = """LocalLens helper for Windows
============================
What it does: the "Open in Power BI" button in LocalLens downloads the chart as a Power BI project and opens it in
Power BI Desktop, in one click.

Install (once):  double-click install.bat. No administrator rights are needed.
Remove:          double-click uninstall.bat.

Needs Power BI Desktop on this computer and a browser on this computer. Each click opens a new copy of the project
(kept under %LOCALAPPDATA%\\LocalLens\\exports for two weeks).

Safety: the helper only accepts links that point at {server}, the LocalLens server this copy was made for, and only
the one-time download path that server creates. It does not run anything from the download; it only unzips it and
opens the .pbip file in Power BI Desktop.
"""


def origin_of(base_url: str) -> str:
    """scheme://host[:port], lower case, the form the helper compares against."""
    parts = urlsplit(base_url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def build_helper_zip(server_origin: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("LocalLens-helper/config.json", json.dumps({"server": server_origin}, indent=2))
        z.writestr("LocalLens-helper/locallens-open.ps1", OPEN_SCRIPT.replace("\n", "\r\n"))
        z.writestr("LocalLens-helper/install.ps1", INSTALL_SCRIPT.replace("\n", "\r\n"))
        z.writestr("LocalLens-helper/uninstall.ps1", UNINSTALL_SCRIPT.replace("\n", "\r\n"))
        z.writestr("LocalLens-helper/install.bat", BAT.format(script="install.ps1"))
        z.writestr("LocalLens-helper/uninstall.bat", BAT.format(script="uninstall.ps1"))
        z.writestr("LocalLens-helper/README.txt", README.format(server=server_origin).replace("\n", "\r\n"))
    return buf.getvalue()
