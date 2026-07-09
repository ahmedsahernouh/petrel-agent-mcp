# Petrel Agent MCP

**An AI agent control surface for Schlumberger Petrel — with no Ocean SDK, no vendor API, and no Python connector.**

This repository contains a 41-tool [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI agents (Claude, Codex, or any MCP client) inventory, export, convert, audit, and round-trip data through Petrel 2018.2. It exists to demonstrate a broader thesis:

> **Agentic AI can control software that has no API.** Old versions, closed desktop applications, license-gated vendor SDKs — if a human can operate it, an agent can be given a safe, deterministic, evidence-gated tool surface for it.

Petrel 2018.2 is the demonstration case, not the boundary. Nothing here uses the Ocean developer framework or any modern Petrel connector; connectors for this version either do not exist or require licenses this project deliberately does without.

## How it works: four routes

Every tool is built on the highest viable tier of a strict hierarchy:

| Tier | Route | Example tools |
|------|-------|---------------|
| 1 | **Zero-GUI file processing** — decode and write Petrel's own file formats directly | native store export, `.zhz` surface decode → ZMAP+/XYZ, ZGY seismic → arrays, LAS → CSV, well tops ASCII writer, project audit report |
| 2 | **Saved Workflow Editor / native control** — drive Petrel headlessly through its own saved workflows, with guarded patch-run-restore | SEG-Y export via donor workflow, SystemCmd bridge, workflow runner |
| 3 | **Deterministic GUI micro-workflows** — fail-closed UIA + OCR automation, no hardcoded coordinates | Well Tops ASCII export (validated 84/84 rows), well logs LAS export |
| 4 | **Discovery / donor capture** — mapping and analysis only, never production automation | native workflow region mapper, clone-readiness analyzers |

**32 of the 41 tools never start Petrel at all** — they work purely on project files, so they run without consuming a Petrel license (the project files themselves originate from a licensed Petrel).

## Safety model

- Every tool carries a **fail-closed failure policy** (`mcp/petrel_mcp_failure_policies.json`) and returns a per-run **result audit** with evidence, failure class, and next safe action.
- Tools that could launch Petrel are **dry-run by default** and require explicit opt-in flags.
- Native project files are never mutated without snapshot → patch → validate → restore evidence.
- Every exported artifact is registered in a **manifest with SHA-256 checksums** and validated.
- Anything unproven refuses loudly (`layout_unresolved`, `preflight_failed`, `blocked`) instead of guessing.

## Quickstart (new machine)

Requirements: Windows, Python 3.10+ (the MCP server itself is **pure standard library** — no `pip install` needed to run it).

```powershell
git clone https://github.com/ahmedsahernouh/petrel-agent-mcp ; cd petrel-agent-mcp
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_petrel_mcp.ps1
```

That single command checks your Python version, creates a local `.venv`, installs the optional geodata packages (numpy, zmapio, pyzgy, lasio, pandas — for the surface/ZGY/grid/LAS chain tools), writes the project `.mcp.json`, reports whether Tesseract and Petrel are present, and finishes by running the 41-tool protocol smoke test. If it prints `Petrel MCP smoke test passed`, you are done. Pass `-NoVenv -NoGeodata -NoSmoke` for the minimal config-only behavior; `scripts\doctor_petrel_mcp.ps1` is the deeper environment check.

Then approve the server in your MCP client (Claude Code picks up the project `.mcp.json` automatically), or register it manually:

```powershell
claude mcp add --transport stdio petrel-no-ocean-control -- python <checkout>\mcp\petrel_mcp_server.py
```

External tools some routes need (setup detects and reports both; nothing fails without them):

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — deterministic GUI tools only
- Petrel 2018.2 — only for the 9 tools that launch or drive Petrel itself

## Quickstart (your own Petrel project)

1. Call `petrel_prepare_mvp` with your `.pet` project path — scaffolds an inventory + export package.
2. Run the zero-GUI exporters: `petrel_export_native_zero_gui`, `petrel_export_native_semantic_zero_gui`, `petrel_export_well_tables_zero_gui`, `petrel_export_surfaces_zero_gui`, `petrel_export_seismic_zgy_zero_gui`.
3. Call `petrel_project_audit_report` — a self-contained HTML audit of everything found, with QC flags, without Petrel ever starting.
4. For live-Petrel routes (saved-workflow SEG-Y export, GUI exports), follow `docs/NO_OCEAN_MCP_CONTROL.md` — these need one-time per-project setup (a donor saved workflow, a GUI calibration pass).

Start every agent session with `petrel_agent_readiness` → `petrel_status` → `petrel_tool_creation_hierarchy` → `petrel_tool_failure_policy`; the server tells the agent what is proven, what is beta, and what is refused.

## Honest boundaries

- **Version scope is Petrel 2018.2.** Native format decoding and GUI geometry were validated there and nowhere else; the framework is version-aware, but cross-version use requires revalidation, and the tools say so rather than pretend otherwise.
- Validated end-to-end on one full demo project; a new project needs the per-project setup steps above.
- Native binary *marker-pick* decoding is **not** solved (the ASCII round-trip route is); zero-GUI creation of *new* workflow commands is **not** solved (analyzers are `blocked` pending donor evidence). The docs record what failed as carefully as what worked.
- The knowledge base (OKF/wiki) this project was developed against derives from licensed Petrel documentation and is **not** included; `petrel_query_kb` and `petrel_generate_workflow_from_okf` degrade gracefully without it. `docs/AGENT_INDEX_AND_RETRIEVAL.md` + `scripts/build_agent_index.py` let you build your own.
- The demonstration project data (Schlumberger's Petrel 2010 demo project) is likewise not redistributable and not included.

## Documentation

| Doc | Contents |
|-----|----------|
| `docs/AI_CODER_HANDOVER_2026-07-08.md` | Full operational handover for an AI coder |
| `docs/NO_OCEAN_MCP_CONTROL.md` | The control path: every tool, every boundary |
| `docs/PETREL_TOOL_CREATION_HIERARCHY.md` | The four-tier tool creation contract |
| `docs/MCP_FAILURE_POLICY.md` | Fail-closed policy + result audit system |
| `docs/DETERMINISTIC_PETREL_GUI_WORKFLOWS.md` | UIA/OCR GUI automation: patterns, performance, robustness |
| `docs/PETREL_NATIVE_WORKFLOW_EDITING.md` | Native store research: what is proven, what is refused |
| `docs/FULL_PROJECT_EXPORT_MVP.md` | The full-project export pipeline |
| `docs/STAGE_1_NO_OCEAN_MCP_BASELINE.md` | Stage-1 baseline and evidence |

## Trademark and intent

Petrel and Ocean are trademarks of SLB (Schlumberger). This is an independent research project, not affiliated with or endorsed by SLB. File-format handling exists for interoperability with data the user already owns; nothing here circumvents licensing — tools that require Petrel still require a licensed Petrel.
