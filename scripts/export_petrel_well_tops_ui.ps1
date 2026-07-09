param(
    [string]$ProjectName = "Petrel2010 demo project",
    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",
    [string]$ProjectPath = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",
    [string]$PetrelVersion = "2018.2.0.5333",
    [string]$InventoryPackage = "",
    [string]$ExportPackage = "",
    [int]$PetrelProcessId = 0,
    [string]$LicenseProfile = "BatchProfile",
    [string]$LicensePackage = "",
    [ValidateSet("Dash", "Slash")]
    [string]$PetrelOptionStyle = "Slash",
    [string]$TargetSubfolder = "02_wells\well_tops",
    [string]$Extension = "txt",
    [string]$OutputFileName = "",
    [string]$FormatPattern = "Petrel.*well.*tops.*ASCII|Well Tops.*ASCII",
    [string]$TesseractPath = "",
    [string]$DriveLetter = "P",
    [int]$TimeoutSeconds = 240,
    [int]$LicenseDialogTimeoutSeconds = 25,
    [int]$StableFileTicks = 3,
    [int]$FilePollSeconds = 2,
    [int]$WellTopsRelativeX = 91,
    [int]$WellTopsRelativeY = 546,
    [int]$ExportObjectRelativeX = 221,
    [int]$ExportObjectRelativeY = 415,
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

$driver = Join-Path $PSScriptRoot "export_petrel_well_logs_ui.ps1"
$driverArgs = @{
    ProjectName = $ProjectName
    ProjectFile = $ProjectFile
    ProjectPath = $ProjectPath
    PetrelVersion = $PetrelVersion
    InventoryPackage = $InventoryPackage
    ExportPackage = $ExportPackage
    LicenseProfile = $LicenseProfile
    LicensePackage = $(if ([string]::IsNullOrWhiteSpace($LicensePackage)) { $LicenseProfile } else { $LicensePackage })
    ExportKind = "WellTops"
    PetrelOptionStyle = $PetrelOptionStyle
    TargetSubfolder = $TargetSubfolder
    Extension = $Extension
    FormatPattern = $FormatPattern
    TesseractPath = $TesseractPath
    DriveLetter = $DriveLetter
    TimeoutSeconds = $TimeoutSeconds
    LicenseDialogTimeoutSeconds = $LicenseDialogTimeoutSeconds
    StableFileTicks = $StableFileTicks
    FilePollSeconds = $FilePollSeconds
    WellTopsRelativeX = $WellTopsRelativeX
    WellTopsRelativeY = $WellTopsRelativeY
    ExportObjectRelativeX = $ExportObjectRelativeX
    ExportObjectRelativeY = $ExportObjectRelativeY
}

if ($PetrelProcessId -gt 0) {
    $driverArgs.PetrelProcessId = $PetrelProcessId
}
if (-not [string]::IsNullOrWhiteSpace($OutputFileName)) {
    $driverArgs.OutputFileName = $OutputFileName
}
if ($OpenProjectWritable) {
    $driverArgs.OpenProjectWritable = $true
}
if ($AllowExistingTarget) {
    $driverArgs.AllowExistingTarget = $true
}
if ($NoRegister) {
    $driverArgs.NoRegister = $true
}
if ($NoValidate) {
    $driverArgs.NoValidate = $true
}
if ($KeepDriveMapping) {
    $driverArgs.KeepDriveMapping = $true
}
if ($CoordinateFallback) {
    $driverArgs.CoordinateFallback = $true
}
if ($ContextMenuKeyboard) {
    $driverArgs.ContextMenuKeyboard = $true
}

& $driver @driverArgs
