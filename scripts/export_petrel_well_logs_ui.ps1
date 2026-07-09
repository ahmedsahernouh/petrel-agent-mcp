param(
    [string]$ProjectName = "Petrel2010 demo project",

    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",

    [string]$ProjectPath = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$InventoryRoot = "D:\Computer\Code\Petrel_project\build\inventory_pilots",

    [string]$ExportRoot = "D:\Computer\Code\Petrel_project\build\export_pilots",

    [string]$InventoryPackage = "",

    [string]$ExportPackage = "",

    [int]$PetrelProcessId = 0,

    [string]$LicenseProfile = "BatchProfile",

    [string]$LicensePackage = "",

    [ValidateSet("WellLogs", "WellTops")]
    [string]$ExportKind = "WellLogs",

    [ValidateSet("Dash", "Slash")]
    [string]$PetrelOptionStyle = "Slash",

    [string]$TargetSubfolder = "02_wells\well_logs_las",

    [string]$Extension = "las",

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
$script:PetrelUiTracePath = ""

function Write-RunTrace {
    param([Parameter(Mandatory = $true)][string]$Message)

    if ([string]::IsNullOrWhiteSpace($script:PetrelUiTracePath)) {
        return
    }

    $line = "{0}`t{1}" -f (Get-Date).ToString("o"), $Message
    Add-Content -LiteralPath $script:PetrelUiTracePath -Value $line -Encoding UTF8
}

function Get-LastNativeExitCode {
    $variable = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
    if ($null -eq $variable -or $null -eq $variable.Value) {
        return 0
    }
    return [int]$variable.Value
}

function Invoke-SubstCommand {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    $substPath = Join-Path $env:SystemRoot "System32\subst.exe"
    if (-not (Test-Path -LiteralPath $substPath -PathType Leaf)) {
        $substPath = "subst.exe"
    }

    $output = @()
    try {
        $output = @(& $substPath @Arguments 2>&1)
        $exitCode = Get-LastNativeExitCode
    } catch {
        if (-not $AllowFailure) {
            throw
        }
        $exitCode = 1
        $output = @($_.Exception.Message)
    }

    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "subst.exe failed with exit code $exitCode. Args: $($Arguments -join ' '). Output: $($output -join ' ')"
    }

    return [pscustomobject]@{
        exit_code = $exitCode
        output = ($output -join "`n")
    }
}

function Get-LatestPackage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,

        [Parameter(Mandatory = $true)]
        [string]$Pattern
    )

    if (-not (Test-Path -LiteralPath $Root)) {
        return ""
    }

    $item = Get-ChildItem -LiteralPath $Root -Directory -Filter $Pattern |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1

    if ($null -eq $item) {
        return ""
    }

    return $item.FullName
}

function Initialize-UiAutomation {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    if ($null -eq ("PetrelUiNative" -as [type])) {
        Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class PetrelUiNative {
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

function Get-AutomationRoot {
    return [System.Windows.Automation.AutomationElement]::RootElement
}

function New-NameCondition {
    param([Parameter(Mandatory = $true)][string]$Name)
    return New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $Name
    )
}

function New-ControlTypeCondition {
    param([Parameter(Mandatory = $true)][System.Windows.Automation.ControlType]$ControlType)
    return New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        $ControlType
    )
}

function Get-ElementRect {
    param([Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Element)
    return $Element.Current.BoundingRectangle
}

function Test-VisibleRect {
    param($Rect)
    return ($Rect.Width -gt 1 -and $Rect.Height -gt 1 -and $Rect.Left -gt -32000 -and $Rect.Top -gt -32000)
}

function Click-Point {
    param(
        [Parameter(Mandatory = $true)][int]$X,
        [Parameter(Mandatory = $true)][int]$Y,
        [switch]$RightClick
    )

    [PetrelUiNative]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 120
    if ($RightClick) {
        [PetrelUiNative]::mouse_event(0x0008, 0, 0, 0, [UIntPtr]::Zero)
        [PetrelUiNative]::mouse_event(0x0010, 0, 0, 0, [UIntPtr]::Zero)
    } else {
        [PetrelUiNative]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
        [PetrelUiNative]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    }
    Start-Sleep -Milliseconds 250
}

function Click-Element {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Element,
        [switch]$RightClick
    )

    $rect = Get-ElementRect -Element $Element
    if (-not (Test-VisibleRect -Rect $rect)) {
        throw "Element has no visible rectangle: $($Element.Current.Name)"
    }

    $x = [int]($rect.Left + ($rect.Width / 2))
    $y = [int]($rect.Top + ($rect.Height / 2))
    Click-Point -X $x -Y $y -RightClick:$RightClick
}

function Invoke-Element {
    param([Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Element)

    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
        $pattern.Invoke()
        Start-Sleep -Milliseconds 300
        return
    }

    Click-Element -Element $Element
}

function Select-Element {
    param([Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Element)

    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) {
        $pattern.Select()
        Start-Sleep -Milliseconds 300
        return
    }

    Click-Element -Element $Element
}

function Get-AncestorByControlType {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory = $true)][System.Windows.Automation.ControlType]$ControlType
    )

    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $node = $Element
    while ($null -ne $node) {
        if ($node.Current.ControlType -eq $ControlType) {
            return $node
        }
        $node = $walker.GetParent($node)
    }

    return $null
}

function Find-ButtonByDescendantText {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory = $true)][string]$Text
    )

    $textElement = Find-FirstByName -Root $Root -Name $Text
    if ($null -eq $textElement) {
        return $null
    }

    return Get-AncestorByControlType -Element $textElement -ControlType ([System.Windows.Automation.ControlType]::Button)
}

function Expand-Element {
    param([Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Element)

    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) {
        if ($pattern.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded) {
            $pattern.Expand()
            Start-Sleep -Milliseconds 600
        }
    }
}

function Find-FirstByName {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory = $true)][string]$Name,
        [System.Windows.Automation.TreeScope]$Scope = [System.Windows.Automation.TreeScope]::Descendants
    )

    return $Root.FindFirst($Scope, (New-NameCondition -Name $Name))
}

function Find-VisibleByNameInRect {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory = $true)][string]$Name,
        [double]$MinLeft,
        [double]$MaxLeft,
        [double]$MinTop,
        [double]$MaxTop
    )

    $matches = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, (New-NameCondition -Name $Name))
    foreach ($match in $matches) {
        try {
            $rect = Get-ElementRect -Element $match
            if ((Test-VisibleRect -Rect $rect) -and
                $rect.Left -ge $MinLeft -and $rect.Left -le $MaxLeft -and
                $rect.Top -ge $MinTop -and $rect.Top -le $MaxTop) {
                return $match
            }
        } catch {
            continue
        }
    }

    return $null
}

function Find-VisibleByNameOnDesktop {
    param([Parameter(Mandatory = $true)][string]$Name)

    $root = Get-AutomationRoot
    $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $matches = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, (New-NameCondition -Name $Name))
    foreach ($match in $matches) {
        try {
            $rect = Get-ElementRect -Element $match
            if ((Test-VisibleRect -Rect $rect) -and
                $rect.Left -ge $bounds.Left -and $rect.Left -le ($bounds.Left + $bounds.Width) -and
                $rect.Top -ge $bounds.Top -and $rect.Top -le ($bounds.Top + $bounds.Height)) {
                return $match
            }
        } catch {
            continue
        }
    }

    return $null
}

function Wait-VisibleByNameOnDesktop {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [int]$Timeout = 30
    )

    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $element = Find-VisibleByNameOnDesktop -Name $Name
        if ($null -ne $element) {
            return $element
        }
        Start-Sleep -Milliseconds 500
    }

    return $null
}

function Find-ContextMenuItemByName {
    # Fast context-menu item finder. A Win32/WPF context menu is its own top-level
    # window (class #32768 or ControlType Menu), so we only descend into those small
    # popup subtrees and never walk the Petrel main window's enormous UIA tree. This
    # replaces the whole-desktop FindAll(Descendants) scan that cost 10-20s per call.
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [int]$Timeout = 2
    )

    $root = Get-AutomationRoot
    $nameCondition = New-NameCondition -Name $Name
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $children = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($child in $children) {
            try {
                $controlType = $child.Current.ControlType
                $className = [string]$child.Current.ClassName
                $isPopup = ($className -eq "#32768") -or
                           ($controlType -eq [System.Windows.Automation.ControlType]::Menu) -or
                           ($controlType -eq [System.Windows.Automation.ControlType]::Window -and [string]::IsNullOrWhiteSpace([string]$child.Current.Name))
                if (-not $isPopup) {
                    continue
                }
                $item = $child.FindFirst([System.Windows.Automation.TreeScope]::Subtree, $nameCondition)
                if ($null -ne $item) {
                    $rect = Get-ElementRect -Element $item
                    if (Test-VisibleRect -Rect $rect) {
                        return $item
                    }
                }
            } catch {
                continue
            }
        }
        Start-Sleep -Milliseconds 120
    }

    return $null
}

function Find-FirstByRegex {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [System.Windows.Automation.TreeScope]$Scope = [System.Windows.Automation.TreeScope]::Descendants
    )

    $matches = $Root.FindAll($Scope, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($match in $matches) {
        try {
            $name = [string]$match.Current.Name
            if ($name -match $Pattern) {
                return $match
            }
        } catch {
            continue
        }
    }

    return $null
}

function Wait-ByName {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory = $true)][string]$Name,
        [int]$Timeout = 30,
        [System.Windows.Automation.TreeScope]$Scope = [System.Windows.Automation.TreeScope]::Descendants
    )

    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $element = Find-FirstByName -Root $Root -Name $Name -Scope $Scope
        if ($null -ne $element) {
            return $element
        }
        Start-Sleep -Milliseconds 500
    }

    return $null
}

function Wait-TopLevelByRegex {
    param(
        [Parameter(Mandatory = $true)][string]$Pattern,
        [int]$Timeout = 30
    )

    $root = Get-AutomationRoot
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $element = Find-FirstByRegex -Root $root -Pattern $Pattern -Scope ([System.Windows.Automation.TreeScope]::Children)
        if ($null -ne $element) {
            return $element
        }
        Start-Sleep -Milliseconds 500
    }

    return $null
}

function Find-TopLevelWindowByTitleRegex {
    param(
        [Parameter(Mandatory = $true)][string]$Pattern,
        [int]$ProcessId = 0,
        [int]$Timeout = 2
    )

    $root = Get-AutomationRoot
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $children = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($child in $children) {
            try {
                if ($ProcessId -gt 0 -and [int]$child.Current.ProcessId -ne $ProcessId) {
                    continue
                }
                $name = [string]$child.Current.Name
                if (-not [string]::IsNullOrWhiteSpace($name) -and $name -match $Pattern) {
                    return $child
                }
            } catch {
                continue
            }
        }
        Start-Sleep -Milliseconds 150
    }

    return $null
}

function Find-WindowByRegexDeep {
    param(
        [Parameter(Mandatory = $true)][string]$Pattern,
        [int]$ProcessId = 0,
        [int]$Timeout = 2
    )

    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $topLevel = Find-TopLevelWindowByTitleRegex -Pattern $Pattern -ProcessId $ProcessId -Timeout 1
        if ($null -ne $topLevel) {
            return $topLevel
        }

        $root = Get-AutomationRoot
        $children = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($child in $children) {
            try {
                if ($ProcessId -gt 0 -and [int]$child.Current.ProcessId -ne $ProcessId) {
                    continue
                }
                $windows = $child.FindAll([System.Windows.Automation.TreeScope]::Descendants, (New-ControlTypeCondition -ControlType ([System.Windows.Automation.ControlType]::Window))
                )
                foreach ($window in $windows) {
                    $name = [string]$window.Current.Name
                    $rect = Get-ElementRect -Element $window
                    if ((Test-VisibleRect -Rect $rect) -and -not [string]::IsNullOrWhiteSpace($name) -and $name -match $Pattern) {
                        return $window
                    }
                }
            } catch {
                continue
            }
        }
        Start-Sleep -Milliseconds 150
    }

    return $null
}

function Wait-TopLevelContainingText {
    param(
        [Parameter(Mandatory = $true)][string]$Pattern,
        [int]$Timeout = 30
    )

    $root = Get-AutomationRoot
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $children = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($child in $children) {
            try {
                $name = [string]$child.Current.Name
                if ($name -match $Pattern) {
                    return $child
                }
                $descendant = Find-FirstByRegex -Root $child -Pattern $Pattern
                if ($null -ne $descendant) {
                    return $child
                }
            } catch {
                continue
            }
        }
        Start-Sleep -Milliseconds 500
    }

    return $null
}

function Wait-DescendantByRegex {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [int]$Timeout = 30
    )

    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $element = Find-FirstByRegex -Root $Root -Pattern $Pattern
        if ($null -ne $element) {
            return $element
        }
        Start-Sleep -Milliseconds 500
    }

    return $null
}

function Set-ValueOrType {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
        $pattern.SetValue($Value)
        Start-Sleep -Milliseconds 200
        return
    }

    Click-Element -Element $Element
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    [System.Windows.Forms.SendKeys]::SendWait($Value)
}

function Save-Screenshot {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [System.Windows.Automation.AutomationElement]$Element = $null
    )

    $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $rect = $null
    if ($null -ne $Element) {
        $candidate = Get-ElementRect -Element $Element
        if (Test-VisibleRect -Rect $candidate) {
            $rect = $candidate
        }
    }

    if ($null -eq $rect) {
        $rect = [pscustomobject]@{
            Left = $bounds.Left
            Top = $bounds.Top
            Width = $bounds.Width
            Height = $bounds.Height
        }
    } else {
        $left = [Math]::Max([double]$rect.Left, [double]$bounds.Left)
        $top = [Math]::Max([double]$rect.Top, [double]$bounds.Top)
        $right = [Math]::Min([double]($rect.Left + $rect.Width), [double]($bounds.Left + $bounds.Width))
        $bottom = [Math]::Min([double]($rect.Top + $rect.Height), [double]($bounds.Top + $bounds.Height))
        if (($right -le $left) -or ($bottom -le $top)) {
            $left = $bounds.Left
            $top = $bounds.Top
            $right = $bounds.Left + $bounds.Width
            $bottom = $bounds.Top + $bounds.Height
        }
        $rect = [pscustomobject]@{
            Left = $left
            Top = $top
            Width = ($right - $left)
            Height = ($bottom - $top)
        }
    }

    $bitmap = New-Object System.Drawing.Bitmap([int]$rect.Width, [int]$rect.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen([int]$rect.Left, [int]$rect.Top, 0, 0, $bitmap.Size)
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    } catch {
        Write-Warning "Screenshot capture failed for ${Path}: $($_.Exception.Message)"
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Add-DiagnosticScreenshot {
    param([Parameter(Mandatory = $true)][string]$FileName)

    if ([string]::IsNullOrWhiteSpace($script:screenDir)) {
        return
    }

    $path = Join-Path $script:screenDir $FileName
    try {
        Write-RunTrace "screenshot $FileName begin"
        Save-Screenshot -Path $path
        Write-RunTrace "screenshot $FileName end"
        if ($null -ne $script:screenshots) {
            [void]$script:screenshots.Add($path)
        }
    } catch {
        Write-RunTrace "screenshot $FileName failed: $($_.Exception.Message)"
    }
}

function Resolve-TesseractPath {
    param([string]$ExplicitPath = "")

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $candidates += $ExplicitPath
    }
    $envPath = [Environment]::GetEnvironmentVariable("PETREL_TESSERACT_PATH")
    if (-not [string]::IsNullOrWhiteSpace($envPath)) {
        $candidates += $envPath
    }
    $candidates += @(
        "C:\Program Files\Tesseract-OCR\tesseract.exe",
        "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
    )

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $command = Get-Command "tesseract.exe" -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    throw "Tesseract OCR was not found. Install it or pass -TesseractPath."
}

function Convert-ToInvariantDouble {
    param([object]$Value)

    return [double]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture)
}

function Find-OcrTextInImage {
    param(
        [Parameter(Mandatory = $true)][string]$ImagePath,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [double]$MinLeft = -100000,
        [double]$MaxLeft = 100000,
        [double]$MinTop = -100000,
        [double]$MaxTop = 100000,
        [double]$MinConfidence = 45,
        [int]$PageSegmentationMode = 6
    )

    $tesseract = Resolve-TesseractPath -ExplicitPath $TesseractPath
    $output = & $tesseract $ImagePath "stdout" "-l" "eng" "--psm" ([string]$PageSegmentationMode) "tsv" 2>$null
    if ((Get-LastNativeExitCode) -ne 0) {
        throw "Tesseract failed while reading $ImagePath."
    }
    if ($null -eq $output -or @($output).Count -eq 0) {
        return $null
    }

    $rows = @($output | ConvertFrom-Csv -Delimiter "`t")
    $words = New-Object System.Collections.ArrayList
    foreach ($row in $rows) {
        try {
            $text = ([string]$row.text).Trim()
            if ([string]::IsNullOrWhiteSpace($text)) {
                continue
            }
            $confidence = Convert-ToInvariantDouble -Value $row.conf
            if ($confidence -lt $MinConfidence) {
                continue
            }
            $left = [int](Convert-ToInvariantDouble -Value $row.left)
            $top = [int](Convert-ToInvariantDouble -Value $row.top)
            $width = [int](Convert-ToInvariantDouble -Value $row.width)
            $height = [int](Convert-ToInvariantDouble -Value $row.height)
            $right = $left + $width
            $bottom = $top + $height
            if ($right -lt $MinLeft -or $left -gt $MaxLeft -or $bottom -lt $MinTop -or $top -gt $MaxTop) {
                continue
            }
            [void]$words.Add([pscustomobject]@{
                text = $text
                confidence = $confidence
                left = $left
                top = $top
                width = $width
                height = $height
                block_num = [string]$row.block_num
                par_num = [string]$row.par_num
                line_num = [string]$row.line_num
                word_num = [int](Convert-ToInvariantDouble -Value $row.word_num)
            })
        } catch {
            continue
        }
    }

    $wordHits = @($words | Where-Object { $_.text -match $Pattern } | Sort-Object top, left)
    if ($wordHits.Count -gt 0) {
        $word = $wordHits[0]
        return [pscustomobject]@{
            text = $word.text
            confidence = [math]::Round($word.confidence, 2)
            left = [int]$word.left
            top = [int]$word.top
            width = [int]$word.width
            height = [int]$word.height
            image_path = $ImagePath
        }
    }

    $groups = @($words | Group-Object -Property block_num, par_num, line_num)
    $ocrHits = New-Object System.Collections.ArrayList
    foreach ($group in $groups) {
        $items = @($group.Group | Sort-Object word_num)
        if ($items.Count -eq 0) {
            continue
        }
        $text = ($items | ForEach-Object { $_.text }) -join " "
        if ($text -notmatch $Pattern) {
            continue
        }
        $left = ($items | Measure-Object -Property left -Minimum).Minimum
        $top = ($items | Measure-Object -Property top -Minimum).Minimum
        $right = ($items | ForEach-Object { $_.left + $_.width } | Measure-Object -Maximum).Maximum
        $bottom = ($items | ForEach-Object { $_.top + $_.height } | Measure-Object -Maximum).Maximum
        $confidence = [math]::Round((($items | Measure-Object -Property confidence -Average).Average), 2)
        [void]$ocrHits.Add([pscustomobject]@{
            text = $text
            confidence = $confidence
            left = [int]$left
            top = [int]$top
            width = [int]($right - $left)
            height = [int]($bottom - $top)
            image_path = $ImagePath
        })
    }

    if ($ocrHits.Count -eq 0) {
        return $null
    }
    return @($ocrHits | Sort-Object top, left)[0]
}

function Save-OcrUpscaledCrop {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [Parameter(Mandatory = $true)][int]$X,
        [Parameter(Mandatory = $true)][int]$Y,
        [Parameter(Mandatory = $true)][int]$Width,
        [Parameter(Mandatory = $true)][int]$Height,
        [int]$Scale = 3
    )

    $source = [System.Drawing.Bitmap]::FromFile($SourcePath)
    try {
        $target = New-Object System.Drawing.Bitmap ($Width * $Scale), ($Height * $Scale)
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($target)
            try {
                # NearestNeighbor keeps the anti-aliased UI text strokes bit-exact when
                # upscaling; GDI+ bicubic smooths them into mid-gray, which defeats
                # Tesseract's binarization even though the result looks fine to the eye.
                $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
                $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
                $sourceRect = New-Object System.Drawing.Rectangle $X, $Y, $Width, $Height
                $targetRect = New-Object System.Drawing.Rectangle 0, 0, ($Width * $Scale), ($Height * $Scale)
                $graphics.DrawImage($source, $targetRect, $sourceRect, [System.Drawing.GraphicsUnit]::Pixel)
            } finally {
                $graphics.Dispose()
            }
            $target.Save($TargetPath, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally {
            $target.Dispose()
        }
    } finally {
        $source.Dispose()
    }
}

function Find-OcrTextInWindowRegion {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$FileName,
        [double]$MinLeft,
        [double]$MaxLeft,
        [double]$MinTop,
        [double]$MaxTop,
        [double]$MinConfidence = 45
    )

    $path = Join-Path $script:screenDir $FileName
    Save-Screenshot -Path $path -Element $MainWindow
    if ($null -ne $script:screenshots) {
        [void]$script:screenshots.Add($path)
    }

    # Tesseract is unreliable on ~11px UI labels at native resolution, which made the
    # tree/tab scans flaky. Crop the requested region and upscale it before OCR, then
    # map hit coordinates back to window-relative pixels for the callers.
    $sourceImage = [System.Drawing.Bitmap]::FromFile($path)
    try {
        $imageWidth = $sourceImage.Width
        $imageHeight = $sourceImage.Height
    } finally {
        $sourceImage.Dispose()
    }

    $cropLeft = [int][math]::Max(0, [math]::Floor($MinLeft))
    $cropTop = [int][math]::Max(0, [math]::Floor($MinTop))
    $cropRight = [int][math]::Min($imageWidth, [math]::Ceiling($MaxLeft))
    $cropBottom = [int][math]::Min($imageHeight, [math]::Ceiling($MaxTop))
    $cropWidth = $cropRight - $cropLeft
    $cropHeight = $cropBottom - $cropTop
    if ($cropWidth -lt 8 -or $cropHeight -lt 8) {
        Write-RunTrace "ocr_region: degenerate crop for $FileName left=$cropLeft top=$cropTop width=$cropWidth height=$cropHeight"
        return $null
    }

    $scale = 3
    $processedPath = $path -replace "\.png$", "_proc.png"
    Save-OcrUpscaledCrop -SourcePath $path -TargetPath $processedPath -X $cropLeft -Y $cropTop -Width $cropWidth -Height $cropHeight -Scale $scale
    if ($null -ne $script:screenshots) {
        [void]$script:screenshots.Add($processedPath)
    }

    $hit = Find-OcrTextInImage -ImagePath $processedPath -Pattern $Pattern -MinConfidence $MinConfidence
    if ($null -eq $hit) {
        return $null
    }

    return [pscustomobject]@{
        text = $hit.text
        confidence = $hit.confidence
        left = [int]($cropLeft + ($hit.left / $scale))
        top = [int]($cropTop + ($hit.top / $scale))
        width = [int][math]::Max(1, [math]::Round($hit.width / $scale))
        height = [int][math]::Max(1, [math]::Round($hit.height / $scale))
        image_path = $processedPath
    }
}

function Find-OcrTextInWindowElement {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow,
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$FileName,
        [double]$MinConfidence = 45
    )

    $mainRect = Get-ElementRect -Element $MainWindow
    $elementRect = Get-ElementRect -Element $Element
    $minLeft = [math]::Max(0, $elementRect.Left - $mainRect.Left - 8)
    $maxLeft = [math]::Max($minLeft + 1, $elementRect.Left + $elementRect.Width - $mainRect.Left + 8)
    $minTop = [math]::Max(0, $elementRect.Top - $mainRect.Top - 8)
    $maxTop = [math]::Max($minTop + 1, $elementRect.Top + $elementRect.Height - $mainRect.Top + 8)

    return Find-OcrTextInWindowRegion -MainWindow $MainWindow -Pattern $Pattern -FileName $FileName -MinLeft $minLeft -MaxLeft $maxLeft -MinTop $minTop -MaxTop $maxTop -MinConfidence $MinConfidence
}

function Find-ExplorerInputTabByOcr {
    param([Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow)

    # Search regions must scale with the window: the Explorer tab strip (Input/Models/
    # Results/Templates) sits at the bottom of the tree pane, so its vertical position
    # tracks window height, and the docked pane width can be widened by the operator.
    # Fixed pixel caps (MaxTop 720, MaxLeft 430) silently missed the strip when the
    # window was resized larger. The sibling/left-of-Models/reject-Processes checks
    # below still constrain false matches, so a wider search is safe.
    $mainRect = Get-ElementRect -Element $MainWindow
    $paneMaxLeft = [int][math]::Min([math]::Max(450, $mainRect.Width * 0.45), 900)
    $paneMaxTop = [int]$mainRect.Height

    $models = Find-OcrTextInWindowRegion -MainWindow $MainWindow -Pattern "\bModels\b" -FileName "02a_explorer_tabs_models_ocr.png" -MinLeft 0 -MaxLeft $paneMaxLeft -MinTop 0 -MaxTop $paneMaxTop -MinConfidence 30
    if ($null -eq $models) {
        Write-RunTrace "explorer_input_tab: Models tab anchor not found (search maxleft=$paneMaxLeft maxtop=$paneMaxTop)"
        return $null
    }

    $stripTop = [int][math]::Max(0, $models.top - 24)
    $stripBottom = [int]($models.top + $models.height + 30)
    $inputMaxLeft = [int][math]::Max(90, $models.left + 20)
    $input = Find-OcrTextInWindowRegion -MainWindow $MainWindow -Pattern "\bInput\b" -FileName "02a_explorer_tabs_input_ocr.png" -MinLeft 0 -MaxLeft $inputMaxLeft -MinTop $stripTop -MaxTop $stripBottom -MinConfidence 25
    $results = Find-OcrTextInWindowRegion -MainWindow $MainWindow -Pattern "\bResults\b" -FileName "02a_explorer_tabs_results_ocr.png" -MinLeft 0 -MaxLeft $paneMaxLeft -MinTop $stripTop -MaxTop $stripBottom -MinConfidence 25
    $templates = Find-OcrTextInWindowRegion -MainWindow $MainWindow -Pattern "\bTemplates\b" -FileName "02a_explorer_tabs_templates_ocr.png" -MinLeft 0 -MaxLeft $paneMaxLeft -MinTop $stripTop -MaxTop $stripBottom -MinConfidence 25

    # Sibling data tabs (Models is required; Results/Templates confirm the strip).
    $siblingLabels = New-Object System.Collections.ArrayList
    [void]$siblingLabels.Add("Models")
    if ($null -ne $results) { [void]$siblingLabels.Add("Results") }
    if ($null -ne $templates) { [void]$siblingLabels.Add("Templates") }
    # Require Models plus at least one other data tab. Demanding all three caused
    # false negatives: OCR reliably reads the bold active label but can miss a
    # dimmer sibling. The geometry and reject-below-Processes guards below still
    # prevent activating the wrong location.
    if ($siblingLabels.Count -lt 2) {
        Write-RunTrace "explorer_input_tab: rejected because no sibling data tab was found next to Models. found=$($siblingLabels -join ',') strip=$stripTop-$stripBottom"
        return $null
    }

    # The Input tab is the leftmost of a fixed strip: Input | Models | Results |
    # Templates. OCR reads the ~11px "Input" glyph only intermittently (and it
    # restyles when active), but "Models"/"Results" read reliably. So if the direct
    # "Input" OCR misses, synthesize its click point from tab geometry: one tab
    # pitch left of Models, where pitch = Results.left - Models.left. This removes
    # the run's dependence on reading the tiny Input label at all.
    $inputSynthesized = $false
    if ($null -eq $input) {
        $pitch = $null
        if ($null -ne $results) { $pitch = [int]($results.left - $models.left) }
        elseif ($null -ne $templates) { $pitch = [int](($templates.left - $models.left) / 2) }
        if ($null -ne $pitch -and $pitch -ge 30 -and $pitch -le 200) {
            $synthLeft = [int]($models.left - $pitch)
            if ($synthLeft -ge 0) {
                $input = [pscustomobject]@{
                    text = "Input(synth)"
                    left = $synthLeft
                    top = [int]$models.top
                    width = [int][math]::Min($pitch - 4, $models.width + 10)
                    height = [int]$models.height
                    confidence = 0
                }
                $inputSynthesized = $true
                Write-RunTrace "explorer_input_tab: Input OCR missed; synthesized from Models/Results geometry pitch=$pitch left=$synthLeft top=$($models.top)"
            }
        }
        if ($null -eq $input) {
            Write-RunTrace "explorer_input_tab: Input label not found and could not synthesize from geometry (models_left=$($models.left) results=$($null -ne $results) templates=$($null -ne $templates))"
            return $null
        }
    }
    if (-not $inputSynthesized -and $input.left -gt ($models.left + 8)) {
        Write-RunTrace "explorer_input_tab: rejected Input '$($input.text)' because it is not left of Models. input_left=$($input.left) models_left=$($models.left)"
        return $null
    }

    $processes = Find-OcrTextInWindowRegion -MainWindow $MainWindow -Pattern "\bProcesses\b" -FileName "02a_processes_header_ocr.png" -MinLeft 0 -MaxLeft 240 -MinTop $stripTop -MaxTop ([int]($stripBottom + 180)) -MinConfidence 25
    if ($null -ne $processes -and $input.top -gt $processes.top) {
        Write-RunTrace "explorer_input_tab: rejected Input below Processes header. input_top=$($input.top) processes_top=$($processes.top)"
        return $null
    }

    Add-Member -InputObject $input -MemberType NoteProperty -Name "context" -Value "explorer_data_tab_strip" -Force
    Add-Member -InputObject $input -MemberType NoteProperty -Name "sibling_labels" -Value (@($siblingLabels)) -Force
    Add-Member -InputObject $input -MemberType NoteProperty -Name "strip_top" -Value $stripTop -Force
    Add-Member -InputObject $input -MemberType NoteProperty -Name "strip_bottom" -Value $stripBottom -Force
    Write-RunTrace "explorer_input_tab: confirmed Input tab '$($input.text)' with siblings $($siblingLabels -join ',') rect $($input.left),$($input.top),$($input.width),$($input.height)"
    return $input
}

function Activate-ExplorerInputTab {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow,
        [switch]$FailClosed
    )

    # Self-heal: retry the OCR find across a few Petrel repaints. When another tab
    # (e.g. Models) is active, the tree redraw can lag the first OCR pass; a short
    # retry lets the tab strip settle instead of failing the run outright.
    $match = $null
    for ($attempt = 1; $attempt -le 3 -and $null -eq $match; $attempt++) {
        $match = Find-ExplorerInputTabByOcr -MainWindow $MainWindow
        if ($null -eq $match -and $attempt -lt 3) {
            Write-RunTrace "explorer_input_tab: find attempt $attempt did not confirm the Input tab; brief settle then retry"
            Start-Sleep -Milliseconds 400
        }
    }
    if ($null -eq $match) {
        $message = "Explorer Input tab was not confirmed after 3 attempts. The selector requires the data tab strip (Input left of Models, with at least one of Results/Templates) and rejects Processes > Input."
        if ($FailClosed) {
            throw $message
        }
        Write-RunTrace "explorer_input_tab: $message"
        return $null
    }

    # Click the Input tab to make it active. Do NOT re-run OCR to "confirm" the
    # switch: the "Input" label is an ~11px glyph that Tesseract reads only
    # intermittently (observed finding it once then missing it 4x at the same
    # position in one run). A second OCR pass adds no certainty and was the actual
    # failure point. The click on a confirmed Input-tab match reliably activates
    # the pane; the caller uses the returned match to bound the tree scan.
    Click-OcrWindowMatch -MainWindow $MainWindow -Match $match | Out-Null
    Start-Sleep -Milliseconds 400
    return $match
}

function Find-BlueSelectedRowInImage {
    param(
        [Parameter(Mandatory = $true)][string]$ImagePath,
        [int]$MinLeft,
        [int]$MaxLeft,
        [int]$MinTop,
        [int]$MaxTop
    )

    $bitmap = [System.Drawing.Bitmap]::FromFile($ImagePath)
    try {
        $blueRows = New-Object System.Collections.ArrayList
        $rightLimit = [math]::Min($MaxLeft, $bitmap.Width - 1)
        $bottomLimit = [math]::Min($MaxTop, $bitmap.Height - 1)
        for ($y = [math]::Max(0, $MinTop); $y -le $bottomLimit; $y++) {
            $count = 0
            $rowMinX = $rightLimit
            $rowMaxX = $MinLeft
            for ($x = [math]::Max(0, $MinLeft); $x -le $rightLimit; $x++) {
                $pixel = $bitmap.GetPixel($x, $y)
                if ($pixel.B -gt 100 -and $pixel.R -lt 90 -and $pixel.G -lt 140 -and ($pixel.B - $pixel.R) -gt 45) {
                    $count += 1
                    if ($x -lt $rowMinX) { $rowMinX = $x }
                    if ($x -gt $rowMaxX) { $rowMaxX = $x }
                }
            }
            if ($count -ge 8) {
                [void]$blueRows.Add([pscustomobject]@{ y = $y; min_x = $rowMinX; max_x = $rowMaxX; count = $count })
            }
        }

        if ($blueRows.Count -eq 0) {
            return $null
        }

        $blueGroups = New-Object System.Collections.ArrayList
        $current = $null
        foreach ($row in @($blueRows | Sort-Object y)) {
            if ($null -eq $current -or $row.y -gt ($current.bottom + 1)) {
                if ($null -ne $current) { [void]$blueGroups.Add($current) }
                $current = [pscustomobject]@{ top = $row.y; bottom = $row.y; left = $row.min_x; right = $row.max_x; pixels = $row.count }
            } else {
                $current.bottom = $row.y
                if ($row.min_x -lt $current.left) { $current.left = $row.min_x }
                if ($row.max_x -gt $current.right) { $current.right = $row.max_x }
                $current.pixels += $row.count
            }
        }
        if ($null -ne $current) { [void]$blueGroups.Add($current) }

        $candidate = @($blueGroups |
            Where-Object { ($_.bottom - $_.top) -ge 4 -and ($_.right - $_.left) -ge 20 } |
            Sort-Object pixels -Descending |
            Select-Object -First 1)
        if ($candidate.Count -eq 0) {
            return $null
        }

        $item = $candidate[0]
        return [pscustomobject]@{
            text = "selected_blue_row"
            confidence = 100
            left = [int]$item.left
            top = [int]$item.top
            width = [int]($item.right - $item.left)
            height = [int]($item.bottom - $item.top)
            image_path = $ImagePath
        }
    } finally {
        $bitmap.Dispose()
    }
}

function Find-BlueSelectedRowInWindowRegion {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow,
        [Parameter(Mandatory = $true)][string]$FileName,
        [int]$MinLeft,
        [int]$MaxLeft,
        [int]$MinTop,
        [int]$MaxTop
    )

    $path = Join-Path $script:screenDir $FileName
    Save-Screenshot -Path $path -Element $MainWindow
    if ($null -ne $script:screenshots) {
        [void]$script:screenshots.Add($path)
    }
    return Find-BlueSelectedRowInImage -ImagePath $path -MinLeft $MinLeft -MaxLeft $MaxLeft -MinTop $MinTop -MaxTop $MaxTop
}

function Click-OcrWindowMatch {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow,
        [Parameter(Mandatory = $true)][object]$Match,
        [switch]$RightClick
    )

    $mainRect = Get-ElementRect -Element $MainWindow
    $x = [int]($mainRect.Left + $Match.left + ($Match.width / 2))
    $y = [int]($mainRect.Top + $Match.top + ($Match.height / 2))
    Click-Point -X $x -Y $y -RightClick:$RightClick
    return [pscustomobject]@{ x = $x; y = $y }
}

function Find-OcrTextOnDesktopNear {
    param(
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][int]$AnchorX,
        [Parameter(Mandatory = $true)][int]$AnchorY,
        [Parameter(Mandatory = $true)][string]$FileName,
        [int]$LeftPad = 80,
        [int]$RightPad = 360,
        [int]$TopPad = 80,
        [int]$BottomPad = 420,
        [double]$MinConfidence = 35,
        [int]$PageSegmentationMode = 6
    )

    $path = Join-Path $script:screenDir $FileName
    Save-Screenshot -Path $path
    if ($null -ne $script:screenshots) {
        [void]$script:screenshots.Add($path)
    }

    $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $minLeft = [math]::Max(0, $AnchorX - $bounds.Left - $LeftPad)
    $maxLeft = [math]::Min($bounds.Width, $AnchorX - $bounds.Left + $RightPad)
    $minTop = [math]::Max(0, $AnchorY - $bounds.Top - $TopPad)
    $maxTop = [math]::Min($bounds.Height, $AnchorY - $bounds.Top + $BottomPad)
    $match = Find-OcrTextInImage -ImagePath $path -Pattern $Pattern -MinLeft $minLeft -MaxLeft $maxLeft -MinTop $minTop -MaxTop $maxTop -MinConfidence $MinConfidence -PageSegmentationMode $PageSegmentationMode
    if ($null -eq $match) {
        return $null
    }
    Add-Member -InputObject $match -MemberType NoteProperty -Name "screen_left" -Value $bounds.Left -Force
    Add-Member -InputObject $match -MemberType NoteProperty -Name "screen_top" -Value $bounds.Top -Force
    return $match
}

function Find-BlueSelectedRowOnDesktopNear {
    param(
        [Parameter(Mandatory = $true)][int]$AnchorX,
        [Parameter(Mandatory = $true)][int]$AnchorY,
        [Parameter(Mandatory = $true)][string]$FileName,
        [int]$LeftPad = 80,
        [int]$RightPad = 360,
        [int]$TopPad = 220,
        [int]$BottomPad = 320
    )

    $path = Join-Path $script:screenDir $FileName
    Save-Screenshot -Path $path
    if ($null -ne $script:screenshots) {
        [void]$script:screenshots.Add($path)
    }

    $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $minLeft = [math]::Max(0, $AnchorX - $bounds.Left - $LeftPad)
    $maxLeft = [math]::Min($bounds.Width, $AnchorX - $bounds.Left + $RightPad)
    $minTop = [math]::Max(0, $AnchorY - $bounds.Top - $TopPad)
    $maxTop = [math]::Min($bounds.Height, $AnchorY - $bounds.Top + $BottomPad)
    $match = Find-BlueSelectedRowInImage -ImagePath $path -MinLeft ([int]$minLeft) -MaxLeft ([int]$maxLeft) -MinTop ([int]$minTop) -MaxTop ([int]$maxTop)
    if ($null -eq $match) {
        return $null
    }
    Add-Member -InputObject $match -MemberType NoteProperty -Name "screen_left" -Value $bounds.Left -Force
    Add-Member -InputObject $match -MemberType NoteProperty -Name "screen_top" -Value $bounds.Top -Force
    return $match
}

function Click-OcrDesktopMatch {
    param([Parameter(Mandatory = $true)][object]$Match)

    $x = [int]($Match.screen_left + $Match.left + ($Match.width / 2))
    $y = [int]($Match.screen_top + $Match.top + ($Match.height / 2))
    Click-Point -X $x -Y $y
    return [pscustomobject]@{ x = $x; y = $y }
}

function Get-PetrelProcess {
    param([int]$ProcessId)

    if ($ProcessId -gt 0) {
        return Get-Process -Id $ProcessId -ErrorAction Stop
    }

    $processes = @(Get-Process -Name "Petrel" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 } |
        Sort-Object StartTime -Descending)

    if ($processes.Count -eq 0) {
        return $null
    }

    return $processes[0]
}

function Wait-PetrelProcess {
    param(
        [int]$ProcessId,
        [int]$Timeout = 90
    )

    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $process = Get-PetrelProcess -ProcessId $ProcessId
        if ($null -ne $process -and $process.MainWindowHandle -ne 0) {
            return $process
        }
        Start-Sleep -Seconds 1
    }

    throw "Petrel main window was not found within $Timeout seconds."
}

function Wait-PetrelReadyWindow {
    param(
        [int]$ProcessId,
        [int]$Timeout = 180
    )

    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $process = Get-PetrelProcess -ProcessId $ProcessId
        if ($null -ne $process -and
            $process.MainWindowHandle -ne 0 -and
            -not [string]::IsNullOrWhiteSpace($process.MainWindowTitle) -and
            -not ([string]$process.MainWindowTitle -match "License selection")) {
            return $process
        }
        Start-Sleep -Seconds 1
    }

    throw "Petrel project window was not ready within $Timeout seconds."
}

function Get-ForegroundProcessId {
    $foreground = [PetrelUiNative]::GetForegroundWindow()
    if ($foreground -eq [IntPtr]::Zero) {
        return 0
    }

    $processId = [uint32]0
    [PetrelUiNative]::GetWindowThreadProcessId($foreground, [ref]$processId) | Out-Null
    return [int]$processId
}

function Normalize-PetrelWindow {
    # Self-healing layout: the Explorer tree/tab strip has no UIA accessibility, so it
    # can only be read visually - which means the window must be a workable, predictable
    # size. Rather than depend on however the operator left the window (small, huge, or
    # on either monitor of a dual-screen / remote-desktop session), maximize it to a
    # deterministic size when it is minimized or too small. All OCR regions are already
    # window-relative, so once the window is a known large size the visual scans are
    # stable regardless of monitor, position, or prior size.
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow,
        [int]$MinWidth = 1200,
        [int]$MinHeight = 800
    )

    $handle = [IntPtr]$MainWindow.Current.NativeWindowHandle
    if ($handle -eq [IntPtr]::Zero) {
        return "no_handle"
    }
    # 9 = SW_RESTORE (undo a minimized state so bounds are real).
    [PetrelUiNative]::ShowWindow($handle, 9) | Out-Null
    Start-Sleep -Milliseconds 200
    $rect = Get-ElementRect -Element $MainWindow
    if ($rect.Width -ge $MinWidth -and $rect.Height -ge $MinHeight) {
        Write-RunTrace "normalize_window: size ok $($rect.Width)x$($rect.Height)"
        return "ok_$($rect.Width)x$($rect.Height)"
    }
    # 3 = SW_MAXIMIZE for a deterministic large layout.
    [PetrelUiNative]::ShowWindow($handle, 3) | Out-Null
    Start-Sleep -Milliseconds 500
    $rect2 = Get-ElementRect -Element $MainWindow
    Write-RunTrace "normalize_window: maximized from $($rect.Width)x$($rect.Height) to $($rect2.Width)x$($rect2.Height)"
    return "maximized_$($rect2.Width)x$($rect2.Height)"
}

function Focus-Window {
    param(
        [Parameter(Mandatory = $true)][IntPtr]$Handle,
        [int]$ExpectedProcessId = 0
    )

    [PetrelUiNative]::ShowWindow($Handle, 9) | Out-Null
    [PetrelUiNative]::BringWindowToTop($Handle) | Out-Null
    [PetrelUiNative]::SetForegroundWindow($Handle) | Out-Null
    Start-Sleep -Milliseconds 150
    # The ALT tap only helps satisfy Windows' foreground-lock rule. SendInput can be
    # transiently denied (UIPI / another window holding foreground / an open menu),
    # and that must not abort the run: SwitchToThisWindow + SetForegroundWindow below
    # still take focus, and the foreground-PID check is the real gate.
    try {
        [System.Windows.Forms.SendKeys]::SendWait("%")
    } catch {
        Write-RunTrace "focus: ALT tap denied ($($_.Exception.Message)); continuing with SwitchToThisWindow"
    }
    Start-Sleep -Milliseconds 100
    [PetrelUiNative]::SwitchToThisWindow($Handle, $true)
    [PetrelUiNative]::SetForegroundWindow($Handle) | Out-Null
    Start-Sleep -Milliseconds 600

    if ($ExpectedProcessId -gt 0) {
        $foregroundPid = Get-ForegroundProcessId
        Write-RunTrace "focus foreground_pid=$foregroundPid expected_pid=$ExpectedProcessId"
        if ($foregroundPid -ne $ExpectedProcessId) {
            # One transient retry: the earlier foreground holder may have released.
            Start-Sleep -Milliseconds 400
            [PetrelUiNative]::SwitchToThisWindow($Handle, $true)
            [PetrelUiNative]::SetForegroundWindow($Handle) | Out-Null
            Start-Sleep -Milliseconds 400
            $foregroundPid = Get-ForegroundProcessId
            Write-RunTrace "focus retry foreground_pid=$foregroundPid expected_pid=$ExpectedProcessId"
            if ($foregroundPid -ne $ExpectedProcessId) {
                throw "Petrel window did not become foreground. Foreground PID is $foregroundPid; expected $ExpectedProcessId."
            }
        }
    }
}

function Select-LicenseProfileIfShown {
    param(
        [string]$ProfileName,
        [int]$Timeout = 20
    )

    $dialog = Wait-TopLevelByRegex -Pattern "License selection" -Timeout $Timeout
    if ($null -eq $dialog) {
        return "not_shown"
    }

    $profile = Wait-ByName -Root $dialog -Name $ProfileName -Timeout 10
    if ($null -eq $profile) {
        throw "License selection dialog is open, but profile was not found: $ProfileName"
    }

    $profileItem = Get-AncestorByControlType -Element $profile -ControlType ([System.Windows.Automation.ControlType]::ListItem)
    if ($null -ne $profileItem) {
        Select-Element -Element $profileItem
    } else {
        Select-Element -Element $profile
    }

    $ok = Find-ButtonByDescendantText -Root $dialog -Text "OK"
    if ($null -eq $ok) {
        $ok = Wait-ByName -Root $dialog -Name "OK" -Timeout 10
    }
    if ($null -eq $ok) {
        throw "License selection dialog is open, but OK button was not found."
    }

    Invoke-Element -Element $ok
    return "selected_$ProfileName"
}

function Select-BrowseFolderDrive {
    param(
        [Parameter(Mandatory = $true)][string]$DriveLetter,
        [int]$Timeout = 45
    )

    $dialog = Wait-TopLevelByRegex -Pattern "Browse For Folder" -Timeout $Timeout
    if ($null -eq $dialog) {
        throw "Browse For Folder dialog did not appear."
    }

    $thisPc = Find-FirstByName -Root $dialog -Name "This PC"
    if ($null -eq $thisPc) {
        $thisPc = Find-FirstByName -Root $dialog -Name "Computer"
    }
    if ($null -ne $thisPc) {
        Expand-Element -Element $thisPc
    }

    $drivePattern = "\($([regex]::Escape($DriveLetter)):\)"
    $drive = Wait-DescendantByRegex -Root $dialog -Pattern $drivePattern -Timeout 20
    if ($null -eq $drive) {
        throw "Mapped drive $DriveLetter`: was not found in Browse For Folder."
    }

    Select-Element -Element $drive

    $ok = Wait-ByName -Root $dialog -Name "OK" -Timeout 10
    if ($null -eq $ok) {
        throw "Browse For Folder OK button was not found."
    }

    Invoke-Element -Element $ok
}

function Confirm-ExtensionDialog {
    param(
        [Parameter(Mandatory = $true)][string]$Extension,
        [int]$Timeout = 30
    )

    $dialog = Wait-TopLevelContainingText -Pattern "file extension" -Timeout $Timeout
    if ($null -eq $dialog) {
        throw "File extension dialog did not appear."
    }

    $message = Wait-DescendantByRegex -Root $dialog -Pattern "file extension" -Timeout 5
    if ($null -eq $message -and ([string]$dialog.Current.Name) -notmatch "file extension") {
        throw "Could not confirm that the visible dialog is the file extension dialog."
    }

    $editCondition = New-ControlTypeCondition -ControlType ([System.Windows.Automation.ControlType]::Edit)
    $edit = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCondition)
    if ($null -ne $edit) {
        Set-ValueOrType -Element $edit -Value $Extension
    } else {
        [System.Windows.Forms.SendKeys]::SendWait($Extension)
    }

    $ok = Find-FirstByName -Root $dialog -Name "OK"
    if ($null -ne $ok) {
        Invoke-Element -Element $ok
    } else {
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    }
}

function Find-WellTopsInInputTree {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [int]$MaxPages = 12,
        [object]$ExplorerInputTabMatch = $null
    )

    $rect = Get-ElementRect -Element $MainWindow
    # Bound the tree scan just above the Explorer tab strip. The prior fixed 650 cap
    # cut the scan short on taller windows where the strip sits far lower; derive the
    # fallback from window height instead so it scales.
    $scanMaxTop = [int][math]::Max(140, $rect.Height - 120)
    if ($null -ne $ExplorerInputTabMatch) {
        $scanMaxTop = [int][math]::Max(140, $ExplorerInputTabMatch.top - 4)
        Write-RunTrace "welltops_menu: input tree OCR scan bounded above Explorer tab strip max_top=$scanMaxTop tab_top=$($ExplorerInputTabMatch.top)"
    } else {
        Write-RunTrace "welltops_menu: input tree OCR scan has no Explorer tab-strip bound; using height-derived max_top=$scanMaxTop"
    }

    $treeX = [int]($rect.Left + 165)
    $treeY = [int]($rect.Top + 250)
    Click-Point -X $treeX -Y $treeY
    Start-Sleep -Milliseconds 150

    [System.Windows.Forms.SendKeys]::SendWait("^{HOME}")
    Start-Sleep -Milliseconds 350

    for ($page = 0; $page -lt $MaxPages; $page++) {
        $fileName = "02a_input_pane_scan_{0:00}.png" -f $page
        $match = Find-OcrTextInWindowRegion -MainWindow $MainWindow -Pattern $Pattern -FileName $fileName -MinLeft 0 -MaxLeft 330 -MinTop 140 -MaxTop $scanMaxTop -MinConfidence 0
        if ($null -ne $match) {
            Write-RunTrace "welltops_menu: scan found Well Tops on page=$page text='$($match.text)' rect $($match.left),$($match.top),$($match.width),$($match.height)"
            return $match
        }

        $wellsMatch = Find-OcrTextInWindowRegion -MainWindow $MainWindow -Pattern "\b(Wells|Wate|Wel)\b" -FileName ("02a_input_pane_scan_wells_{0:00}.png" -f $page) -MinLeft 0 -MaxLeft 230 -MinTop 140 -MaxTop $scanMaxTop -MinConfidence 20
        if ($null -ne $wellsMatch) {
            Write-RunTrace "welltops_menu: scan saw Wells row on page=$page text='$($wellsMatch.text)'"
            $mainRect = Get-ElementRect -Element $MainWindow
            $expandX = [int]($mainRect.Left + [math]::Max(4, $wellsMatch.left - 48))
            $expandY = [int]($mainRect.Top + $wellsMatch.top + ($wellsMatch.height / 2))
            Click-Point -X $expandX -Y $expandY
            Start-Sleep -Milliseconds 350
            $match = Find-OcrTextInWindowRegion -MainWindow $MainWindow -Pattern $Pattern -FileName ("02a_input_pane_scan_after_wells_{0:00}.png" -f $page) -MinLeft 0 -MaxLeft 330 -MinTop 140 -MaxTop $scanMaxTop -MinConfidence 0
            if ($null -ne $match) {
                Write-RunTrace "welltops_menu: scan found Well Tops after Wells click page=$page text='$($match.text)' rect $($match.left),$($match.top),$($match.width),$($match.height)"
                return $match
            }
        }

        [System.Windows.Forms.SendKeys]::SendWait("{PGDN}")
        Start-Sleep -Milliseconds 350
    }

    return $null
}

function Invoke-WellLogsExportMenu {
    param([Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow)

    if ($MainWindow.Current.NativeWindowHandle -ne 0) {
        Focus-Window -Handle ([IntPtr]$MainWindow.Current.NativeWindowHandle) -ExpectedProcessId ([int]$MainWindow.Current.ProcessId)
    }

    $rect = Get-ElementRect -Element $MainWindow
    $input = Find-VisibleByNameInRect -Root $MainWindow -Name "Input" -MinLeft $rect.Left -MaxLeft ($rect.Left + 450) -MinTop $rect.Top -MaxTop ($rect.Top + 700)
    $inputRect = $null
    if ($null -ne $input) {
        Click-Element -Element $input
        $inputRect = Get-ElementRect -Element $input
    } else {
        Click-Point -X ([int]($rect.Left + 29)) -Y ([int]($rect.Top + 250))
    }

    Start-Sleep -Seconds 1

    $wells = Find-VisibleByNameInRect -Root $MainWindow -Name "Wells" -MinLeft $rect.Left -MaxLeft ($rect.Left + 450) -MinTop $rect.Top -MaxTop ($rect.Top + 450)
    if ($MainWindow.Current.NativeWindowHandle -ne 0) {
        Focus-Window -Handle ([IntPtr]$MainWindow.Current.NativeWindowHandle) -ExpectedProcessId ([int]$MainWindow.Current.ProcessId)
    }
    if ($null -ne $wells) {
        Click-Element -Element $wells -RightClick
    } elseif ($null -ne $inputRect -and (Test-VisibleRect -Rect $inputRect)) {
        Click-Point -X ([int]($inputRect.Left + 78)) -Y ([int]($inputRect.Top + 29)) -RightClick
    } else {
        Click-Point -X ([int]($rect.Left + 92)) -Y ([int]($rect.Top + 106)) -RightClick
    }

    $menuItem = Wait-VisibleByNameOnDesktop -Name "Export all logs in folder" -Timeout 15
    if ($null -eq $menuItem) {
        throw "The Wells context menu did not expose 'Export all logs in folder'."
    }

    Invoke-Element -Element $menuItem
}

function Invoke-WellTopsExportMenu {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow,
        [switch]$CoordinateFallback
    )

    Write-RunTrace "welltops_menu: focus main window"
    if ($MainWindow.Current.NativeWindowHandle -ne 0) {
        Focus-Window -Handle ([IntPtr]$MainWindow.Current.NativeWindowHandle) -ExpectedProcessId ([int]$MainWindow.Current.ProcessId)
    }

    $rect = Get-ElementRect -Element $MainWindow
        Write-RunTrace "welltops_menu: main rect $($rect.Left),$($rect.Top),$($rect.Width),$($rect.Height)"

    # Activate the Explorer Input data tab once, in BOTH modes. If a leftover
    # Models/Results/Templates view is active, the coordinate click (or the OCR
    # tree scan) would land on the wrong tree - this is the "Models pane was up
    # instead of Input pane" failure. This one call runs the full fail-closed
    # selector (Input left of Models, sibling data tab present, not Processes>Input)
    # and clicks the confirmed tab. Its result is reused below so we never re-run
    # the flaky ~11px "Input" OCR a second time in the same run.
    $inputTabMatch = $null
    try {
        $inputTabMatch = Activate-ExplorerInputTab -MainWindow $MainWindow
    } catch {
        Write-RunTrace "welltops_menu: Input tab activation error $($_.Exception.Message)"
    }
    if ($null -ne $inputTabMatch) {
        Write-RunTrace "welltops_menu: activated Explorer Input tab '$($inputTabMatch.text)' rect $($inputTabMatch.left),$($inputTabMatch.top),$($inputTabMatch.width),$($inputTabMatch.height)"
    } else {
        Write-RunTrace "welltops_menu: Input tab activation not confirmed on first pass"
    }

    if ($CoordinateFallback) {
        $wellTopsX = [int]($rect.Left + $WellTopsRelativeX)
        $wellTopsY = [int]($rect.Top + $WellTopsRelativeY)
        Write-RunTrace "welltops_menu: coordinate fallback select at $wellTopsX,$wellTopsY"
        Click-Point -X $wellTopsX -Y $wellTopsY
        Start-Sleep -Milliseconds 300
        Write-RunTrace "welltops_menu: coordinate fallback right-click at $wellTopsX,$wellTopsY"
        Click-Point -X $wellTopsX -Y $wellTopsY -RightClick
        Start-Sleep -Milliseconds 600
        Add-DiagnosticScreenshot -FileName "02a_welltops_context_menu.png"
        Write-RunTrace "welltops_menu: coordinate fallback wait export object by name"
        $menuItem = Wait-VisibleByNameOnDesktop -Name "Export object" -Timeout 5
        if ($null -ne $menuItem) {
            $menuRect = Get-ElementRect -Element $menuItem
            Write-RunTrace "welltops_menu: coordinate fallback click named menu item '$($menuItem.Current.Name)' rect $($menuRect.Left),$($menuRect.Top),$($menuRect.Width),$($menuRect.Height)"
            Click-Element -Element $menuItem
            Start-Sleep -Seconds 1
            return
        }
        Write-RunTrace "welltops_menu: coordinate fallback named export object not found"
        if ($ContextMenuKeyboard) {
            Write-RunTrace "welltops_menu: coordinate fallback context menu keyboard selection"
            [System.Windows.Forms.SendKeys]::SendWait("e")
            Start-Sleep -Milliseconds 200
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            Start-Sleep -Seconds 1
            return
        }
        $exportObjectX = [int]($rect.Left + $ExportObjectRelativeX)
        $exportObjectY = [int]($rect.Top + $ExportObjectRelativeY)
        Write-RunTrace "welltops_menu: coordinate fallback click export object at $exportObjectX,$exportObjectY"
        Click-Point -X $exportObjectX -Y $exportObjectY
        Start-Sleep -Seconds 1
        return
    }

    # Reuse the Input tab anchor from the single activation above. Only re-activate
    # (fail-closed) if that first pass never confirmed one - this avoids a second
    # flaky ~11px "Input" OCR pass that, once activated, adds no certainty and was
    # the observed failure point. Either way we require a real, guard-checked anchor
    # before scanning the tree, so the fail-closed contract holds.
    if ($null -eq $inputTabMatch) {
        $inputTabMatch = Activate-ExplorerInputTab -MainWindow $MainWindow -FailClosed
        Write-RunTrace "welltops_menu: re-activated Explorer Input tab by OCR '$($inputTabMatch.text)' rect $($inputTabMatch.left),$($inputTabMatch.top),$($inputTabMatch.width),$($inputTabMatch.height)"
    }

    $wellTopsPattern = "\b(Well|Weil|Weli|Wal)\s*T(o|op|oe|0)"
    $wellTopsMatch = Find-WellTopsInInputTree -MainWindow $MainWindow -Pattern $wellTopsPattern -MaxPages 12 -ExplorerInputTabMatch $inputTabMatch
    if ($null -eq $wellTopsMatch) {
        throw "The Explorer Input tree scan did not find a visible 'Well Tops' row above the Explorer tab strip."
    }

    Write-RunTrace "welltops_menu: OCR target '$($wellTopsMatch.text)' confidence=$($wellTopsMatch.confidence) rect $($wellTopsMatch.left),$($wellTopsMatch.top),$($wellTopsMatch.width),$($wellTopsMatch.height)"
    if ($MainWindow.Current.NativeWindowHandle -ne 0) {
        Focus-Window -Handle ([IntPtr]$MainWindow.Current.NativeWindowHandle) -ExpectedProcessId ([int]$MainWindow.Current.ProcessId)
    }
    # The OCR match box usually starts at the tree glyphs/checkbox left of the label.
    # Petrel opens a different (Studio/folder) context menu when the icon area is
    # clicked, so target the right portion of the box where the label text sits.
    $labelClickMatch = [pscustomobject]@{
        left = $wellTopsMatch.left + [int]($wellTopsMatch.width * 0.7)
        top = $wellTopsMatch.top
        width = [int][math]::Max(4, [int]($wellTopsMatch.width * 0.2))
        height = $wellTopsMatch.height
    }
    Write-RunTrace "welltops_menu: label click box rect $($labelClickMatch.left),$($labelClickMatch.top),$($labelClickMatch.width),$($labelClickMatch.height)"
    $targetPoint = Click-OcrWindowMatch -MainWindow $MainWindow -Match $labelClickMatch
    Start-Sleep -Milliseconds 150
    $targetPoint = Click-OcrWindowMatch -MainWindow $MainWindow -Match $labelClickMatch -RightClick
    Start-Sleep -Milliseconds 350

    # No blind accelerator keys into an unverified menu: identify Export object by
    # UIA name or OCR first, and fail closed with menu screenshots otherwise.
    # Use the popup-scoped finder (fast) instead of a whole-desktop UIA scan.
    $menuItem = Find-ContextMenuItemByName -Name "Export object" -Timeout 2
    if ($null -ne $menuItem) {
        $menuRect = Get-ElementRect -Element $menuItem
        Write-RunTrace "welltops_menu: click UIA menu item '$($menuItem.Current.Name)' rect $($menuRect.Left),$($menuRect.Top),$($menuRect.Width),$($menuRect.Height)"
        Click-Element -Element $menuItem
        Start-Sleep -Milliseconds 750
        return
    }

    Write-RunTrace "welltops_menu: OCR export object menu item"
    $menuMatch = Find-OcrTextOnDesktopNear -Pattern "\bExport\s+object\b" -AnchorX ([int]$targetPoint.x) -AnchorY ([int]$targetPoint.y) -FileName "02b_context_menu_ocr.png" -TopPad 620 -BottomPad 320 -MinConfidence 30 -PageSegmentationMode 11
    if ($null -eq $menuMatch) {
        Write-RunTrace "welltops_menu: OCR export object split fallback"
        $menuMatch = Find-OcrTextOnDesktopNear -Pattern "\bobject\b" -AnchorX ([int]$targetPoint.x) -AnchorY ([int]$targetPoint.y) -FileName "02c_context_menu_object_ocr.png" -TopPad 620 -BottomPad 320 -MinConfidence 30 -PageSegmentationMode 11
    }
    if ($null -ne $menuMatch) {
        if ($menuMatch.width -lt 12 -or $menuMatch.height -lt 6) {
            Write-RunTrace "welltops_menu: ignored tiny OCR menu hit '$($menuMatch.text)' rect $($menuMatch.left),$($menuMatch.top),$($menuMatch.width),$($menuMatch.height)"
        } else {
        Write-RunTrace "welltops_menu: click OCR menu item '$($menuMatch.text)' confidence=$($menuMatch.confidence) rect $($menuMatch.left),$($menuMatch.top),$($menuMatch.width),$($menuMatch.height)"
        Click-OcrDesktopMatch -Match $menuMatch | Out-Null
        Start-Sleep -Milliseconds 750
        return
        }
    }

    $menuBlueMatch = Find-BlueSelectedRowOnDesktopNear -AnchorX ([int]$targetPoint.x) -AnchorY ([int]$targetPoint.y) -FileName "02d_context_menu_selected_row.png"
    if ($null -ne $menuBlueMatch -and $menuBlueMatch.height -ge 12) {
        Write-RunTrace "welltops_menu: click highlighted context-menu row rect $($menuBlueMatch.left),$($menuBlueMatch.top),$($menuBlueMatch.width),$($menuBlueMatch.height)"
        Click-OcrDesktopMatch -Match $menuBlueMatch | Out-Null
        Start-Sleep -Milliseconds 750
        return
    }
    if ($null -ne $menuBlueMatch) {
        Write-RunTrace "welltops_menu: ignored highlighted row below menu-row height rect $($menuBlueMatch.left),$($menuBlueMatch.top),$($menuBlueMatch.width),$($menuBlueMatch.height)"
    }
    # Close the context menu so the desktop is left clean before failing closed.
    [System.Windows.Forms.SendKeys]::SendWait("{ESC}")
    Start-Sleep -Milliseconds 200
    throw "The Well Tops context menu did not expose 'Export object'. Menu screenshots were captured for recalibration; the menu content suggests the click landed on the icon area or a Studio-scoped node."

    if ($ContextMenuKeyboard) {
        Write-RunTrace "welltops_menu: OCR menu target not found; trying keyboard context menu selection"
        [System.Windows.Forms.SendKeys]::SendWait("e")
        Start-Sleep -Milliseconds 200
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Milliseconds 750
        return
    }

    throw "The Well Tops context menu did not expose 'Export object' through UIA or OCR."
}

function Find-TopLevelDialogByRegex {
    param(
        [Parameter(Mandatory = $true)][string]$Pattern,
        [string]$ExcludeTitlePattern = "",
        [int]$ProcessId = 0,
        [int]$Timeout = 45
    )

    $root = Get-AutomationRoot
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $children = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($child in $children) {
            try {
                if ($ProcessId -gt 0 -and [int]$child.Current.ProcessId -ne $ProcessId) {
                    continue
                }
                $name = [string]$child.Current.Name
                $childExcluded = (-not [string]::IsNullOrWhiteSpace($ExcludeTitlePattern) -and $name -match $ExcludeTitlePattern)
                if (-not $childExcluded -and $name -match $Pattern) {
                    return $child
                }
                $windowCondition = New-ControlTypeCondition -ControlType ([System.Windows.Automation.ControlType]::Window)
                $ownedWindows = $child.FindAll([System.Windows.Automation.TreeScope]::Descendants, $windowCondition)
                foreach ($ownedWindow in $ownedWindows) {
                    try {
                        $ownedName = [string]$ownedWindow.Current.Name
                        if (-not [string]::IsNullOrWhiteSpace($ExcludeTitlePattern) -and $ownedName -match $ExcludeTitlePattern) {
                            continue
                        }
                        if ($ownedName -match $Pattern) {
                            return $ownedWindow
                        }
                        $ownedDescendant = Find-FirstByRegex -Root $ownedWindow -Pattern $Pattern
                        if ($null -ne $ownedDescendant) {
                            return $ownedWindow
                        }
                    } catch {
                        continue
                    }
                }
                if ($childExcluded) {
                    continue
                }
                $descendant = Find-FirstByRegex -Root $child -Pattern $Pattern
                if ($null -ne $descendant) {
                    return $child
                }
            } catch {
                continue
            }
        }
        Start-Sleep -Milliseconds 500
    }

    return $null
}

function Select-ExportFormatIfPresent {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Dialog,
        [Parameter(Mandatory = $true)][string]$Pattern
    )

    if ([string]::IsNullOrWhiteSpace($Pattern)) {
        return "not_requested"
    }

    $comboCondition = New-ControlTypeCondition -ControlType ([System.Windows.Automation.ControlType]::ComboBox)
    $combos = @($Dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, $comboCondition))
    foreach ($combo in $combos) {
        try {
            $currentValue = Get-ComboText -Combo $combo
            Write-RunTrace "welltops_save: combo '$($combo.Current.Name)' current '$currentValue'"
            if ($currentValue -match $Pattern) {
                return "already_selected:$currentValue"
            }
        } catch {
            continue
        }
    }

    foreach ($combo in $combos) {
        try {
            Expand-Element -Element $combo
            Start-Sleep -Milliseconds 500
            $candidate = Find-VisibleSelectableByRegexOnDesktop -Pattern $Pattern
            if ($null -ne $candidate) {
                Select-Element -Element $candidate
                Start-Sleep -Milliseconds 500
                $selectedValue = Get-ComboText -Combo $combo
                Write-RunTrace "welltops_save: combo after select '$selectedValue'"
                if ($selectedValue -match $Pattern) {
                    return "selected_combo_format:$selectedValue"
                }
                return "selection_unverified:$selectedValue"
            }
        } catch {
            continue
        }
    }

    return "not_found"
}

function Get-ElementText {
    param([Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Element)

    $values = New-Object System.Collections.Generic.List[string]
    try {
        $name = [string]$Element.Current.Name
        if (-not [string]::IsNullOrWhiteSpace($name)) {
            [void]$values.Add($name)
        }
    } catch {}

    $valuePattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$valuePattern)) {
        try {
            $value = [string]$valuePattern.Current.Value
            if (-not [string]::IsNullOrWhiteSpace($value)) {
                [void]$values.Add($value)
            }
        } catch {}
    }

    return (($values | Select-Object -Unique) -join " ").Trim()
}

function Get-ComboText {
    param([Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Combo)

    $values = New-Object System.Collections.Generic.List[string]
    $ownText = Get-ElementText -Element $Combo
    if (-not [string]::IsNullOrWhiteSpace($ownText)) {
        [void]$values.Add($ownText)
    }

    $selectionPattern = $null
    if ($Combo.TryGetCurrentPattern([System.Windows.Automation.SelectionPattern]::Pattern, [ref]$selectionPattern)) {
        try {
            foreach ($selection in @($selectionPattern.Current.GetSelection())) {
                $selectionText = Get-ElementText -Element $selection
                if (-not [string]::IsNullOrWhiteSpace($selectionText)) {
                    [void]$values.Add($selectionText)
                }
            }
        } catch {}
    }

    return (($values | Select-Object -Unique) -join " ").Trim()
}

function Find-VisibleSelectableByRegexOnDesktop {
    param([Parameter(Mandatory = $true)][string]$Pattern)

    $root = Get-AutomationRoot
    $matches = @($root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition))
    foreach ($match in $matches) {
        try {
            $name = [string]$match.Current.Name
            if ([string]::IsNullOrWhiteSpace($name) -or $name -notmatch $Pattern) {
                continue
            }
            $rect = Get-ElementRect -Element $match
            if (-not (Test-VisibleRect -Rect $rect)) {
                continue
            }
            $controlType = $match.Current.ControlType
            $selectPattern = $null
            $invokePattern = $null
            if ($match.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$selectPattern) -or
                $match.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokePattern) -or
                $controlType -eq [System.Windows.Automation.ControlType]::ListItem -or
                $controlType -eq [System.Windows.Automation.ControlType]::MenuItem) {
                return $match
            }
        } catch {
            continue
        }
    }

    return $null
}

function Set-SaveDialogFilePath {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$Dialog,
        [Parameter(Mandatory = $true)][string]$OutputFile
    )

    $editCondition = New-ControlTypeCondition -ControlType ([System.Windows.Automation.ControlType]::Edit)
    $edits = @($Dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCondition))
    $targetEdit = $null
    foreach ($edit in $edits) {
        try {
            $name = [string]$edit.Current.Name
            if ($name -match "File name|Name|File") {
                $targetEdit = $edit
                break
            }
        } catch {
            continue
        }
    }
    if ($null -eq $targetEdit -and $edits.Count -gt 0) {
        $targetEdit = $edits[0]
    }
    if ($null -eq $targetEdit) {
        throw "Could not find an editable filename field in the export dialog."
    }

    Set-ValueOrType -Element $targetEdit -Value $OutputFile
}

function Submit-WellTopsSaveDialogByCoordinates {
    param(
        [Parameter(Mandatory = $true)][string]$OutputFile,
        [Parameter(Mandatory = $true)][System.Windows.Automation.AutomationElement]$MainWindow
    )

    $rect = Get-ElementRect -Element $MainWindow
    $fileNameX = [int]($rect.Left + 334)
    $fileNameY = [int]($rect.Top + 370)
    Add-DiagnosticScreenshot -FileName "03_welltops_export_dialog_before_path.png"
    Write-RunTrace "welltops_save: coordinate fallback file field at $fileNameX,$fileNameY"
    Click-Point -X $fileNameX -Y $fileNameY
    Start-Sleep -Milliseconds 200
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    Start-Sleep -Milliseconds 80
    Write-RunTrace "welltops_save: coordinate fallback type output $OutputFile"
    [System.Windows.Forms.SendKeys]::SendWait($OutputFile)
    Start-Sleep -Milliseconds 150
    Add-DiagnosticScreenshot -FileName "04_welltops_export_dialog_after_path.png"
    # A file name typed into a Windows save dialog is committed by its default
    # button (Save) on Enter. Pressing Enter right after the paste is faster and
    # more reliable than a fixed-coordinate Save click, and it is what a human does.
    Write-RunTrace "welltops_save: coordinate fallback commit filename with Enter"
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")

    # A confirmation-style CRS dialog ("OK for all" defaulted) follows the save.
    # Find-TopLevelWindowByTitleRegex polls internally and returns the moment the
    # dialog appears, so a small timeout waits only as long as needed, then Enter
    # commits it immediately instead of a fixed-coordinate click plus a 1.2s sleep.
    $crsDialog = Find-TopLevelWindowByTitleRegex -Pattern "Coordinate reference system selection|OK for all" -Timeout 4
    $crsShown = ($null -ne $crsDialog)
    if ($crsShown) {
        Write-RunTrace "welltops_save: coordinate fallback commit CRS with Enter"
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Milliseconds 200
    } else {
        Write-RunTrace "welltops_save: coordinate fallback CRS dialog not observed within wait window"
    }
    Add-DiagnosticScreenshot -FileName "06_welltops_after_crs_click.png"

    return [pscustomobject]@{
        dialog_title = "Export as"
        format_status = "coordinate_existing_petrel_well_tops_ascii"
        overwrite_status = "not_checked_unique_filename"
        crs_status = if ($crsShown) { "coordinate_enter_commit" } else { "crs_not_shown" }
    }
}

function Confirm-OverwriteIfShown {
    param([int]$Timeout = 10)

    $dialog = Find-TopLevelWindowByTitleRegex -Pattern "already exists|replace|overwrite|confirm|Confirm|Save As" -Timeout $Timeout
    if ($null -eq $dialog) {
        return "not_shown"
    }

    foreach ($name in @("Yes", "&Yes", "Replace", "OK")) {
        $button = Find-FirstByName -Root $dialog -Name $name
        if ($null -ne $button) {
            Invoke-Element -Element $button
            return "confirmed"
        }
    }

    return "shown_unhandled:$([string]$dialog.Current.Name)"
}

function Confirm-WellTopsCrsIfShown {
    param([int]$Timeout = 12)

    $dialog = Find-TopLevelWindowByTitleRegex -Pattern "Coordinate reference system selection" -Timeout $Timeout
    if ($null -eq $dialog) {
        $dialog = Wait-TopLevelContainingText -Pattern "Coordinate reference system selection|OK for all" -Timeout 1
    }
    if ($null -eq $dialog) {
        return "not_shown"
    }

    foreach ($name in @("OK for all", "OK", "&OK")) {
        $button = Find-FirstByName -Root $dialog -Name $name
        if ($null -ne $button) {
            Invoke-Element -Element $button
            return "confirmed_$name"
        }
    }

    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Milliseconds 500
    return "sent_enter"
}

function Dismiss-StaleExportDialogIfShown {
    param(
        [int]$ProcessId = 0,
        [int]$Timeout = 1
    )

    # A leftover Export/Save dialog is always a top-level window, so the fast
    # top-level scan finds it. The former deep whole-tree scan cost ~15s on the
    # common case where no stale dialog exists.
    $dialog = Find-TopLevelWindowByTitleRegex -Pattern "^Export as$|^Save As$|^Save as$" -ProcessId $ProcessId -Timeout $Timeout
    if ($null -eq $dialog) {
        return "not_shown"
    }

    $windowPattern = $null
    if ($dialog.TryGetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern, [ref]$windowPattern)) {
        $windowPattern.Close()
        Start-Sleep -Milliseconds 700
        return "closed_WindowPattern"
    }

    foreach ($name in @("Cancel", "&Cancel", "Close")) {
        $button = Find-FirstByName -Root $dialog -Name $name
        if ($null -ne $button) {
            Invoke-Element -Element $button
            Start-Sleep -Milliseconds 500
            return "cancelled_$name"
        }
    }

    [System.Windows.Forms.SendKeys]::SendWait("%{F4}")
    Start-Sleep -Milliseconds 500
    return "sent_alt_f4"
}

function Dismiss-StudioLoginIfShown {
    param([int]$Timeout = 2)

    $dialog = Find-TopLevelWindowByTitleRegex -Pattern "Studio connection|Database authentication|Repository|Login" -Timeout $Timeout
    if ($null -eq $dialog) {
        return "not_shown"
    }

    foreach ($name in @("Cancel", "&Cancel", "Close")) {
        $button = Find-FirstByName -Root $dialog -Name $name
        if ($null -ne $button) {
            Invoke-Element -Element $button
            Start-Sleep -Milliseconds 500
            return "cancelled_$name"
        }
    }

    [System.Windows.Forms.SendKeys]::SendWait("{ESC}")
    Start-Sleep -Milliseconds 500
    return "sent_esc"
}

function Dismiss-ProjectDataTableIfShown {
    param(
        [int]$ProcessId = 0,
        [int]$Timeout = 1
    )

    $dialog = Find-TopLevelWindowByTitleRegex -Pattern "^Project data table:" -ProcessId $ProcessId -Timeout $Timeout
    if ($null -eq $dialog) {
        return "not_shown"
    }

    $title = [string]$dialog.Current.Name
    Write-RunTrace "project data table close attempt '$title'"
    $windowPattern = $null
    if ($dialog.TryGetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern, [ref]$windowPattern)) {
        $windowPattern.Close()
        Start-Sleep -Milliseconds 700
        return "closed_WindowPattern"
    }

    try {
        $handle = [IntPtr]$dialog.Current.NativeWindowHandle
        if ($handle -ne [IntPtr]::Zero) {
            Focus-Window -Handle $handle -ExpectedProcessId ([int]$dialog.Current.ProcessId)
            [System.Windows.Forms.SendKeys]::SendWait("%{F4}")
            Start-Sleep -Milliseconds 700
            return "closed_AltF4"
        }
    } catch {
        Write-RunTrace "project data table close fallback failed $($_.Exception.Message)"
    }

    return "close_unavailable"
}

function Dismiss-OfmConnectorIfShown {
    param(
        [int]$ProcessId = 0,
        [int]$Timeout = 1
    )

    $dialog = Find-TopLevelWindowByTitleRegex -Pattern "OFM Data Connector" -ProcessId $ProcessId -Timeout $Timeout
    if ($null -eq $dialog) {
        return "not_shown"
    }

    $title = [string]$dialog.Current.Name
    Write-RunTrace "ofm connector close attempt '$title'"
    $windowPattern = $null
    if ($dialog.TryGetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern, [ref]$windowPattern)) {
        $windowPattern.Close()
        Start-Sleep -Milliseconds 700
        return "closed_WindowPattern"
    }

    try {
        $handle = [IntPtr]$dialog.Current.NativeWindowHandle
        if ($handle -ne [IntPtr]::Zero) {
            Focus-Window -Handle $handle -ExpectedProcessId ([int]$dialog.Current.ProcessId)
            [System.Windows.Forms.SendKeys]::SendWait("%{F4}")
            Start-Sleep -Milliseconds 700
            return "closed_AltF4"
        }
    } catch {
        Write-RunTrace "ofm connector close fallback failed $($_.Exception.Message)"
    }

    return "close_unavailable"
}

function Submit-WellTopsSaveDialog {
    param(
        [Parameter(Mandatory = $true)][string]$OutputFile,
        [Parameter(Mandatory = $true)][string]$FormatPattern,
        [int]$PetrelProcessId = 0,
        [int]$Timeout = 60
    )

    Write-RunTrace "welltops_save: wait dialog"
    # Cheap title probe first (2s): if the dialog exposes a title it is found instantly.
    # Petrel's Export as dialog has an EMPTY title, so the real match comes from the
    # content-based top-level scan below. (A structure-based finder keyed on a "File name"
    # edit was tried and reverted: the field is a ComboBox with the label, so the inner
    # Edit is unnamed and the match timed out, adding ~18s instead of saving time.)
    $dialog = Find-TopLevelWindowByTitleRegex -Pattern "^Export as$|^Save As$" -ProcessId $PetrelProcessId -Timeout 2
    if ($null -eq $dialog) {
        $dialog = Find-TopLevelDialogByRegex -Pattern "Save As|Export|file name|Save as type|Format" -ExcludeTitlePattern "Petrel E.?P Software Platform" -ProcessId $PetrelProcessId -Timeout $Timeout
    }
    if ($null -eq $dialog) {
        throw "No export/save dialog appeared for Well Tops."
    }

    Write-RunTrace "welltops_save: dialog '$($dialog.Current.Name)'"
    $formatStatus = Select-ExportFormatIfPresent -Dialog $dialog -Pattern $FormatPattern
    Write-RunTrace "welltops_save: format status $formatStatus"
    if ($formatStatus -match "^not_found|^selection_unverified|OFM master table") {
        throw "The export dialog did not verify the requested Well Tops ASCII format. Status: $formatStatus"
    }
    Set-SaveDialogFilePath -Dialog $dialog -OutputFile $OutputFile
    Write-RunTrace "welltops_save: set output $OutputFile"

    foreach ($name in @("Save", "&Save", "OK", "Export")) {
        $button = Find-FirstByName -Root $dialog -Name $name
        if ($null -ne $button) {
            Write-RunTrace "welltops_save: invoke button $name"
            Invoke-Element -Element $button
            $overwriteStatus = Confirm-OverwriteIfShown -Timeout 2
            Write-RunTrace "welltops_save: overwrite status $overwriteStatus"
            $crsStatus = Confirm-WellTopsCrsIfShown -Timeout 12
            Write-RunTrace "welltops_save: crs status $crsStatus"
            return [pscustomobject]@{ dialog_title = $dialog.Current.Name; format_status = $formatStatus; overwrite_status = $overwriteStatus; crs_status = $crsStatus }
        }
    }

    Write-RunTrace "welltops_save: send enter"
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    $overwrite = Confirm-OverwriteIfShown -Timeout 2
    Write-RunTrace "welltops_save: overwrite status $overwrite"
    $crs = Confirm-WellTopsCrsIfShown -Timeout 12
    Write-RunTrace "welltops_save: crs status $crs"
    return [pscustomobject]@{ dialog_title = $dialog.Current.Name; format_status = $formatStatus; overwrite_status = $overwrite; crs_status = $crs }
}

function Wait-ExportedLasFiles {
    param(
        [Parameter(Mandatory = $true)][string]$TargetFolder,
        [int]$Timeout = 180
    )

    $deadline = (Get-Date).AddSeconds($Timeout)
    $lastCount = -1
    $stableTicks = 0

    while ((Get-Date) -lt $deadline) {
        $files = @(Get-ChildItem -LiteralPath $TargetFolder -Recurse -File -Filter "*.las" -ErrorAction SilentlyContinue)
        if ($files.Count -gt 0 -and $files.Count -eq $lastCount) {
            $stableTicks += 1
        } else {
            $stableTicks = 0
        }

        if ($files.Count -gt 0 -and $stableTicks -ge 3) {
            return $files
        }

        $lastCount = $files.Count
        Start-Sleep -Seconds 2
    }

    return @(Get-ChildItem -LiteralPath $TargetFolder -Recurse -File -Filter "*.las" -ErrorAction SilentlyContinue)
}

function Wait-ExportedFiles {
    param(
        [Parameter(Mandatory = $true)][string]$TargetFolder,
        [Parameter(Mandatory = $true)][string]$Filter,
        [int]$Timeout = 180,
        [int]$StableTicksRequired = 3,
        [int]$PollSeconds = 2
    )

    $deadline = (Get-Date).AddSeconds($Timeout)
    $lastSignature = ""
    $stableTicks = 0

    while ((Get-Date) -lt $deadline) {
        $files = @(Get-ChildItem -LiteralPath $TargetFolder -Recurse -File -Filter $Filter -ErrorAction SilentlyContinue)
        $signature = ($files | Sort-Object FullName | ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }) -join ";"
        if ($files.Count -gt 0 -and $signature -eq $lastSignature) {
            $stableTicks += 1
        } else {
            $stableTicks = 0
        }

        if ($files.Count -gt 0 -and $stableTicks -ge $StableTicksRequired) {
            return $files
        }

        $lastSignature = $signature
        Start-Sleep -Seconds $PollSeconds
    }

    return @(Get-ChildItem -LiteralPath $TargetFolder -Recurse -File -Filter $Filter -ErrorAction SilentlyContinue)
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

$ProjectFile = (Resolve-Path -LiteralPath $ProjectFile).Path
$ProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path

if ([string]::IsNullOrWhiteSpace($InventoryPackage)) {
    $InventoryPackage = Get-LatestPackage -Root $InventoryRoot -Pattern "*_inventory_*"
}
if ([string]::IsNullOrWhiteSpace($ExportPackage)) {
    $ExportPackage = Get-LatestPackage -Root $ExportRoot -Pattern "*_export_*"
}
if ([string]::IsNullOrWhiteSpace($InventoryPackage)) {
    throw "Inventory package was not supplied and no latest inventory package was found."
}
if ([string]::IsNullOrWhiteSpace($ExportPackage)) {
    throw "Export package was not supplied and no latest export package was found."
}

$InventoryPackage = (Resolve-Path -LiteralPath $InventoryPackage).Path
$ExportPackage = (Resolve-Path -LiteralPath $ExportPackage).Path

$runDir = Join-Path $ExportPackage "07_workflows_reports\automation_runs"
$targetRoot = Join-Path $ExportPackage $TargetSubfolder
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

if (-not $AllowExistingTarget) {
    $existing = @(Get-ChildItem -LiteralPath $targetRoot -Force -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
        $targetRoot = Join-Path $targetRoot "ui_export_$stamp"
        New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
    }
}

$screenDir = Join-Path $runDir "ui_well_log_export_$stamp"
New-Item -ItemType Directory -Force -Path $screenDir | Out-Null

$statusPath = Join-Path $runDir "petrel_ui_well_log_export_$stamp.json"
$tracePath = Join-Path $runDir "petrel_ui_$($ExportKind.ToLowerInvariant())_export_$stamp.trace.log"
$script:PetrelUiTracePath = $tracePath
Write-RunTrace "start export_kind=$ExportKind target_root=$targetRoot"
$screenshots = New-Object System.Collections.Generic.List[string]
$drive = $DriveLetter.TrimEnd(":").ToUpperInvariant()
if ($drive.Length -ne 1) {
    throw "DriveLetter must be a single drive letter, for example P."
}
$driveSpec = "$drive`:"

Initialize-UiAutomation
Write-RunTrace "ui automation initialized"

$petrelProcess = Get-PetrelProcess -ProcessId $PetrelProcessId
if ($null -eq $petrelProcess) {
    Write-RunTrace "petrel process not found; launching project"
    $launcher = Join-Path $scriptDir "invoke_petrel_export_pilot.ps1"
    $launcherArgs = @{
        Mode = "OpenProject"
        ProjectName = $ProjectName
        ProjectFile = $ProjectFile
        ProjectPath = $ProjectPath
        InventoryPackage = $InventoryPackage
        ExportPackage = $ExportPackage
        LicensePackage = $(if ([string]::IsNullOrWhiteSpace($LicensePackage)) { $LicenseProfile } else { $LicensePackage })
        PetrelOptionStyle = $PetrelOptionStyle
    }
    if ($OpenProjectWritable) {
        $launcherArgs.OpenProjectWritable = $true
    }
    & $launcher @launcherArgs | Out-Null
    $petrelProcess = Wait-PetrelProcess -ProcessId 0 -Timeout 120
    Write-RunTrace "petrel launched pid=$($petrelProcess.Id) title='$($petrelProcess.MainWindowTitle)'"
} else {
    Write-RunTrace "petrel process found pid=$($petrelProcess.Id) title='$($petrelProcess.MainWindowTitle)'"
}

$licenseStatus = Select-LicenseProfileIfShown -ProfileName $LicenseProfile -Timeout $LicenseDialogTimeoutSeconds
Write-RunTrace "license status $licenseStatus"
$petrelProcess = Wait-PetrelReadyWindow -ProcessId $petrelProcess.Id -Timeout 180
Write-RunTrace "petrel ready pid=$($petrelProcess.Id) title='$($petrelProcess.MainWindowTitle)'"
Focus-Window -Handle $petrelProcess.MainWindowHandle -ExpectedProcessId $petrelProcess.Id
$projectDataTableStatus = Dismiss-ProjectDataTableIfShown -ProcessId $petrelProcess.Id -Timeout 1
Write-RunTrace "project data table status $projectDataTableStatus"
$ofmConnectorStatus = Dismiss-OfmConnectorIfShown -ProcessId $petrelProcess.Id -Timeout 1
Write-RunTrace "ofm connector status $ofmConnectorStatus"
$studioLoginStatus = Dismiss-StudioLoginIfShown -Timeout 2
Write-RunTrace "studio login status $studioLoginStatus"
$staleExportDialogStatus = Dismiss-StaleExportDialogIfShown -ProcessId $petrelProcess.Id -Timeout 1
Write-RunTrace "stale export dialog status $staleExportDialogStatus"
Focus-Window -Handle $petrelProcess.MainWindowHandle -ExpectedProcessId $petrelProcess.Id
$mainWindow = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$petrelProcess.MainWindowHandle)
$normalizeStatus = Normalize-PetrelWindow -MainWindow $mainWindow
Write-RunTrace "normalize window status $normalizeStatus"

$screenshotPath = Join-Path $screenDir "01_petrel_ready.png"
Write-RunTrace "screenshot 01 begin"
Save-Screenshot -Path $screenshotPath -Element $mainWindow
Write-RunTrace "screenshot 01 end"
$screenshots.Add($screenshotPath)

$cleanupResult = Invoke-SubstCommand -Arguments @($driveSpec, "/D") -AllowFailure
if ($cleanupResult.exit_code -ne 0) {
    Write-RunTrace "pre-map cleanup for $driveSpec returned exit_code=$($cleanupResult.exit_code)"
}
Invoke-SubstCommand -Arguments @($driveSpec, $targetRoot) | Out-Null
if (-not (Test-Path -LiteralPath "$driveSpec\")) {
    throw "Mapped drive was not visible after subst: $driveSpec"
}
Write-RunTrace "mapped drive $driveSpec to $targetRoot"

$exportedFiles = @()
$dialogStatus = $null
$outputFileOnDrive = ""
$waitFilter = "*.$Extension"
try {
    if ($ExportKind -eq "WellLogs") {
        Write-RunTrace "welllogs export begin"
        Invoke-WellLogsExportMenu -MainWindow $mainWindow
        $screenshotPath = Join-Path $screenDir "02_after_export_menu.png"
        Save-Screenshot -Path $screenshotPath
        $screenshots.Add($screenshotPath)

        Select-BrowseFolderDrive -DriveLetter $drive -Timeout 60
        $screenshotPath = Join-Path $screenDir "03_after_folder_selection.png"
        Save-Screenshot -Path $screenshotPath
        $screenshots.Add($screenshotPath)

        Confirm-ExtensionDialog -Extension $Extension -Timeout 45
        $exportedFiles = @(Wait-ExportedLasFiles -TargetFolder $targetRoot -Timeout $TimeoutSeconds)
        Write-RunTrace "welllogs wait complete count=$($exportedFiles.Count)"
    } elseif ($ExportKind -eq "WellTops") {
        Write-RunTrace "welltops export begin"
        if ([string]::IsNullOrWhiteSpace($OutputFileName)) {
            $OutputFileName = "well_tops_petrel_ascii_$stamp.$Extension"
        }
        if ([IO.Path]::GetExtension($OutputFileName) -eq "") {
            $OutputFileName = "$OutputFileName.$Extension"
        }
        $outputFileOnDrive = Join-Path "$driveSpec\" $OutputFileName
        $waitFilter = Split-Path -Leaf $OutputFileName
        Write-RunTrace "welltops output_file=$outputFileOnDrive wait_filter=$waitFilter"

        Invoke-WellTopsExportMenu -MainWindow $mainWindow -CoordinateFallback:$CoordinateFallback
        Write-RunTrace "welltops menu complete"
        $screenshotPath = Join-Path $screenDir "02_after_export_menu.png"
        Write-RunTrace "screenshot 02 begin"
        Save-Screenshot -Path $screenshotPath
        Write-RunTrace "screenshot 02 end"
        $screenshots.Add($screenshotPath)

        if ($CoordinateFallback) {
            try {
                $dialogStatus = Submit-WellTopsSaveDialog -OutputFile $outputFileOnDrive -FormatPattern $FormatPattern -PetrelProcessId $petrelProcess.Id -Timeout 30
            } catch {
                Write-RunTrace "welltops_save: UIA submit failed in coordinate mode; falling back to coordinate dialog submit: $($_.Exception.Message)"
                $dialogStatus = Submit-WellTopsSaveDialogByCoordinates -OutputFile $outputFileOnDrive -MainWindow $mainWindow
            }
        } else {
            $dialogStatus = Submit-WellTopsSaveDialog -OutputFile $outputFileOnDrive -FormatPattern $FormatPattern -PetrelProcessId $petrelProcess.Id -Timeout 90
        }
        Write-RunTrace "welltops save complete"
        $screenshotPath = Join-Path $screenDir "03_after_save_dialog.png"
        Write-RunTrace "screenshot 03 begin"
        Save-Screenshot -Path $screenshotPath
        Write-RunTrace "screenshot 03 end"
        $screenshots.Add($screenshotPath)

        $exportedFiles = @(Wait-ExportedFiles -TargetFolder $targetRoot -Filter $waitFilter -Timeout $TimeoutSeconds -StableTicksRequired $StableFileTicks -PollSeconds $FilePollSeconds)
        Write-RunTrace "welltops wait complete count=$($exportedFiles.Count)"
    } else {
        throw "Unsupported export kind: $ExportKind"
    }
} finally {
    if (-not $KeepDriveMapping) {
        $cleanupResult = Invoke-SubstCommand -Arguments @($driveSpec, "/D") -AllowFailure
        if ($cleanupResult.exit_code -eq 0) {
            Write-RunTrace "removed drive mapping $driveSpec"
        } else {
            Write-RunTrace "cleanup warning: failed to remove drive mapping $driveSpec exit_code=$($cleanupResult.exit_code)"
        }
    }
}

$registerStatus = "skipped"
$registerReport = ""
if (-not $NoRegister) {
    Write-RunTrace "registration begin"
    $registrar = Join-Path $scriptDir "register_petrel_file_exports.ps1"
    $registerOutput = & $registrar `
        -ExportPackage $ExportPackage `
        -ProjectName $ProjectName `
        -PetrelVersion $PetrelVersion `
        -InventoryPackage $InventoryPackage
    $registerStatus = (($registerOutput | Select-Object -First 1) -replace '^File export registration:\s*', '')
    $registerReportLine = @($registerOutput | Where-Object { $_ -match '^Report:' } | Select-Object -First 1)
    if ($registerReportLine.Count -gt 0) {
        $registerReport = ($registerReportLine[0] -replace '^Report:\s*', '')
    }
    Write-RunTrace "registration status $registerStatus"
}

$validationStatus = "skipped"
$validationReport = ""
if (-not $NoValidate) {
    Write-RunTrace "validation begin"
    $validator = Join-Path $scriptDir "validate_export_package.ps1"
    $validationOutput = & $validator -ExportPackage $ExportPackage -UpdateManifest -WriteChecksums
    $validationStatus = (($validationOutput | Select-Object -First 1) -replace '^Validation status:\s*', '')
    $validationReportLine = @($validationOutput | Where-Object { $_ -match '^Report:' } | Select-Object -First 1)
    if ($validationReportLine.Count -gt 0) {
        $validationReport = ($validationReportLine[0] -replace '^Report:\s*', '')
    }
    Write-RunTrace "validation status $validationStatus"
}

$exportedBytes = 0
foreach ($file in $exportedFiles) {
    $exportedBytes += $file.Length
}

$status = [ordered]@{
    run_id = "petrel_ui_$($ExportKind.ToLowerInvariant())_export_$stamp"
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    project_name = $ProjectName
    project_file = $ProjectFile
    export_kind = $ExportKind
    inventory_package = $InventoryPackage
    export_package = $ExportPackage
    petrel_process_id = $petrelProcess.Id
    petrel_window_title = $petrelProcess.MainWindowTitle
    license_status = $licenseStatus
    target_folder = $targetRoot
    temporary_drive = $driveSpec
    extension = $Extension
    output_file_name = $OutputFileName
    output_file_on_drive = $outputFileOnDrive
    wait_filter = $waitFilter
    dialog_status = $dialogStatus
    exported_file_count = $exportedFiles.Count
    exported_bytes = $exportedBytes
    exported_las_count = @($exportedFiles | Where-Object { $_.Extension -ieq ".las" }).Count
    exported_las_bytes = if ($ExportKind -eq "WellLogs") { $exportedBytes } else { 0 }
    register_status = $registerStatus
    register_report = $registerReport
    validation_status = $validationStatus
    validation_report = $validationReport
    screenshots = @($screenshots)
    files = @($exportedFiles | ForEach-Object { $_.FullName })
}

$status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statusPath -Encoding UTF8
Write-RunTrace "status written $statusPath"

Write-Output "UI $ExportKind export: completed"
Write-Output "Petrel PID: $($petrelProcess.Id)"
Write-Output "Target folder: $targetRoot"
Write-Output "Exported files: $($exportedFiles.Count)"
Write-Output "Exported bytes: $exportedBytes"
Write-Output "File export registration: $registerStatus"
Write-Output "Validation: $validationStatus"
Write-Output "Status file: $statusPath"

if ($exportedFiles.Count -eq 0) {
    throw "UI $ExportKind export produced zero files in $targetRoot."
}
if ($validationStatus -eq "failed") {
    throw "UI $ExportKind export validation failed. Report: $validationReport"
}
