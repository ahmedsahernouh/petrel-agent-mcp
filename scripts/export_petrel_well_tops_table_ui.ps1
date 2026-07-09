param(
    [string]$ProjectName = "Petrel2010 demo project",
    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",
    [string]$ProjectPath = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",
    [string]$PetrelVersion = "2018.2.0.5333",
    [string]$InventoryPackage = "",
    [string]$ExportPackage = "",
    [int]$PetrelProcessId = 0,
    [string]$LicenseProfile = "BatchProfile",
    [ValidateSet("Dash", "Slash")]
    [string]$PetrelOptionStyle = "Slash",
    [string]$TargetSubfolder = "02_wells\well_tops",
    [string]$Extension = "txt",
    [string]$OutputFileName = "",
    [string]$FormatPattern = "",
    [string]$DriveLetter = "P",
    [int]$TimeoutSeconds = 120,
    [int]$LicenseDialogTimeoutSeconds = 3,
    [int]$StableFileTicks = 1,
    [int]$FilePollSeconds = 1,
    [int]$WellTopsRelativeX = 91,
    [int]$WellTopsRelativeY = 185,
    [int]$ExportObjectRelativeX = 221,
    [int]$ExportObjectRelativeY = 246,
    [switch]$OpenProjectWritable,
    [switch]$AllowExistingTarget,
    [switch]$NoRegister,
    [switch]$NoValidate,
    [switch]$KeepDriveMapping,
    [switch]$CoordinateFallback,
    [switch]$ContextMenuKeyboard
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

if ([string]::IsNullOrWhiteSpace($ExportPackage)) {
    $ExportPackage = (Get-ChildItem -LiteralPath (Join-Path $repoRoot "build\export_pilots") -Directory -Filter "*_export_*" |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1).FullName
}
if ([string]::IsNullOrWhiteSpace($InventoryPackage)) {
    $latestInventory = Get-ChildItem -LiteralPath (Join-Path $repoRoot "build\inventory_pilots") -Directory -Filter "*_inventory_*" |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($null -ne $latestInventory) {
        $InventoryPackage = $latestInventory.FullName
    }
}
if ([string]::IsNullOrWhiteSpace($ExportPackage)) {
    throw "Export package was not supplied and no latest export package was found."
}

$targetRoot = Join-Path $ExportPackage $TargetSubfolder
$runDir = Join-Path $ExportPackage "07_workflows_reports\automation_runs"
$screenDir = Join-Path $runDir "ui_well_tops_table_export_$stamp"
New-Item -ItemType Directory -Force -Path $targetRoot, $runDir, $screenDir | Out-Null

if ([string]::IsNullOrWhiteSpace($OutputFileName)) {
    $OutputFileName = "well_tops_project_data_table_$stamp.$Extension"
}
if ([IO.Path]::GetExtension($OutputFileName) -eq "") {
    $OutputFileName = "$OutputFileName.$Extension"
}
$outputFile = Join-Path $targetRoot $OutputFileName
$statusPath = Join-Path $runDir "petrel_ui_well_tops_table_export_$stamp.json"
$tracePath = Join-Path $runDir "petrel_ui_well_tops_table_export_$stamp.trace.log"
$screenshots = New-Object System.Collections.Generic.List[string]

function Write-RunTrace {
    param([string]$Message)
    $line = "{0}`t{1}" -f (Get-Date).ToString("o"), $Message
    Add-Content -LiteralPath $script:tracePath -Value $line -Encoding UTF8
}

function Initialize-Native {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    if ($null -eq ("PetrelTableUiNative" -as [type])) {
        Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class PetrelTableUiNative {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool BringWindowToTop(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern void SwitchToThisWindow(IntPtr hWnd, bool fAltTab);

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int X, int Y);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
}
"@
    }
}

function Get-PetrelProcess {
    if ($PetrelProcessId -gt 0) {
        return Get-Process -Id $PetrelProcessId -ErrorAction Stop
    }

    $process = Get-Process -Name "Petrel" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 } |
        Sort-Object StartTime -Descending |
        Select-Object -First 1
    if ($null -eq $process) {
        throw "Petrel main window was not found."
    }
    return $process
}

function Get-ForegroundProcessId {
    $foreground = [PetrelTableUiNative]::GetForegroundWindow()
    if ($foreground -eq [IntPtr]::Zero) {
        return 0
    }
    $processId = [uint32]0
    [PetrelTableUiNative]::GetWindowThreadProcessId($foreground, [ref]$processId) | Out-Null
    return [int]$processId
}

function Focus-Window {
    param(
        [Parameter(Mandatory = $true)][IntPtr]$Handle,
        [Parameter(Mandatory = $true)][int]$ExpectedProcessId
    )

    [PetrelTableUiNative]::ShowWindow($Handle, 9) | Out-Null
    [PetrelTableUiNative]::BringWindowToTop($Handle) | Out-Null
    [PetrelTableUiNative]::SetForegroundWindow($Handle) | Out-Null
    Start-Sleep -Milliseconds 150
    [System.Windows.Forms.SendKeys]::SendWait("%")
    Start-Sleep -Milliseconds 100
    [PetrelTableUiNative]::SwitchToThisWindow($Handle, $true)
    [PetrelTableUiNative]::SetForegroundWindow($Handle) | Out-Null
    Start-Sleep -Milliseconds 600

    $foregroundPid = Get-ForegroundProcessId
    Write-RunTrace "focus foreground_pid=$foregroundPid expected_pid=$ExpectedProcessId"
    if ($foregroundPid -ne $ExpectedProcessId) {
        throw "Petrel window did not become foreground. Foreground PID is $foregroundPid; expected $ExpectedProcessId."
    }
}

function Get-WindowRect {
    param([Parameter(Mandatory = $true)][IntPtr]$Handle)
    $nativeRect = New-Object PetrelTableUiNative+RECT
    if (-not [PetrelTableUiNative]::GetWindowRect($Handle, [ref]$nativeRect)) {
        throw "Could not read Petrel window rectangle."
    }
    return [pscustomobject]@{
        Left = $nativeRect.Left
        Top = $nativeRect.Top
        Width = ($nativeRect.Right - $nativeRect.Left)
        Height = ($nativeRect.Bottom - $nativeRect.Top)
    }
}

function Click-Point {
    param(
        [Parameter(Mandatory = $true)][int]$X,
        [Parameter(Mandatory = $true)][int]$Y,
        [switch]$RightClick
    )

    [PetrelTableUiNative]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 80
    if ($RightClick) {
        [PetrelTableUiNative]::mouse_event(0x0008, 0, 0, 0, [UIntPtr]::Zero)
        [PetrelTableUiNative]::mouse_event(0x0010, 0, 0, 0, [UIntPtr]::Zero)
    } else {
        [PetrelTableUiNative]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
        [PetrelTableUiNative]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    }
    Start-Sleep -Milliseconds 250
}

function Save-Screenshot {
    param([Parameter(Mandatory = $true)][string]$FileName)
    $path = Join-Path $screenDir $FileName
    $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bitmap.Size)
        $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        [void]$screenshots.Add($path)
        Write-RunTrace "screenshot $FileName"
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Get-ClipboardTextSafe {
    try {
        return Get-Clipboard -Raw -ErrorAction Stop
    } catch {
        return ""
    }
}

function Copy-VisibleTableText {
    param([Parameter(Mandatory = $true)]$Rect)

    $attempts = @(
        [pscustomobject]@{ Name = "center_document"; X = [int]($Rect.Left + 820); Y = [int]($Rect.Top + 380) },
        [pscustomobject]@{ Name = "output_sheet_area"; X = [int]($Rect.Left + 630); Y = [int]($Rect.Top + 210) },
        [pscustomobject]@{ Name = "lower_table_area"; X = [int]($Rect.Left + 820); Y = [int]($Rect.Top + 690) }
    )

    foreach ($attempt in $attempts) {
        Write-RunTrace "copy attempt $($attempt.Name) click $($attempt.X),$($attempt.Y)"
        try {
            Set-Clipboard -Value "" -ErrorAction SilentlyContinue
        } catch {
            Write-RunTrace "clipboard clear failed: $($_.Exception.Message)"
        }
        Click-Point -X $attempt.X -Y $attempt.Y
        Start-Sleep -Milliseconds 300
        [System.Windows.Forms.SendKeys]::SendWait("^a")
        Start-Sleep -Milliseconds 300
        [System.Windows.Forms.SendKeys]::SendWait("^c")
        Start-Sleep -Seconds 1
        $text = Get-ClipboardTextSafe
        Write-RunTrace "copy attempt $($attempt.Name) clipboard_chars=$($text.Length)"
        if ($text -match "Well identifier" -and $text -match "Surface" -and $text -match "Depth") {
            return $text
        }
    }

    return Get-ClipboardTextSafe
}

$status = [ordered]@{
    run_id = "petrel_ui_well_tops_table_export_$stamp"
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    project_name = $ProjectName
    project_file = $ProjectFile
    export_kind = "WellTopsTable"
    inventory_package = $InventoryPackage
    export_package = $ExportPackage
    petrel_process_id = 0
    petrel_window_title = ""
    target_folder = $targetRoot
    extension = $Extension
    output_file_name = $OutputFileName
    output_file = $outputFile
    exported_file_count = 0
    exported_bytes = 0
    clipboard_char_count = 0
    clipboard_line_count = 0
    header_detected = $false
    screenshots = @()
    files = @()
    error = ""
}

$failed = $false
try {
    Write-RunTrace "start export_kind=WellTopsTable target_root=$targetRoot"
    Initialize-Native
    $petrel = Get-PetrelProcess
    $status.petrel_process_id = $petrel.Id
    $status.petrel_window_title = $petrel.MainWindowTitle
    Write-RunTrace "petrel process found pid=$($petrel.Id) title='$($petrel.MainWindowTitle)'"

    Focus-Window -Handle $petrel.MainWindowHandle -ExpectedProcessId $petrel.Id
    $rect = Get-WindowRect -Handle $petrel.MainWindowHandle
    Write-RunTrace "petrel rect $($rect.Left),$($rect.Top),$($rect.Width),$($rect.Height)"
    Save-Screenshot -FileName "01_petrel_ready.png"

    $wellTopsX = [int]($rect.Left + $WellTopsRelativeX)
    $wellTopsY = [int]($rect.Top + $WellTopsRelativeY)
    Write-RunTrace "right-click well tops at $wellTopsX,$wellTopsY"
    Click-Point -X $wellTopsX -Y $wellTopsY -RightClick
    Start-Sleep -Milliseconds 700
    Save-Screenshot -FileName "02_well_tops_context_menu.png"

    $menuX = [int]($rect.Left + $ExportObjectRelativeX)
    $menuY = [int]($rect.Top + $ExportObjectRelativeY)
    Write-RunTrace "click select-and-show menu at $menuX,$menuY"
    Click-Point -X $menuX -Y $menuY
    Start-Sleep -Seconds 3
    Save-Screenshot -FileName "03_after_project_data_table_command.png"

    $tableText = Copy-VisibleTableText -Rect $rect
    $status.clipboard_char_count = $tableText.Length
    $status.clipboard_line_count = @($tableText -split "`r?`n").Count
    $status.header_detected = ($tableText -match "Well identifier" -and $tableText -match "Surface" -and $tableText -match "Depth")

    if (-not $status.header_detected) {
        throw "Copied Petrel clipboard text did not contain a Well Tops table header."
    }

    Set-Content -LiteralPath $outputFile -Value $tableText -Encoding UTF8
    $fileInfo = Get-Item -LiteralPath $outputFile
    $status.exported_file_count = 1
    $status.exported_bytes = $fileInfo.Length
    $status.files = @($fileInfo.FullName)
} catch {
    $failed = $true
    $status.error = $_.Exception.Message
    Write-RunTrace "failed: $($status.error)"
} finally {
    $status.screenshots = @($screenshots)
    $status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-RunTrace "status written $statusPath"
}

Write-Output "UI WellTopsTable export: completed"
Write-Output "Petrel PID: $($status.petrel_process_id)"
Write-Output "Target folder: $targetRoot"
Write-Output "Exported files: $($status.exported_file_count)"
Write-Output "Exported bytes: $($status.exported_bytes)"
Write-Output "Clipboard chars: $($status.clipboard_char_count)"
Write-Output "Status file: $statusPath"

if ($failed) {
    throw $status.error
}
