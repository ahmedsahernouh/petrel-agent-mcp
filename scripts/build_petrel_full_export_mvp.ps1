param(
    [string]$ProjectName = "Petrel2010 demo project",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$ExportPackage = "D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609",

    [string]$InventoryPackage = "D:\Computer\Code\Petrel_project\build\inventory_pilots\Petrel2010_demo_project_inventory_20260701_055128",

    [string]$WorkflowName = "ExportPiloX",

    [string]$HelpTopicCsv = "D:\Computer\Code\Petrel_project\build\reports\petrel2018_help_export_topics.csv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([string]$PathValue)

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return (Join-Path (Get-Location).Path $PathValue)
}

function Get-EvidenceTopics {
    param(
        [object[]]$Topics,
        [string[]]$Patterns,
        [int]$Limit = 5
    )

    $matches = @()
    foreach ($pattern in $Patterns) {
        $matches += @(
            $Topics |
                Where-Object {
                    $_.topic_title -match $pattern -or
                    $_.category -match $pattern -or
                    $_.formats -match $pattern -or
                    $_.abstract -match $pattern -or
                    $_.subject -match $pattern
                }
        )
    }

    return @(
        $matches |
            Sort-Object @{ Expression = { [int]$_.relevance_score }; Descending = $true }, topic_title -Unique |
            Select-Object -First $Limit
    )
}

function Join-Values {
    param([object[]]$Values)

    return (@($Values) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | Select-Object -Unique) -join "; "
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$exportRoot = (Resolve-Path -LiteralPath (Resolve-RepoPath $ExportPackage)).Path
$inventoryRoot = ""
if (-not [string]::IsNullOrWhiteSpace($InventoryPackage) -and (Test-Path -LiteralPath $InventoryPackage -PathType Container)) {
    $inventoryRoot = (Resolve-Path -LiteralPath $InventoryPackage).Path
}
$helpCsvPath = (Resolve-Path -LiteralPath (Resolve-RepoPath $HelpTopicCsv)).Path
$topics = @(Import-Csv -LiteralPath $helpCsvPath)

$manifestDir = Join-Path $exportRoot "00_manifest"
$mvpDir = Join-Path $exportRoot "07_workflows_reports\mvp_full_project_export"
New-Item -ItemType Directory -Force -Path $manifestDir, $mvpDir | Out-Null

$objectClasses = @(
    [pscustomobject]@{ ObjectClass = "project_metadata"; PetrelContent = "Project CRS, units, Petrel version, project summary"; Category = "metadata"; Preferred = "JSON"; Secondary = "CSV"; TargetFolder = "01_project_metadata"; Metadata = "project_name, petrel_version, CRS, xy_units, depth_units, time_units, velocity_units"; Patterns = @("Project coordinates|Coordinate Reference System|units|Export data"); Manual = "yes"; BatchCli = "wrapper_ready"; Workflow = "external_bridge_ready"; Api = "unknown"; Status = "mvp_external_ready"; Validation = "JSON exists, required metadata fields present"; Risk = "low"; Notes = "Captured outside Petrel for now; must be confirmed from Project settings." },
    [pscustomobject]@{ ObjectClass = "well_headers"; PetrelContent = "Well headers and coordinate table"; Category = "wells"; Preferred = "CSV"; Secondary = "ASCII"; TargetFolder = "02_wells\well_headers"; Metadata = "well name, X, Y, datum, CRS, xy_units, KB/DF, status"; Patterns = @("^Export well data$","Export coordinates to MS Excel","Wells, exporting coordinates"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "CSV/XLSX exists, nonzero rows, coordinate metadata present"; Risk = "low"; Notes = "First real export target." },
    [pscustomobject]@{ ObjectClass = "well_trajectories"; PetrelContent = "Well trajectory/deviation coordinates"; Category = "wells"; Preferred = "CSV"; Secondary = "ASCII"; TargetFolder = "02_wells\well_trajectories"; Metadata = "well name, MD, inclination, azimuth, TVD, units"; Patterns = @("Export well deviation coordinates","^Export well data$"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "CSV/ASCII exists, MD/TVD columns present"; Risk = "low"; Notes = "Useful for validating well geometry." },
    [pscustomobject]@{ ObjectClass = "well_logs"; PetrelContent = "Well logs by well/log set"; Category = "wells"; Preferred = "LAS"; Secondary = "CSV"; TargetFolder = "02_wells\well_logs_las"; Metadata = "well name, log names, curve units, depth units, null value"; Patterns = @("Export well log data as LAS","^Export well data$","LAS"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "LAS header sections, curve count, nonzero file"; Risk = "low"; Notes = "Known local help says LAS 2.0 one well at a time." },
    [pscustomobject]@{ ObjectClass = "well_tops"; PetrelContent = "Well tops/markers"; Category = "wells"; Preferred = "CSV"; Secondary = "ASCII"; TargetFolder = "02_wells\well_tops"; Metadata = "well name, top name, MD/TVD/TWT/depth, z_units"; Patterns = @("^Export well data$","well tops|markers|Wells"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "CSV/ASCII exists, top/depth columns present"; Risk = "low"; Notes = "Grouped with well data export." },
    [pscustomobject]@{ ObjectClass = "checkshots_vsp"; PetrelContent = "Checkshot and VSP time-depth data"; Category = "wells"; Preferred = "CSV"; Secondary = "ASCII"; TargetFolder = "02_wells\checkshots_vsp"; Metadata = "well name, time, depth, datum, units"; Patterns = @("Export of checkshot data","checkshot|VSP"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "CSV/ASCII exists, time-depth columns present"; Risk = "medium"; Notes = "Datum handling must be recorded." },
    [pscustomobject]@{ ObjectClass = "data_tables"; PetrelContent = "Project data tables and QA reports"; Category = "tables_and_spreadsheets"; Preferred = "XLSX"; Secondary = "CSV"; TargetFolder = "07_workflows_reports\exported_reports"; Metadata = "table name, column units, source object path"; Patterns = @("Export data displayed in a data table","CSV file","Excel"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "candidate_via_output_sheet"; Api = "unknown"; Status = "probe_validated"; Validation = "file exists, nonzero rows, expected columns"; Risk = "low"; Notes = "Current workflow probe is already a table-style export." },
    [pscustomobject]@{ ObjectClass = "seismic_3d_2d"; PetrelContent = "3D cubes, 2D lines, intersections, composite lines"; Category = "seismic"; Preferred = "SEG-Y"; Secondary = "ZGY"; TargetFolder = "03_seismic\segy"; Metadata = "survey name, domain, sample rate, trace count, byte mapping, CRS, units"; Patterns = @("Export seismic data in SEG-Y format","Export a seismic cube in ZGY format","SEG-Y|ZGY"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "ocean_candidate"; Status = "planned_not_exported"; Validation = "file exists, sidecar metadata present, independent header probe later"; Risk = "high"; Notes = "Delay until wells/logs/surface pass." },
    [pscustomobject]@{ ObjectClass = "prestack_seismic"; PetrelContent = "Prestack seismic datasets"; Category = "seismic"; Preferred = "SEG-Y"; Secondary = "SEG-Y Rev0/Rev1"; TargetFolder = "03_seismic\segy"; Metadata = "dataset name, gather type, domain, sample rate, byte mapping"; Patterns = @("Export prestack data in SEG-Y format","prestack"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "ocean_candidate"; Status = "planned_not_exported"; Validation = "file exists, sidecar metadata present"; Risk = "high"; Notes = "Larger data and options; not first pilot." },
    [pscustomobject]@{ ObjectClass = "seismic_navigation"; PetrelContent = "Seismic line/navigation metadata"; Category = "seismic"; Preferred = "CSV"; Secondary = "ASCII"; TargetFolder = "03_seismic\navigation"; Metadata = "line, trace/CDP, X, Y, CRS"; Patterns = @("navigation|coordinates","Export seismic data in SEG-Y format"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "CSV exists, coordinate fields present"; Risk = "medium"; Notes = "May come from SEG-Y sidecar or table export." },
    [pscustomobject]@{ ObjectClass = "surfaces_maps"; PetrelContent = "Gridded surfaces and maps"; Category = "surfaces_and_maps"; Preferred = "ZMAP DAT"; Secondary = "XYZ ASCII"; TargetFolder = "04_surfaces_maps\zmap_dat"; Metadata = "surface name, domain, grid increment, CRS, xy_units, z_units, null_value"; Patterns = @("Export gridded surfaces","Export surfaces","surface"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "ZMAP/XYZ exists, nonzero rows, null/domain metadata present"; Risk = "medium"; Notes = "Fourth first-pilot object class." },
    [pscustomobject]@{ ObjectClass = "lines_points"; PetrelContent = "Lines, points, generic interpretation geometry"; Category = "gis_lines_points"; Preferred = "ASCII"; Secondary = "CSV"; TargetFolder = "05_interpretation\points"; Metadata = "object name, X, Y, Z/domain, point order, CRS"; Patterns = @("Export lines and points","general lines/points","Points"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "ASCII/CSV exists, coordinate fields present"; Risk = "medium"; Notes = "Generic geometry fallback." },
    [pscustomobject]@{ ObjectClass = "polygons_shapefiles"; PetrelContent = "Geopolygons, shapes, GIS objects"; Category = "gis_lines_points"; Preferred = "Shapefile"; Secondary = "CSV/ASCII"; TargetFolder = "05_interpretation\polygons"; Metadata = "object name, CRS, geometry type, attributes"; Patterns = @("Export shapefiles","Export geopolygons","geopolygon|shapefile"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "SHP sidecar files exist or CSV geometry exists"; Risk = "medium"; Notes = "Needs all shapefile sidecars preserved." },
    [pscustomobject]@{ ObjectClass = "fault_polygons_surfaces"; PetrelContent = "Fault polygons/surfaces from grids"; Category = "interpretation"; Preferred = "ASCII"; Secondary = "ZMAP/Surface"; TargetFolder = "05_interpretation\faults"; Metadata = "fault name, grid/model source, X/Y/Z, domain, units"; Patterns = @("Export faults from a 3D grid as fault polygons","Export faults from a 3D grid as fault surfaces","Faults"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "geometry files exist, coordinate/domain metadata present"; Risk = "high"; Notes = "Keep after simple exports." },
    [pscustomobject]@{ ObjectClass = "model_grids_properties"; PetrelContent = "3D grids and property models"; Category = "grids_models_simulation"; Preferred = "ECLIPSE/GRDECL"; Secondary = "RESQML"; TargetFolder = "06_models_properties\grids"; Metadata = "grid name, grid dimensions, origin, coordinate mode, property names/units, null value"; Patterns = @("Export a 3D grid","Export 3D grids","Export settings for 3D grids and properties","ECLIPSE|GRDECL"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "candidate_for_sim_results_only"; Api = "ocean_candidate"; Status = "planned_not_exported"; Validation = "GRDECL/ECLIPSE files exist, include keywords present"; Risk = "high"; Notes = "Complex but essential for full project export." },
    [pscustomobject]@{ ObjectClass = "simulation_results"; PetrelContent = "3D simulation result/composite result"; Category = "grids_models_simulation"; Preferred = "ECLIPSE/GRDECL"; Secondary = "CSV"; TargetFolder = "06_models_properties\simulation_exports"; Metadata = "case name, result name, timestep, units"; Patterns = @("Export 3D simulation results from a workflow","simulation results","ECLIPSE"); Manual = "yes"; BatchCli = "runworkflow_ready"; Workflow = "help_topic_candidate"; Api = "candidate"; Status = "planned_not_exported"; Validation = "ECLIPSE/GRDECL files exist, case metadata present"; Risk = "high"; Notes = "Only class with explicit Workflow Editor export topic found so far." },
    [pscustomobject]@{ ObjectClass = "resqml_rescue_models"; PetrelContent = "Grid models in RESQML/RESCUE"; Category = "grids_models_simulation"; Preferred = "RESQML"; Secondary = "RESCUE"; TargetFolder = "06_models_properties\simulation_exports"; Metadata = "model name, grid/properties included, CRS, units, RESQML/RESCUE version"; Patterns = @("Export a model in RESQML format","Export a RESCUE model","RESQML|RESCUE"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "model package exists, metadata sidecar present"; Risk = "high"; Notes = "Useful for richer model handoff after simple pilots." },
    [pscustomobject]@{ ObjectClass = "fluid_models"; PetrelContent = "Black oil and compositional fluid models"; Category = "grids_models_simulation"; Preferred = "ECLIPSE"; Secondary = "ASCII"; TargetFolder = "06_models_properties\simulation_exports"; Metadata = "fluid model name, components/PVT, units"; Patterns = @("Export a black oil fluid model","Export a compositional fluid model","fluid model"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "needs_petrel_export_operation"; Api = "candidate"; Status = "planned_not_exported"; Validation = "ECLIPSE keyword files exist"; Risk = "medium"; Notes = "Specialized reservoir engineering object class." },
    [pscustomobject]@{ ObjectClass = "charts_images_reports"; PetrelContent = "Charts, plots, screenshots, exported reports"; Category = "images_and_plots"; Preferred = "PNG/PDF"; Secondary = "Excel"; TargetFolder = "07_workflows_reports\screenshots"; Metadata = "view/report name, object list, date, purpose"; Patterns = @("Export and share charts and data","PNG|PDF|Image|Excel","charts"); Manual = "yes"; BatchCli = "runworkflow_ready_export_step_unproven"; Workflow = "candidate"; Api = "unknown"; Status = "planned_not_exported"; Validation = "image/report file exists, manifest row present"; Risk = "low"; Notes = "QC artifacts, not primary data." }
)

$matrixRows = @()
$evidenceRows = @()
foreach ($class in $objectClasses) {
    $evidence = @(Get-EvidenceTopics -Topics $topics -Patterns $class.Patterns)
    foreach ($topic in $evidence) {
        $evidenceRows += [pscustomobject]@{
            object_class = $class.ObjectClass
            topic_title = $topic.topic_title
            category = $topic.category
            formats = $topic.formats
            relevance_score = $topic.relevance_score
            local_path = $topic.local_path
        }
    }

    $matrixRows += [pscustomobject]@{
        object_class = $class.ObjectClass
        petrel_content = $class.PetrelContent
        category = $class.Category
        preferred_export_format = $class.Preferred
        secondary_export_format = $class.Secondary
        target_folder = $class.TargetFolder
        metadata_required = $class.Metadata
        kb_evidence_topics = Join-Values @($evidence | ForEach-Object { $_.topic_title })
        kb_evidence_formats = Join-Values @($evidence | ForEach-Object { $_.formats })
        manual_export_possible = $class.Manual
        batch_cli_possible = $class.BatchCli
        workflow_editor_possible = $class.Workflow
        api_ocean_possible = $class.Api
        external_mvp_status = $class.Status
        validation_method = $class.Validation
        risk_level = $class.Risk
        notes = $class.Notes
    }
}

$matrixPath = Join-Path $manifestDir "full_project_export_capability_matrix.csv"
$evidencePath = Join-Path $mvpDir "kb_evidence_used.csv"
$matrixRows | Export-Csv -LiteralPath $matrixPath -NoTypeInformation -Encoding UTF8
$evidenceRows | Export-Csv -LiteralPath $evidencePath -NoTypeInformation -Encoding UTF8

$planRows = @()
$phase = 1
foreach ($row in $matrixRows) {
    $planRows += [pscustomobject]@{
        plan_id = ("P{0:00}_{1}" -f $phase, $row.object_class)
        phase = $phase
        object_class = $row.object_class
        target_folder = $row.target_folder
        preferred_export_format = $row.preferred_export_format
        petrel_side_action = "Export matching Petrel objects to export_package\$($row.target_folder)"
        external_action = "register_petrel_file_exports.ps1 scans target folder and validate_export_package.ps1 validates manifest rows"
        current_status = $row.external_mvp_status
        validation_method = $row.validation_method
    }
    $phase += 1
}

$planPath = Join-Path $manifestDir "full_project_export_plan.csv"
$planRows | Export-Csv -LiteralPath $planPath -NoTypeInformation -Encoding UTF8

$bridgeScript = Join-Path $scriptDir "petrel_export_mvp_bridge.ps1"
$bridgeCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$bridgeScript`" -StepName `"post_export_register_validate`""
$runCommand = Join-Path $scriptDir "run_petrel_export_pilot.ps1"

$workflowSpec = [ordered]@{
    schema_version = "0.1"
    workflow_name = "petrel.workflow.export_project_universal_package"
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    source_kb = [ordered]@{
        help_topic_csv = $helpCsvPath
        workflow_note = "vault/Petrel Knowledge Wiki/20 Workflows/Export Petrel Project To Universal Formats.md"
        inventory_note = "vault/Petrel Knowledge Wiki/20 Workflows/Create Petrel Project Inventory.md"
        package_structure_note = "vault/Petrel Knowledge Wiki/50 Concepts/Universal Petrel Export Package Structure.md"
    }
    petrel_project = [ordered]@{
        project_name = $ProjectName
        petrel_version = $PetrelVersion
        export_package = $exportRoot
        inventory_package = $inventoryRoot
    }
    required_petrel_workflow_variables = @(
        [ordered]@{ name = "export_package"; type = "string"; source = "CLI -sparm"; value = $exportRoot },
        [ordered]@{ name = "inventory_package"; type = "string"; source = "CLI -sparm"; value = $inventoryRoot },
        [ordered]@{ name = "export_manifest"; type = "string"; source = "CLI -sparm"; value = Join-Path $manifestDir "export_manifest.csv" }
    )
    cli_runner = [ordered]@{
        command = $runCommand
        current_workflow_name = $WorkflowName
        status = "verified_for_variable_bridge_and_post_run_registration"
    }
    petrel_workflow_editor_mvp = [ordered]@{
        system_command_step = $bridgeCommand
        status = "external_bridge_script_ready"
        purpose = "Call from Petrel Workflow Editor after Petrel export operations to register files, validate, and write reports."
    }
    phases = @(
        [ordered]@{ id = "inventory"; status = "mvp_schema_ready"; output = "00_manifest/source_object_inventory.csv"; action = "Populate inventory manually, through Workflow Editor/UI-assisted capture, or through native workflow mapping." },
        [ordered]@{ id = "export_plan"; status = "generated_from_kb"; output = "00_manifest/full_project_export_plan.csv"; action = "Use KB-derived capability matrix to choose export operation per object class." },
        [ordered]@{ id = "petrel_export"; status = "petrel_side_operations_needed"; output = "02_wells, 03_seismic, 04_surfaces_maps, 05_interpretation, 06_models_properties"; action = "Workflow Editor operations or validated UI/native workflow tooling must write object files to target folders." },
        [ordered]@{ id = "external_bridge"; status = "ready"; output = "07_workflows_reports/exported_reports/external_workflow_bridge_probe.csv"; action = "Run petrel_export_mvp_bridge.ps1 from a Petrel System command step." },
        [ordered]@{ id = "registration_validation"; status = "ready"; output = "export_manifest.csv, checksums_sha256.txt, validation reports"; action = "Register workflow artifacts and file exports, then validate." }
    )
    object_classes = $matrixRows
}

$workflowSpecPath = Join-Path $manifestDir "petrel_full_project_export.workflow.json"
$workflowSpec | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $workflowSpecPath -Encoding UTF8

$mcpSpec = [ordered]@{
    tool_name = "petrel.workflow.export_project_universal_package"
    version = "0.1-mvp"
    status = "prototype_no_ocean_mcp_and_package_runner_ready"
    mcp_server = [ordered]@{
        name = "petrel-no-ocean-control"
        path = Join-Path (Split-Path -Parent $scriptDir) "mcp\petrel_mcp_server.py"
        transport = "stdio"
        requires_ocean_license = $false
        smoke_test = Join-Path $scriptDir "test_petrel_mcp_server.py"
    }
    inputs = [ordered]@{
        project = "petrel_project_ref"
        export_package = "directory"
        inventory_package = "directory"
        scope = "full_project_or_object_filter"
    }
    outputs = [ordered]@{
        export_package = $exportRoot
        manifest = Join-Path $manifestDir "export_manifest.csv"
        capability_matrix = $matrixPath
        export_plan = $planPath
        workflow_spec = $workflowSpecPath
    }
    current_execution_surface = @(
        "PowerShell CLI runner",
        "No-Ocean stdio MCP server",
        "MCP-controlled Petrel project open dry-run/writable launch",
        "Petrel -runWorkflow bridge",
        "Petrel Workflow Editor System command bridge",
        "Native .ptd snapshot/compare workflow",
        "Native .ptd region mapper and guarded same-length patch dry-runs",
        "External manifest registration and validation scripts"
    )
    missing_execution_surface = @(
        "Petrel-side object enumeration",
        "Petrel-side object export operations for each class",
        "Safe record insertion/resize format for native Petrel workflow storage",
        "Mapped UI or native Workflow Editor operations for first real wells/logs/surfaces exports"
    )
}
$mcpSpecPath = Join-Path $mvpDir "mcp_tool_spec.petrel.workflow.export_project_universal_package.json"
$mcpSpec | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $mcpSpecPath -Encoding UTF8

$matrixMdPath = Join-Path $mvpDir "full_project_export_capability_matrix.md"
$md = @(
    "# Full Project Export Capability Matrix",
    "",
    "- Generated UTC: $((Get-Date).ToUniversalTime().ToString("o"))",
    "- Source KB index: $helpCsvPath",
    "- Export package: $exportRoot",
    "- Current status: external MVP and no-Ocean MCP wrapper ready; Petrel-side export operations still require Workflow Editor, UI-assisted, or mapped native implementation.",
    "",
    "| Object class | Preferred | Target folder | Workflow status | MVP status | Risk | Evidence topics |",
    "| --- | --- | --- | --- | --- | --- | --- |"
)
foreach ($row in $matrixRows) {
    $topicsText = $row.kb_evidence_topics -replace "\|", "/"
    $md += "| $($row.object_class) | $($row.preferred_export_format) | $($row.target_folder) | $($row.workflow_editor_possible) | $($row.external_mvp_status) | $($row.risk_level) | $topicsText |"
}
$md | Set-Content -LiteralPath $matrixMdPath -Encoding UTF8

$buildSheetPath = Join-Path $mvpDir "petrel_workflow_editor_build_sheet.md"
$manifestCsvPath = Join-Path $manifestDir "export_manifest.csv"
$buildSheet = @(
    "# Petrel Workflow Editor Build Sheet - ExportPiloX MVP",
    "",
    "This is the external workflow-as-code build sheet generated from the local Petrel KB. It is safe to edit outside Petrel. It does not patch the proprietary .pet or .ptd files directly.",
    "",
    "## Required Workflow Variables",
    "",
    "| Name | Type | Value source |",
    "| --- | --- | --- |",
    "| export_package | string/text | CLI -sparm; current value $exportRoot |",
    "| inventory_package | string/text | CLI -sparm; current value $inventoryRoot |",
    "| export_manifest | string/text | CLI -sparm; current value $manifestCsvPath |",
    "",
    "## Minimum Petrel Workflow Steps",
    "",
    "1. Keep the existing variable probe/output-sheet step.",
    "2. Add export operations for the first pilot classes in this order: well_headers, well_logs, data_tables, surfaces_maps.",
    "3. Write all files under the target folders shown in 00_manifest/full_project_export_plan.csv.",
    "4. Add a final Workflow Editor System command step with this exact command:",
    "",
    '```powershell',
    $bridgeCommand,
    '```',
    "",
    "5. Run from outside Petrel with:",
    "",
    '```powershell',
    ".\scripts\run_petrel_export_pilot.ps1",
    '```',
    "",
    "The CLI runner sets PETREL_EXPORT_PACKAGE, PETREL_INVENTORY_PACKAGE, and PETREL_EXPORT_MANIFEST before launching Petrel. The System command bridge inherits those values and calls the external registrar/validator.",
    "",
    "## First MVP Export Order",
    "",
    "| Order | Object class | Target folder | Validation |",
    "| ---: | --- | --- | --- |"
)
$order = 1
foreach ($row in @($matrixRows | Where-Object { $_.object_class -in @("well_headers", "well_logs", "data_tables", "surfaces_maps") })) {
    $buildSheet += "| $order | $($row.object_class) | $($row.target_folder) | $($row.validation_method) |"
    $order += 1
}
$buildSheet += @(
    "",
    "## External Native Workflow Editing Status",
    "",
    "- Safe external artifact created: 00_manifest/petrel_full_project_export.workflow.json.",
    "- Native Petrel workflow binary/project stores are not patched because no safe import/export format has been confirmed yet.",
    "- Next technical target: either discover a supported workflow import/export format or use an Ocean plugin/MCP server to create/update workflows through Petrel's supported APIs."
)
$buildSheet | Set-Content -LiteralPath $buildSheetPath -Encoding UTF8

$readmePath = Join-Path $mvpDir "README.md"
$readme = @(
    "# Petrel Full Project Export MVP",
    "",
    "This folder is the first KB-driven MVP for full project data export.",
    "",
    "Generated files:",
    "",
    "- 00_manifest/full_project_export_capability_matrix.csv",
    "- 00_manifest/full_project_export_plan.csv",
    "- 00_manifest/petrel_full_project_export.workflow.json",
    "- 07_workflows_reports/mvp_full_project_export/petrel_workflow_editor_build_sheet.md",
    "- 07_workflows_reports/mvp_full_project_export/mcp_tool_spec.petrel.workflow.export_project_universal_package.json",
    "- 07_workflows_reports/mvp_full_project_export/kb_evidence_used.csv",
    "",
    "Run the generator again with:",
    "",
    '```powershell',
    ".\scripts\build_petrel_full_export_mvp.ps1",
    '```',
    "",
    "Run the current Petrel CLI bridge with:",
    "",
    '```powershell',
    ".\scripts\run_petrel_export_pilot.ps1",
    '```'
)
$readme | Set-Content -LiteralPath $readmePath -Encoding UTF8

Write-Output "MVP generated"
Write-Output "Capability matrix: $matrixPath"
Write-Output "Export plan: $planPath"
Write-Output "Workflow spec: $workflowSpecPath"
Write-Output "Workflow build sheet: $buildSheetPath"
Write-Output "MCP tool spec: $mcpSpecPath"
