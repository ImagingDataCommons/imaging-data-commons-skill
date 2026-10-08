# Changelog

All notable changes to the Imaging Data Commons Skill are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.9.0] - 2026-10-08

IDC v25, `idc-index` 0.13.0 (`idc-index-data` 25.0.0), REST/MCP API `3.0.0b5`. The package bump
carries no API change; the substance of the release is **data provenance**.

### Added

- **Provenance** (`index_tables_guide.md`, `sql_patterns.md`, `SKILL.md`): who contributed,
  de-identified, and DICOM-converted each part of the archive. Recorded **per source, keyed on
  `source_DOI`** — `collections_index.sources` is a list of structs (unnest it) with a nested
  `provenance`; `analysis_results_index.provenance` is a new column. A `NULL` struct means that
  source is an analysis result, so look it up in the other table — across the pair, coverage is
  complete. `NOT_APPLICABLE` / `UNKNOWN` / `NOT_DOCUMENTED` are values, not nulls
- Four `index` columns the guides never carried: `sop_class_name`, `transfer_syntax_name`,
  `PhotometricInterpretation`, `PixelRepresentation`. All four are comma-separated when instances
  in a series disagree (~72 000 series) and the latter two are `NULL` for SEG/SR/RTSTRUCT, so `=`
  silently drops mixed-encoding series. `sop_class_name`, not `SOPClassUID`, is filterable
- Hugging Face mirror of the Parquet artifacts
  ([`ImagingDataCommons/idc-index-data`](https://huggingface.co/datasets/ImagingDataCommons/idc-index-data),
  public, no token). A fallback only — revision tags are incomplete, so pin via GCS
- Four missing Parquet artifacts: `sm_instance_index`, `version_metadata_index`,
  `gdc_idc_mapping` (the imaging/genomics join), `tcia_idc_subset`
- `TestProvenance`, covering the unnest path, the NULL-is-a-pointer rule, and `tcga_brca`

### Changed

- Pinned minimum `idc-index` **0.12.5 → 0.13.0**; documented data version **v24 → v25**. Older
  installs report `v24` and cannot download series added in v25
- Archive totals **176 → 179 collections**, ~99 → **~100 TB**; mixed-license collections still 39
- API claims **`3.0.0b3` → `3.0.0b5`**; tool inventory, the 19 filterable attributes, and all REST
  limits re-verified unchanged
- BigQuery example `idc_v24` → `idc_v25`. The DICOMweb store stays `idc-store-v24` — stores lag a
  release by 1-2 weeks and `idc-store-v25` is not populated yet, which `dicomweb_guide.md` now
  warns about at the point of use

### Fixed

- `test_snippets.py` hardcoded `"v24"`, needing a hand edit every data release. It now reads
  `idc-data-version` from the frontmatter, so a stale pin fails CI instead of stale guides

## [1.8.3] - 2026-09-03

A stale index returns zero rows rather than an error, and `scripts/check_version.py` was
too easy to skip. Prompted by an IDC-Tutorials review that ran against 0.12.3 and reported
a working notebook as broken.

### Fixed

- Documented invocation of `scripts/check_version.py` no longer hardcodes an interpreter.
  No name is portable — `python` and `python3` each go missing on common platforms, and
  the failure is a non-fatal `command not found`. Pinned by `tests/test_structure.py`
- Version pins, left at 1.8.1 by the 1.8.2 release, so every checkout reported an update
  that was already installed. Now tracked by `tests/test_check_version.py`

### Added

- `SKILL.md` *Running the version check*: confirm the `meets pinned minimum` line rather
  than assume the command ran
- Setup snippet repeats the check in Python, where it cannot be skipped or fail to launch
- Stale-index output states the consequence — zero rows, not an error — instead of only
  the version gap

### Changed

- Access-path gate step 2 asks whether `idc-index` is "installed and current", not just
  "installed", which an agent that already has it reads as a satisfied precondition

## [1.8.2] - 2026-08-12

### Added

- `SYNC.md`: how registries should vendor the skill. Bundle unchanged

## [1.8.1] - 2026-08-10

Conformance pass from review of the downstream sync in
[K-Dense-AI/scientific-agent-skills#158](https://github.com/K-Dense-AI/scientific-agent-skills/pull/158):
each item was a local edit a registry had to make to the vendored copy, so fixing it here
keeps the next sync a straight file copy.

### Fixed

- `SKILL.md` frontmatter indents `metadata` two spaces, not four. Four is valid YAML, but
  registry validators that read frontmatter line by line see only two-space nesting and
  report `metadata.version` as missing. Pinned by `tests/test_structure.py`

### Changed

- No hardcoded installer commands in the bundle: `SKILL.md` and the guides name the package
  needed and point at `scripts/check_version.py` instead of printing `pip install …`, which
  targets whichever interpreter `pip` resolves to, drops the pinned version, and collides
  with environments standardized on another installer. Guarded by `tests/test_structure.py`
- `check_version.py` prefers `uv` when on `PATH`, with `--python` so it targets the
  interpreter that failed to import `idc_index` rather than the active environment. Neither
  form overrides PEP 668

### Added

- `tests/test_check_version.py`: offline, standard-library-only contract for the bundled
  script — version parsing, install-command construction, exit codes, best-effort network
  notices, and guards that it never shells out to an installer or bypasses PEP 668. Runs
  with nothing installed, so a registry that requires a suite for any skill shipping
  `scripts/` can use it as-is; the duplicated cases left `tests/test_snippets.py`
- `scripts/**` to the `test-snippets.yml` path filters — a change to the bundled script did
  not trigger CI

## [1.8.0] - 2026-08-10

### Added

- `references/rest_api_guide.md` — IDC's hosted REST API at `https://api.imaging.datacommons.cancer.gov/v3` (no authentication): query surfaces, endpoint reference, `terms` / `ranges` filter syntax, SQL guardrails, clinical tables, manifests, licenses, citations. Verified endpoint by endpoint against API 3.0.0b3 / IDC v24
- One filter body shape on every filtered endpoint — the filter object goes under `filters`. Misuse is refused rather than ignored (`422` for a bare filter or unknown key, `400` for an unfiltered manifest), and responses echo `filters_applied` and `warnings`, so a zero count with no warnings means the filter matched nothing ([IDC-REST-MCP#44](https://github.com/ImagingDataCommons/IDC-REST-MCP/pull/44))
- Measured request limits: `/sql` 5000 / 10000 rows and a 30 s timeout, `cohort/manifest` `page_size` 100 / 5000, `manifest.txt` 100000 series, clinical rows 5000 / 100000, attribute values 100 / 10000. No rate limit or quota
- How to check the API against a local `idc-index` via `idc_index_data_version`, and how to read a mismatch: the major is the IDC data release (`24.x.y` serves `v24`), so a differing major means different series, while a differing minor or patch is an index build of the same release
- Workaround for a major mismatch: `idc-index` silently skips manifest rows its own index does not list, so upgrade it or transfer directly from the bucket with `s5cmd --no-sign-request`. Also summarized in `SKILL.md`, since the failure is silent
- "Use v3 only" guidance in `SKILL.md` and the guide: V1 and V2 are superseded and scheduled for shutdown, so V1/V2 examples should be ported rather than extended
- REST API entries in `SKILL.md` (Data Access Options, Quick Navigation, Tool Selection Guide, network access) and `USAGE.md` (setup section, allowed domains, guide listings)
- `tests/test_rest_api.py`: contract tests for the guide's endpoints, attributes, limits, and filter contract, checked against the live API and skipping when unreachable. `IDC_API_BASE` points them at a staging deployment. Added to `test-snippets.yml`

- `references/licensing_and_citation.md` — license semantics (CC BY vs CC BY-NC shares, custom terms, the most-restrictive-term rule for mixed cohorts) and citation generation. Written access-path-neutral: `idc-index`, `POST /v3/licenses` / `POST /v3/citations`, and the `get_licenses` / `get_citations` MCP tools side by side, since neither task is tied to Python
- `tests/test_structure.py` — file-only contract tests, added to `test-snippets.yml` ahead of the slower suites: a 500-line budget for `SKILL.md`, resolution of every guide it names, no orphan guides in `references/`, and assertions pinning the always-loaded content listed below. No network or `idc-index` install needed

### Changed

- Access-path selection is task-based rather than one fixed default. With no MCP server and no `idc-index` installed, read-only metadata (counts, attribute values, SQL under 10000 rows, licenses, citations, viewer URLs) goes to the REST API instead of paying a ~77 MB install; `idc-index` remains the path for downloads, pandas, pixel data, and larger results, and the only one that moves image bytes. `SKILL.md` opens with that four-branch gate, and its frontmatter description no longer names `idc-index`
- `SKILL.md` and the troubleshooting entries defer to `scripts/check_version.py` for install and upgrade commands rather than printing a bare `pip install`, which could target a different interpreter than the one running and ignores the pinned version
- Positioned direct Parquet access after the REST API: it still needs `pip install duckdb` and does not publish the per-collection clinical tables, so it is for version pinning and results past the REST row cap
- Reduced `SKILL.md` from 722 to under 500 lines, holding the budget in CI rather than leaving it to downstream registries to re-split after every sync. Content moved into the topical guide that already owns each subject rather than into a new catch-all file:
  - Discovery and SQL examples (overall-scale query, per-collection breakdown, `collections_index` / `analysis_results_index` queries) → `references/sql_patterns.md`
  - Full index-table inventory with row granularity → `references/index_tables_guide.md`, which also gained the "which table contains column X" search pattern; `SKILL.md` keeps a five-row table-family map
  - Python `dirTemplate=` examples and the default template → `references/cli_guide.md`
  - License and citation detail → `references/licensing_and_citation.md`
  - Clinical-access snippet and BigQuery use-case list condensed to pointers; the "Common SQL Query Patterns" section removed as a duplicate of its Quick Navigation entry
  - The Tool Selection Guide table merged into Data Access Options, which gained a Reference column — the two listed the same access paths
- Corrected the Data Access Options table: DICOMweb split into its proxy (no auth, quota) and Google Healthcare (GCP auth) routes; BigQuery moved last and marked a last resort; the IDC Portal pulled out of the table as the one interactive-only option
- Kept inline, and now pinned there by `tests/test_structure.py`, the guidance that corrects what a model gets confidently wrong from its own priors — a reference file only helps when the agent already knows to look: the opposite argument order of `download_from_selection` and `download_dicom_series`, the "filter kwargs, NOT a DataFrame" warning, enumerate-values-before-filtering, the CC BY-NC license class, and routing "what's new in vX" to `series_init_idc_version` rather than `prior_versions_index`
- `test_endpoint_url_is_consistent_across_docs` now allows `/v3` REST paths alongside the MCP URL, still rejecting a bare host or a stale `/v1`, `/v2` path

### Notes

This is a rewrite, not a byte-for-byte relocation. Of 116 executable lines in the previous
`SKILL.md`, 104 appear verbatim elsewhere in the bundle; the other 12 are mostly re-wrapping.
Three deliberate removals: a `results.iterrows()` printing demo, the SQL form of clinical-table
discovery (`clinical_data_guide.md` covers it via the DataFrame API), and a duplicate
`cohort/counts` curl already in `rest_api_guide.md`.

A text diff is the weaker check regardless — what a split changes is which content is in context
at decision time. `tests/test_snippets.py` executes the queries: 97 passed against IDC v24.

## [1.7.1] - 2026-08-01

### Changed

- Trimmed `SKILL.md` from 791 to 684 lines by relocating content to reference guides rather than deleting it, resuming the Phase 2 reduction that the 1.7.0 MCP section had reversed:
  - Moved the three "what's new in IDC vX" queries to `references/sql_patterns.md` under a new "Version Tracking" section; `SKILL.md` keeps the guidance that matters (use `series_init_idc_version` / `series_revised_idc_version`, never `prior_versions_index`) as a pointer
  - Dropped the second filter-value-discovery query from "Querying Metadata with SQL", which duplicated the `BodyPartExamined` pattern already in `sql_patterns.md`, and the flat-`dirTemplate` and `source_bucket_location="gcs"` download variants, both now described in prose next to the canonical example
  - Removed the repeated `from idc_index import IDCClient` / `client = IDCClient()` preamble from six examples, stating once in the Overview that examples assume it — matching how `sql_patterns.md` is already written
  - Condensed the DICOMweb endpoint table, the `citations_from_selection` parameter list, and the downloaded-file-naming notes into prose; the full endpoint details remain in `references/dicomweb_guide.md`
  - Deduplicated the two `references/bigquery_guide.md` pointers in "Advanced Queries with BigQuery"

## [1.7.0] - 2026-07-31

### Added

- "IDC MCP Server" section in `SKILL.md` and `references/mcp_guide.md`, covering IDC's hosted MCP server at `https://api.imaging.datacommons.cancer.gov/mcp` (streamable HTTP, no authentication): how to recognize it, how to divide work between it and `idc-index`, and how to hand off SeriesInstanceUIDs for download
- Guidance to identify the server by its `idc://guide` MCP resource or a fingerprint of three or more IDC-specific tool names, and to fall back to `idc-index` whenever identification is ambiguous — generic tool names such as `run_sql` are explicitly not treated as evidence
- "IDC MCP Server (Optional)" section in `USAGE.md` with the endpoint, when adding it is worthwhile, and a Claude Code registration example
- `tests/test_mcp_server.py`: contract tests that parse the documented tool fingerprint and inventory out of `SKILL.md` / `references/mcp_guide.md` and check them against the live server, so the docs cannot drift silently as the beta server evolves; network tests skip rather than fail when the server is unreachable, and the offline checks guard URL consistency and keep generic tool names out of the fingerprint
- `USAGE.md` to the `test-snippets.yml` path filter, since the new tests read it
- Snippet test coverage for `references/use_cases.md`, `references/digital_pathology_guide.md`, and `references/parquet_access_guide.md`, which had none: 31 tests covering the use-case selection queries, every slide microscopy / annotation / segmentation query in the pathology guide, and the DuckDB-over-HTTPS Parquet queries. The pathology tests assert the TCGA-BRCA slide counts quoted inline in that guide (2704 primary / 399 normal, barcode sample types 01/06/11), so a data release that moves them fails CI instead of silently making the prose wrong
- `TestParquetAccessGuide` checks that every Parquet file listed in the guide exists under `current/` and that `current/` resolves to the installed `idc-index-data` release

### Changed

- Moved the MCP-vs-`idc-index` routing decision into the `SKILL.md` Overview, next to "Primary tool", so a session that already has the MCP server can skip the `idc-index` setup instead of discovering the alternative only after running it; `idc-index` remains the primary, always-available path and the version-check step is unconditional again
- `scripts/check_version.py` no longer installs anything: when `idc-index` is missing or below the pinned minimum it prints the `pip install` command for the running interpreter and exits non-zero, leaving the choice of environment to the user. `SKILL.md` documents the new behavior
- Updated to idc-index 0.12.5 (idc-index-data 24.2.2); IDC data version remains v24. 0.12.5 relaxes the dependency to `pandas>=2.2.2,<4`, so installing the skill's pinned minimum no longer downgrades a pandas 3.x environment (verified: 0.12.5 installs alongside pandas 3.0.5)
- Refreshed the stale `Tested with:` headers in `references/`: `use_cases.md`, `clinical_data_guide.md`, and `digital_pathology_guide.md` claimed idc-index 0.12.1, and `parquet_access_guide.md` claimed idc-index-data 23.10.1. All snippets were re-run against idc-index 0.12.5 / idc-index-data 24.2.2 before the headers were updated. `bigquery_guide.md` now names the BigQuery dataset it was validated against (`bigquery-public-data.idc_current`, via `bq query --dry_run`) rather than an idc-index version its SQL does not use
- Repository renamed from `idc-claude-skill` to `imaging-data-commons-skill` on GitHub to reflect that the skill is not specific to Claude
- Made `README.md`, `USAGE.md`, `CHANGELOG.md`, the issue template, and test docstrings vendor-neutral: the skill is described as an Agent Skills–format skill usable with any compatible AI assistant; Claude-specific setup instructions remain as one supported environment
- Promoted the `npx skills add` cross-agent installation to the top of `USAGE.md`; renamed "Claude API Setup" to "API Setup"

### Security

- Removed the `pip3 install --upgrade --break-system-packages` call from `scripts/check_version.py`. It bypassed the PEP 668 guard on externally managed interpreters, and — combined with the `pandas<=2.2.4` cap in idc-index ≤ 0.12.4 — could silently downgrade a system-wide pandas 3.x as a side effect of a version *check*. It also invoked whatever `pip3` resolved to on `PATH`, which is not necessarily the running interpreter's pip, so an install could land in a different environment than the one that failed to import `idc_index`. Reported in review of K-Dense-AI/scientific-agent-skills#158

### Fixed

- `parse_version` in `scripts/check_version.py` no longer raises on pre-release or suffixed tags (`0.13.0rc1`, `v1.7.0-beta`); it takes the leading digits of each component and pads to three, so an upstream pre-release cannot crash the startup check. Pre-releases compare equal to their base release, keeping update notices conservative

## [1.6.5] - 2026-06-17

### Added

- `scripts/check_version.py` (run first): installs the pinned author-vetted `idc-index` minimum, then prints best-effort, notify-only notices when a newer `idc-index` (PyPI) or skill release (GitHub) is available — never auto-installs newer releases, silently skipped offline
- "Keeping the Skill Up to Date" section in `USAGE.md` (release notifications, per-surface update steps, fresh-conversation reminder); linked from README

### Changed

- Replaced the inline startup version-check in `SKILL.md` with a prominent pointer to `scripts/check_version.py`, keeping the code out of the model's context
- Renamed repository references `idc-claude-skill` → `imaging-data-commons-skill` across `SKILL.md`, `README.md`, `USAGE.md`
- Pointed `tests/test_snippets.py` at the new script and added a guard that its `MIN_VERSION`/`SKILL_VERSION` match the SKILL.md frontmatter

### Fixed

- Standardized the required `idc-index` on `0.12.3` (was `0.12.2` in the version-check vs `0.12.3` in frontmatter) and switched to numeric, not string, version comparison

## [1.6.4] - 2026-05-22

### Changed

- Added version tracking guidance: "what's new in vX" workflow using `series_init_idc_version`/`series_revised_idc_version` in `index`; clarified `prior_versions_index` is for reproducibility only (zero overlap with `index`, column names differ from main index version columns)
- Collapsed five `SeriesInstanceUID` join rows into a single universal-key statement; table now covers only non-obvious join columns
- Removed Installation and Setup section (duplicated the CRITICAL version-check block); folded optional deps into `ModuleNotFoundError` Troubleshooting entry
- Trimmed "Command-Line Download" inline section from ~60 lines to 5; full CLI coverage (`download-from-manifest`, `download-from-selection`, all options) remains in `references/cli_guide.md`

## [1.6.3] - 2026-05-09

### Added

- `ct_index`, `mr_index`, `pt_index` tables (idc-index 0.12.3 / idc-index-data 24.2.0): modality-specific acquisition and reconstruction parameter indices, one row per series, all joining on `SeriesInstanceUID`
  - `ct_index` (21 columns): pixel spacing, slice thickness, kVp, convolution kernel, tube current min/max (dose-modulated), exposure, spiral pitch, scan options
  - `mr_index` (22 columns): field strength, scanning sequence, TE (array for multi-echo), TR, flip angle, DiffusionBValue (array for DWI), pixel bandwidth, receive coil, number of temporal positions
  - `pt_index` (21 columns): radionuclide, injected dose, reconstruction method, decay/scatter/attenuation correction, frame duration (array for dynamic PET), number of time slices
- SQL query patterns for all three new tables in `references/sql_patterns.md`
- Join column entries for `ct_index`, `mr_index`, `pt_index` in `references/index_tables_guide.md` and SKILL.md
- Parquet file entries for `ct_index.parquet`, `mr_index.parquet`, `pt_index.parquet` in `references/parquet_access_guide.md`

### Changed

- Added concrete `indices_overview` code example showing how to search for a column across all tables and read column schemas without fetching the table; directly addresses the failure mode where agents query `index` for modality-specific parameters (SliceThickness, KVP, etc.) instead of using `ct_index`/`mr_index`/`pt_index`
- Added troubleshooting entry "Column not found in `index` table" with a working `indices_overview` search snippet and join example, covering common acquisition/reconstruction parameters that live in the modality-specific index tables
- Updated idc-index reference to 0.12.3
- Clarified `download_from_selection` API: added explicit warning that it takes filter keyword arguments (not a DataFrame), comparison table vs `download_dicom_series` (which has a different first-argument order), and restructured the download example as a step-by-step query → extract UIDs → pass list flow
- Documented `download_dicom_series` as an alternative download method with its own signature (`seriesInstanceUID` as first arg, then `downloadDir`)
- Reduced redundancy and duplication in SKILL.md for cleaner reading

## [1.6.2] - 2026-05-08

### Changed

- Moved `version_metadata_index` to second position in Available Tables (right after `index`) to surface it alongside the primary index
- Moved `prior_versions_index` to last position in Available Tables; updated description to clarify it contains only removed/superseded series and should not be queried for current data
- Added explicit Best Practices rule prohibiting web search for IDC data content questions; idc-index DuckDB queries are always authoritative — web sources are stale
- Removed "Loaded" column from Available Tables and replaced with an unconditional rule: always call `client.fetch_index("table_name")` before querying any table; `fetch_index()` is idempotent for all tables including auto-loaded ones, so no exceptions are needed

## [1.6.1] - 2026-05-08

### Added

- `series_init_idc_version` and `series_revised_idc_version` columns in primary `index` table (idc-index-data 24.1.0): expose the IDC version when each series was first added and last revised, enabling version-aware filtering
- `version_metadata_index` table: maps each IDC version number to its release timestamp; requires `client.fetch_index("version_metadata_index")`
- Tests for new index columns and `version_metadata_index` (61 total, up from 55)

### Changed

- Updated to idc-index 0.12.2 (idc-index-data 24.1.0); IDC data version remains v24
- `analysis_results_index` column renames (idc-index-data 24.1.0): `Updated` → `updated`, `Description` → `description`

## [1.6.0] - 2026-05-07

### Added

- `tests/test_bq_snippets.py`: BigQuery snippet validation using `bq query --dry_run` — 33 tests covering all SQL examples in `references/bigquery_guide.md` (dicom_all, original_collections_metadata, segmentations, quantitative_measurements, qualitative_measurements, private elements, and clinical tables); skips automatically when `bq` CLI is unavailable or unauthenticated

### Security

- Fixed auto-upgrade subprocess call to pin `idc-index` to `REQUIRED_VERSION` (was `"idc-index"`, now `f"idc-index=={REQUIRED_VERSION}"`), ensuring the installed version always matches the tested version declared in the frontmatter
- Added network access transparency note to Overview documenting expected external endpoints (GCS, S3, BigQuery, DICOMweb proxy, Google Healthcare API) and clarifying that no credentials or environment variables are accessed by the skill
- Added tested-with version comment to optional dependency install block (`pandas>=1.5, numpy>=1.23, pydicom>=2.3`)

### Changed

- Updated frontmatter description to be directive about skill triggering: now explicitly instructs invocation for IDC-related queries even without the word "IDC" in the prompt
- Extracted "Batch Processing and Filtering" (section 6) from SKILL.md to `references/use_cases.md` (Use Case 5); replaced inline code block with a 2-sentence summary and pointer
- Extracted "Integration with Analysis Pipelines" (section 9) from SKILL.md to `references/use_cases.md` (Use Case 6); replaced inline pydicom/SimpleITK code blocks with a 2-sentence summary and pointer
- SKILL.md reduced from 865 → 775 lines (−90 lines); `references/use_cases.md` expanded from 187 → 278 lines
- Updated to idc-index 0.12.1 (idc-index-data 24.0.4, IDC data version v24)
- IDC v24 adds 15 new collections (161 → 176), ~39K new series, ~4 TB new data (99.27 TB total, 85,682 cases)
- Updated `collections_index` column names to snake_case (idc-index-data 24.0.0 breaking change):
  `CancerTypes` → `cancer_types`, `TumorLocations` → `tumor_locations`,
  `Subjects` → `subjects`, `Species` → `species`, `Sources` → `sources`,
  `SupportingData` → `supporting_data`, `Program` → `program_id`
- Updated `analysis_results_index` column names to snake_case (idc-index-data 24.0.4 breaking change):
  `Subjects` → `subjects`, `Collections` → `collections`, `Modalities` → `modalities`

## [1.5.0] - 2026-04-08

### Added

- `volume_geometry_index` table documentation: 3D geometry validation for single-frame CT, MR, and PT series; boolean checks (orientation, spacing, dimensions, slice positions) and composite `regularly_spaced_3d_volume` flag; join via `SeriesInstanceUID`
- `rtstruct_index` table documentation: RT Structure Set metadata (total ROIs, ROI names, generation algorithms, interpreted types, referenced image series UID); join via `SeriesInstanceUID`
- New reference guide `references/parquet_access_guide.md`: direct DuckDB queries against public GCS Parquet files without installing idc-index; URL pattern, available files, and query examples for main index, `volume_geometry_index`, and `rtstruct_index`
- SQL patterns for `volume_geometry_index` and `rtstruct_index` in `references/sql_patterns.md`
- Detailed documentation for BigQuery-only derived tables in `references/bigquery_guide.md`:
  - `segmentations`: per-segment anatomy with full schema, column descriptions, and queries for discovering structures, filtering by coded concept, and linking to SR measurements; note on gap vs `seg_index` in idc-index
  - `quantitative_measurements`: radiomics and clinical numeric measurements from DICOM SR TID1500 (volume, diameter, shape descriptors, texture, intensity statistics); full schema with column descriptions and query examples
  - `qualitative_measurements`: coded assessments from DICOM SR TID1500 (malignancy rating, calcification, texture, margin); full schema with column descriptions and query examples
  - `measurement_groups`: parent grouping table for SR measurements
  - Combined example joining all three derived tables for LIDC-IDRI nodule analysis (malignancy + volume + diameter)
- SKILL.md section 7 now explicitly lists per-segment anatomy search, quantitative SR measurements, and qualitative SR measurements as BigQuery-only use cases with no idc-index equivalent

### Changed

- Updated to idc-index 0.11.14 (idc-index-data 23.10.1)
- Added `SOPClassUID` and `TransferSyntaxUID` columns to Key Columns Reference in `references/index_tables_guide.md`
- Added Direct Parquet Access entry to Data Access Options table and pointer in SKILL.md
- Added `parquet_access_guide.md` to Quick Navigation table in SKILL.md

## [1.4.0] - 2026-03-04

### Added

- New "Identifying Tumor vs Normal Slides" section in digital pathology guide with two approaches:
  - Structured DICOM tissue type via `primaryAnatomicStructureModifier_CodeMeaning` (works across all SM collections)
  - TCGA barcode parsing via `ContainerIdentifier` (TCGA collections only, catches metastatic edge cases)
- TCGA-BRCA worked examples showing tumor vs normal slide counts
- Documentation references to GDC TCGA barcode format and sample type codes
- Specimen preparation query examples: filtering by staining (H&E), embedding medium (FFPE vs frozen), and fixative, with note about array column syntax (`array_to_string`, `list_contains`)
- "Finding Pre-Computed Analysis Results" section: discovering derived datasets (nuclei segmentations, TIL maps) via `analysis_results_index`, with example joining annotations back to source slides
- Note about per-annotation measurements in DICOM ANN objects (extractable via highdicom after download), with link to [microscopy_dicom_ann_intro](https://github.com/ImagingDataCommons/IDC-Tutorials/blob/master/notebooks/pathomics/microscopy_dicom_ann_intro.ipynb) tutorial

### Changed

- Updated to idc-index 0.11.10 (adds `ContainerIdentifier` column to `sm_index`)
- Updated `sm_index` table description to reflect newly available columns (container/slide ID, tissue type, anatomic structure, diagnosis)

## [1.3.1] - 2026-02-11

### Added

- Automatic idc-index package version check with upgrade prompt before any queries
- Version check compares installed version against `metadata.idc-index` in frontmatter and triggers `pip install --upgrade` when outdated

### Fixed

- Prevents "table not found" errors when using newer index tables (e.g., `contrast_index`) with older idc-index versions

## [1.3.0] - 2026-02-10

### Added

- Digital pathology reference guide (`references/digital_pathology_guide.md`) with SM, ANN, and SEG query patterns, join examples, and pathology tool recommendations
- `seg_index` coverage in digital pathology guide with cross-domain clarification (SEG used for both radiology and pathology) and query for finding pathology-specific segmentations
- `AnnotationGroupLabel` filtering examples for finding annotation groups by name
- SM + ANN cross-reference queries showing how to find annotations on slide microscopy images
- Index discovery guidance before BigQuery section to ensure all local indices are checked first
- Documentation for new `ann_index` and `ann_group_index` tables (Microscopy Bulk Simple Annotations)
- Example queries for annotation series and annotation group metadata
- Explanation of downloaded DICOM file naming convention (`<crdc_instance_uuid>.dcm`)
- New reference guides extracted from SKILL.md:
  - `references/index_tables_guide.md` - Table schemas, DataFrame access, join column reference
  - `references/sql_patterns.md` - Quick-reference SQL patterns for common queries
  - `references/use_cases.md` - End-to-end workflow examples
- Quick Navigation section in SKILL.md with decision triggers for when to load each reference
- `idc-data-version` field in frontmatter metadata
- Documentation for new `contrast_index` table (contrast bolus metadata for CT, MR, PT, XA, RF series)

### Changed

- Updated to idc-index 0.11.9 (IDC data version v23)
- Reduced SKILL.md from 1,245 to 825 lines by extracting secondary content to reference files
- Core Capabilities sections remain inline to ensure correct API pattern usage
- Refactored detailed SM/ANN content from SKILL.md into `references/digital_pathology_guide.md`, keeping brief summaries with pointers in main skill
- Made IDC version (v23) more prominent in SKILL.md with verification guidance to prevent responses using older versions
- Clarified distinction between `index_tables_guide.md` (structure/access) and `sql_patterns.md` (query examples)

## [1.2.0] - 2026-02-04

### Added

- Clinical data reference guide for navigating tabular data accompanying images
- Detailed patterns for mapping coded values (option_code to option_description)
- Examples for joining clinical data with imaging data via dicom_patient_id
- Expanded BigQuery guide with comprehensive clinical data coverage (metadata tables, cross-collection queries)
- Private DICOM elements documentation in BigQuery guide covering vendor-specific tags (e.g., diffusion b-values)
- Query patterns for discovering, accessing, and filtering by private tags in the OtherElements column

## [1.1.0] - 2026-02-02

### Added

- CLI reference guide for idc-index command-line tools
- Cloud storage reference guide explaining bucket organization and direct access via s5cmd
- GitHub Actions workflow for syncing skill updates to claude-scientific-skills repository

### Fixed

- Moved version field from top-level frontmatter to metadata section for compatibility
- Corrected s5cmd command-line syntax in cloud storage guide
- Clarified caveat about retracted data in DICOMweb guide

### Changed

- Updated DICOMweb reference to explain differences between the two available endpoints

## [1.0.0] - 2026-01-31

### Added

- Core IDC data model documentation with index tables reference
- Query and download workflows using idc-index Python package
- BigQuery integration guide for advanced queries
- DICOMweb API guide for programmatic access
- Visualization integration with IDC Portal and OHIF viewer
- License checking and citation generation examples
- SQL query patterns for common use cases
- DICOM metadata guidance and best practices
