"""
Regression tests for all queries and code snippets documented in the Imaging Data Commons Skill.

Covers: SKILL.md, references/sql_patterns.md, references/index_tables_guide.md,
        references/clinical_data_guide.md, references/use_cases.md,
        references/digital_pathology_guide.md, references/parquet_access_guide.md

Excluded (require auth or network I/O beyond metadata):
  - Actual DICOM downloads
  - DICOMweb endpoints
  - Direct S3/GCS access to DICOM objects (the public Parquet metadata
    artifacts used by parquet_access_guide.md are covered)
  - pydicom / SimpleITK integration (no downloaded files)

BigQuery snippets are covered separately in test_bq_snippets.py (uses bq CLI dry-run).
"""

import os
import pathlib
import re
import sys

import duckdb
import pandas as pd
import pytest
import idc_index
from idc_index import IDCClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_version  # noqa: E402


# ---------------------------------------------------------------------------
# Shared client fixture – one per test session to avoid re-downloading indices
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def client():
    return IDCClient()


@pytest.fixture(scope="session")
def client_with_all_indices(client):
    """Client with every on-demand index pre-fetched."""
    for table in [
        "collections_index",
        "analysis_results_index",
        "clinical_index",
        "sm_index",
        "seg_index",
        "ann_index",
        "ann_group_index",
        "contrast_index",
        "volume_geometry_index",
        "rtstruct_index",
        "version_metadata_index",
    ]:
        client.fetch_index(table)
    return client


# ===========================================================================
# SKILL.md – Version and setup
# ===========================================================================

class TestVersionAndSetup:
    """SKILL.md: version check and IDC data version.

    The version-tracking columns and the version_metadata_index join are
    described under "Querying Metadata with SQL" in SKILL.md; the full
    "what's new in vX" queries live in sql_patterns.md.
    """

    def test_package_version_meets_minimum(self):
        # The rest of check_version.py — parsing, install instructions, exit codes — is
        # covered offline in test_check_version.py; this needs the package installed.
        assert (
            check_version.parse_version(idc_index.__version__)
            >= check_version.parse_version(check_version.MIN_VERSION)
        ), f"idc-index {idc_index.__version__} < pinned minimum {check_version.MIN_VERSION}"

    def test_idc_data_version_matches_frontmatter(self, client):
        """The installed index must serve the release SKILL.md claims to document.

        Reading the frontmatter rather than hardcoding the version means a data
        release bumps one place (SKILL.md) instead of silently leaving the docs
        describing an older release than the pinned idc-index actually serves.
        """
        skill = pathlib.Path(__file__).resolve().parents[1] / "SKILL.md"
        declared = re.search(
            r'^  idc-data-version:\s*"?(v\d+)"?', skill.read_text(), re.M
        )
        assert declared, "SKILL.md frontmatter has no idc-data-version"
        assert client.get_idc_version() == declared.group(1)

    def test_series_version_columns_present(self, client):
        cols = client.index.columns.tolist()
        assert "series_init_idc_version" in cols
        assert "series_revised_idc_version" in cols

    def test_version_metadata_index_available(self, client):
        assert "version_metadata_index" in client.indices_overview
        assert client.indices_overview["version_metadata_index"]["installed"]

    def test_version_metadata_index_query(self, client_with_all_indices):
        df = client_with_all_indices.sql_query(
            "SELECT idc_version, version_timestamp FROM version_metadata_index ORDER BY idc_version"
        )
        assert len(df) > 0
        assert "idc_version" in df.columns
        assert "version_timestamp" in df.columns

    def test_series_version_columns_query(self, client):
        df = client.sql_query("""
            SELECT SeriesInstanceUID, series_init_idc_version, series_revised_idc_version
            FROM index
            WHERE series_init_idc_version IS NOT NULL
            LIMIT 10
        """)
        assert len(df) > 0

    def test_join_index_with_version_metadata(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.SeriesInstanceUID, i.series_init_idc_version, v.version_timestamp
            FROM index i
            JOIN version_metadata_index v ON i.series_init_idc_version = v.idc_version
            LIMIT 5
        """)
        assert len(df) > 0
        assert "version_timestamp" in df.columns


# ===========================================================================
# SKILL.md – Overall statistics
# ===========================================================================

class TestOverallStats:
    """SKILL.md: data statistics snippet."""

    def test_stats_query(self, client):
        df = client.sql_query("""
            SELECT
                COUNT(DISTINCT collection_id) as collections,
                COUNT(DISTINCT analysis_result_id) as analysis_results,
                COUNT(DISTINCT PatientID) as patients,
                COUNT(DISTINCT StudyInstanceUID) as studies,
                COUNT(DISTINCT SeriesInstanceUID) as series,
                SUM(instanceCount) as instances,
                SUM(series_size_MB)/1000000 as size_TB
            FROM index
        """)
        assert len(df) == 1
        row = df.iloc[0]
        assert row["collections"] > 0
        assert row["series"] > 0


# ===========================================================================
# SKILL.md – Data discovery
# ===========================================================================

class TestDataDiscovery:
    """SKILL.md: Data Discovery and Exploration."""

    def test_collections_summary(self, client):
        df = client.sql_query("""
            SELECT
              collection_id,
              COUNT(DISTINCT PatientID) as patients,
              COUNT(DISTINCT SeriesInstanceUID) as series,
              SUM(series_size_MB) as size_mb
            FROM index
            GROUP BY collection_id
            ORDER BY patients DESC
        """)
        assert len(df) > 0
        assert "collection_id" in df.columns

    def test_collections_index(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT collection_id, cancer_types, tumor_locations, species, subjects, supporting_data
            FROM collections_index
        """)
        assert len(df) > 0

    def test_analysis_results_index(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT analysis_result_id, analysis_result_title, subjects, collections, modalities
            FROM analysis_results_index
        """)
        assert len(df) > 0

    def test_analysis_results_index_column_names(self, client_with_all_indices):
        cols = client_with_all_indices.analysis_results_index.columns.tolist()
        for expected in ("updated", "description"):
            assert expected in cols, f"Expected lowercase column '{expected}' in analysis_results_index"
        assert "Updated" not in cols
        assert "Description" not in cols


# ===========================================================================
# SKILL.md – SQL queries
# ===========================================================================

class TestSQLQueries:
    """SKILL.md: Querying Metadata with SQL."""

    def test_modalities_with_counts(self, client):
        df = client.sql_query("""
            SELECT DISTINCT Modality, COUNT(*) as series_count
            FROM index
            GROUP BY Modality
            ORDER BY series_count DESC
        """)
        assert len(df) > 0
        assert "CT" in df["Modality"].tolist()

    # SKILL.md describes narrowing a filter-value query by another column in
    # prose and defers the variants to sql_patterns.md; this covers that claim.
    def test_body_parts_for_mr(self, client):
        df = client.sql_query("""
            SELECT DISTINCT BodyPartExamined, COUNT(*) as series_count
            FROM index
            WHERE Modality = 'MR' AND BodyPartExamined IS NOT NULL
            GROUP BY BodyPartExamined
            ORDER BY series_count DESC
            LIMIT 20
        """)
        assert len(df) > 0

    def test_breast_mri_query(self, client):
        df = client.sql_query("""
            SELECT
              collection_id, PatientID, SeriesInstanceUID,
              Modality, SeriesDescription, license_short_name
            FROM index
            WHERE Modality = 'MR' AND BodyPartExamined = 'BREAST'
            LIMIT 20
        """)
        assert df is not None

    def test_join_collections_index_breast(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, i.PatientID, i.SeriesInstanceUID, i.Modality
            FROM index i
            JOIN collections_index c ON i.collection_id = c.collection_id
            WHERE c.cancer_types LIKE '%Breast%' AND i.Modality = 'MR'
            LIMIT 20
        """)
        assert df is not None


# ===========================================================================
# SKILL.md – Licenses and citations
# ===========================================================================

class TestLicensesAndCitations:
    """SKILL.md: Understanding and Checking Licenses; Generating Citations."""

    def test_license_query(self, client):
        df = client.sql_query("""
            SELECT DISTINCT
              collection_id,
              license_short_name,
              COUNT(DISTINCT SeriesInstanceUID) as series_count
            FROM index
            GROUP BY collection_id, license_short_name
            ORDER BY collection_id
        """)
        assert len(df) > 0
        assert "license_short_name" in df.columns

    def test_citations_apa(self, client):
        citations = client.citations_from_selection(collection_id="rider_pilot")
        assert len(citations) > 0

    def test_citations_bibtex(self, client):
        citations = client.citations_from_selection(
            collection_id="rider_pilot",
            citation_format=IDCClient.CITATION_FORMAT_BIBTEX,
        )
        assert len(citations) > 0

    def test_citations_from_series(self, client):
        df = client.sql_query(
            "SELECT SeriesInstanceUID FROM index WHERE collection_id = 'tcga_luad' LIMIT 5"
        )
        citations = client.citations_from_selection(
            seriesInstanceUID=list(df["SeriesInstanceUID"].values)
        )
        assert citations is not None


# ===========================================================================
# SKILL.md – Batch processing and manifest generation
# ===========================================================================

class TestBatchAndManifest:
    """Batch selection (use_cases.md) and manifest generation (SKILL.md:
    Command-Line Download, cli_guide.md)."""

    def test_batch_filter_query(self, client):
        df = client.sql_query("""
            SELECT SeriesInstanceUID, PatientID, collection_id, ManufacturerModelName
            FROM index
            WHERE Modality = 'CT'
              AND BodyPartExamined = 'CHEST'
              AND Manufacturer = 'GE MEDICAL SYSTEMS'
              AND license_short_name = 'CC BY 4.0'
            LIMIT 100
        """)
        assert df is not None

    def test_manifest_generation_query(self, client):
        df = client.sql_query("""
            SELECT series_aws_url
            FROM index
            WHERE collection_id = 'rider_pilot' AND Modality = 'CT'
        """)
        assert len(df) > 0
        assert "series_aws_url" in df.columns


# ===========================================================================
# SKILL.md – Viewer URLs
# ===========================================================================

class TestViewerURLs:
    """SKILL.md: Visualizing IDC Images."""

    @pytest.fixture(scope="class")
    def rider_pilot_row(self, client):
        df = client.sql_query("""
            SELECT SeriesInstanceUID, StudyInstanceUID
            FROM index
            WHERE collection_id = 'rider_pilot' AND Modality = 'CT'
            LIMIT 1
        """)
        return df.iloc[0]

    def test_viewer_url_series(self, client, rider_pilot_row):
        url = client.get_viewer_URL(seriesInstanceUID=rider_pilot_row["SeriesInstanceUID"])
        assert url.startswith("http")

    def test_viewer_url_study(self, client, rider_pilot_row):
        url = client.get_viewer_URL(studyInstanceUID=rider_pilot_row["StudyInstanceUID"])
        assert url.startswith("http")


# ===========================================================================
# index_tables_guide.md
# ===========================================================================

class TestIndexTablesGuide:
    """references/index_tables_guide.md."""

    def test_primary_index_sql(self, client):
        df = client.sql_query("SELECT * FROM index WHERE Modality = 'CT' LIMIT 10")
        assert len(df) == 10

    def test_collections_index_sql(self, client_with_all_indices):
        df = client_with_all_indices.sql_query(
            "SELECT collection_id, cancer_types, tumor_locations FROM collections_index"
        )
        assert len(df) > 0

    def test_analysis_results_sql(self, client_with_all_indices):
        df = client_with_all_indices.sql_query(
            "SELECT * FROM analysis_results_index LIMIT 5"
        )
        assert len(df) > 0

    def test_primary_index_dataframe(self, client):
        df = client.index
        assert df is not None and len(df) > 0

    def test_sm_index_dataframe(self, client_with_all_indices):
        sm_df = client_with_all_indices.sm_index
        assert sm_df is not None

    def test_indices_overview_structure(self, client):
        for name, info in client.indices_overview.items():
            assert "installed" in info, f"'installed' missing for {name}"
            assert "description" in info, f"'description' missing for {name}"

    def test_schema_discovery_via_indices_overview(self, client):
        schema = client.indices_overview["index"]["schema"]
        assert "table_description" in schema
        assert "columns" in schema
        assert len(schema["columns"]) > 0

    def test_get_index_schema(self, client):
        schema = client.get_index_schema("index")
        assert "table_description" in schema
        assert "columns" in schema


# ===========================================================================
# sql_patterns.md – Filter discovery
# ===========================================================================

class TestFilterDiscovery:
    """references/sql_patterns.md – Discover Available Filter Values."""

    def test_distinct_modalities(self, client):
        df = client.sql_query("SELECT DISTINCT Modality FROM index")
        assert len(df) > 0

    def test_body_parts_ct(self, client):
        df = client.sql_query("""
            SELECT DISTINCT BodyPartExamined, COUNT(*) as n
            FROM index WHERE Modality = 'CT' AND BodyPartExamined IS NOT NULL
            GROUP BY BodyPartExamined ORDER BY n DESC
        """)
        assert len(df) > 0

    def test_manufacturers_mr(self, client):
        df = client.sql_query("""
            SELECT DISTINCT Manufacturer, COUNT(*) as n
            FROM index WHERE Modality = 'MR'
            GROUP BY Manufacturer ORDER BY n DESC
        """)
        assert len(df) > 0


# ===========================================================================
# sql_patterns.md – Annotations and segmentations
# ===========================================================================

class TestAnnotationsAndSegmentations:
    """references/sql_patterns.md – Find Annotations and Segmentations."""

    def test_seg_rtstruct_by_modality(self, client):
        df = client.sql_query("""
            SELECT collection_id, Modality, COUNT(*) as series_count
            FROM index
            WHERE Modality IN ('SEG', 'RTSTRUCT')
            GROUP BY collection_id, Modality
            ORDER BY series_count DESC
        """)
        assert df is not None

    def test_segmentations_tcga_luad(self, client):
        df = client.sql_query("""
            SELECT SeriesInstanceUID, SeriesDescription, analysis_result_id
            FROM index
            WHERE collection_id = 'tcga_luad' AND Modality = 'SEG'
        """)
        assert df is not None

    def test_analysis_results_for_tcga_luad(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT analysis_result_id, analysis_result_title
            FROM analysis_results_index
            WHERE collections LIKE '%tcga_luad%'
        """)
        assert df is not None

    def test_seg_index_by_algorithm(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT AlgorithmName, AlgorithmType, COUNT(*) as seg_count
            FROM seg_index
            WHERE AlgorithmName IS NOT NULL
            GROUP BY AlgorithmName, AlgorithmType
            ORDER BY seg_count DESC
            LIMIT 10
        """)
        assert df is not None

    def test_seg_join_chest_ct(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT
                s.SeriesInstanceUID as seg_series,
                s.AlgorithmName,
                s.total_segments,
                s.segmented_SeriesInstanceUID as source_series
            FROM seg_index s
            JOIN index src ON s.segmented_SeriesInstanceUID = src.SeriesInstanceUID
            WHERE src.Modality = 'CT' AND src.BodyPartExamined = 'CHEST'
            LIMIT 10
        """)
        assert df is not None

    def test_totalsegmentator_query(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT
                seg_info.collection_id,
                COUNT(DISTINCT s.SeriesInstanceUID) as seg_count,
                SUM(s.total_segments) as total_segments
            FROM seg_index s
            JOIN index seg_info ON s.SeriesInstanceUID = seg_info.SeriesInstanceUID
            WHERE s.AlgorithmName LIKE '%TotalSegmentator%'
            GROUP BY seg_info.collection_id
            ORDER BY seg_count DESC
        """)
        assert df is not None

    def test_ann_group_index_query(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT g.AnnotationGroupLabel, g.GraphicType, g.NumberOfAnnotations, i.collection_id
            FROM ann_group_index g
            JOIN ann_index a ON g.SeriesInstanceUID = a.SeriesInstanceUID
            JOIN index i ON a.SeriesInstanceUID = i.SeriesInstanceUID
            WHERE g.AlgorithmName IS NOT NULL
            LIMIT 10
        """)
        assert df is not None


# ===========================================================================
# sql_patterns.md – Size estimation
# ===========================================================================

class TestSizeEstimation:
    """references/sql_patterns.md – Estimate Download Size."""

    def test_size_estimation_nlst(self, client):
        df = client.sql_query("""
            SELECT SUM(series_size_MB) as total_mb, COUNT(*) as series_count
            FROM index
            WHERE collection_id = 'nlst' AND Modality = 'CT'
        """)
        assert len(df) == 1
        assert df.iloc[0]["series_count"] > 0


# ===========================================================================
# sql_patterns.md – Volume geometry and RT Structure Sets
# ===========================================================================

class TestVolumeGeometryAndRTSTRUCT:
    """references/sql_patterns.md – Volume Geometry Validation and RT Structure Sets."""

    def test_volume_geometry_valid_ct(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, i.SeriesInstanceUID, i.BodyPartExamined,
                   v.obliquity_degrees
            FROM index i
            JOIN volume_geometry_index v ON i.SeriesInstanceUID = v.SeriesInstanceUID
            WHERE i.Modality = 'CT'
              AND v.regularly_spaced_3d_volume = TRUE
            LIMIT 10
        """)
        assert df is not None

    def test_volume_geometry_fraction_per_collection(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id,
                   COUNT(*) as total_ct,
                   SUM(CASE WHEN v.regularly_spaced_3d_volume THEN 1 ELSE 0 END) as valid_3d,
                   ROUND(100.0 * SUM(CASE WHEN v.regularly_spaced_3d_volume THEN 1 ELSE 0 END)
                         / COUNT(*), 1) as pct_valid
            FROM index i
            JOIN volume_geometry_index v ON i.SeriesInstanceUID = v.SeriesInstanceUID
            WHERE i.Modality = 'CT'
            GROUP BY i.collection_id
            ORDER BY total_ct DESC
            LIMIT 10
        """)
        assert len(df) > 0

    def test_rtstruct_index_query(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, i.SeriesInstanceUID,
                   r.total_rois, r.ROINames, r.RTROIInterpretedTypes,
                   r.referenced_SeriesInstanceUID
            FROM index i
            JOIN rtstruct_index r ON i.SeriesInstanceUID = r.SeriesInstanceUID
            LIMIT 10
        """)
        assert df is not None

    def test_rtstruct_per_collection(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id,
                   COUNT(*) as rtstruct_series,
                   ROUND(AVG(r.total_rois), 1) as avg_rois
            FROM index i
            JOIN rtstruct_index r ON i.SeriesInstanceUID = r.SeriesInstanceUID
            GROUP BY i.collection_id
            ORDER BY rtstruct_series DESC
            LIMIT 10
        """)
        assert df is not None

    def test_rtstruct_source_ct(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT r.SeriesInstanceUID as rtstruct_uid,
                   r.total_rois, r.ROINames,
                   src.SeriesInstanceUID as source_ct_uid,
                   src.collection_id, src.BodyPartExamined
            FROM rtstruct_index r
            JOIN index src ON r.referenced_SeriesInstanceUID = src.SeriesInstanceUID
            LIMIT 10
        """)
        assert df is not None


# ===========================================================================
# sql_patterns.md – Clinical data link and slide microscopy
# ===========================================================================

class TestClinicalLinkAndSM:
    """references/sql_patterns.md – Link to Clinical Data and Slide Microscopy."""

    def test_clinical_index_summary(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT collection_id, table_name, COUNT(DISTINCT column_label) as columns
            FROM clinical_index
            GROUP BY collection_id, table_name
            ORDER BY collection_id
        """)
        assert len(df) > 0

    def test_sm_index_join(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, COUNT(*) as sm_series
            FROM index i
            JOIN sm_index s ON i.SeriesInstanceUID = s.SeriesInstanceUID
            GROUP BY i.collection_id
            ORDER BY sm_series DESC
            LIMIT 10
        """)
        assert df is not None

    def test_contrast_index_join(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.SeriesInstanceUID, i.Modality, i.collection_id
            FROM index i
            JOIN contrast_index c ON i.SeriesInstanceUID = c.SeriesInstanceUID
            LIMIT 10
        """)
        assert df is not None


# ===========================================================================
# clinical_data_guide.md
# ===========================================================================

class TestClinicalDataGuide:
    """references/clinical_data_guide.md."""

    def test_clinical_index_columns(self, client_with_all_indices):
        cols = client_with_all_indices.clinical_index.columns.tolist()
        for expected in ("collection_id", "short_table_name", "column", "column_label"):
            assert expected in cols, f"Expected column '{expected}' in clinical_index"

    def test_collections_with_clinical_data(self, client_with_all_indices):
        collections = client_with_all_indices.clinical_index["collection_id"].unique().tolist()
        assert len(collections) > 0

    def test_nlst_has_clinical_columns(self, client_with_all_indices):
        nlst_rows = client_with_all_indices.clinical_index[
            client_with_all_indices.clinical_index["collection_id"] == "nlst"
        ]
        assert len(nlst_rows) > 0

    def test_search_stage_attributes(self, client_with_all_indices):
        stage_attrs = client_with_all_indices.clinical_index[
            client_with_all_indices.clinical_index["column_label"].str.contains(
                "[Ss]tage", na=False
            )
        ]
        assert len(stage_attrs) > 0

    def test_load_clinical_table_nlst_canc(self, client_with_all_indices):
        df = client_with_all_indices.get_clinical_table("nlst_canc")
        assert df is not None
        assert len(df) > 0
        assert "dicom_patient_id" in df.columns

    def test_coded_values_mapping(self, client_with_all_indices):
        nlst_rows = client_with_all_indices.clinical_index[
            client_with_all_indices.clinical_index["collection_id"] == "nlst"
        ]
        stag_rows = nlst_rows[nlst_rows["column"] == "clinical_stag"]
        if len(stag_rows) == 0:
            pytest.skip("clinical_stag column not present in this idc-index version")
        values = stag_rows["values"].values[0]
        mapping = {item["option_code"]: item["option_description"] for item in values}
        assert len(mapping) > 0

    def test_join_clinical_imaging_pandas(self, client_with_all_indices):
        nlst_canc = client_with_all_indices.get_clinical_table("nlst_canc")
        nlst_imaging = client_with_all_indices.index[
            (client_with_all_indices.index["collection_id"] == "nlst")
            & (client_with_all_indices.index["Modality"] == "CT")
        ]
        merged = pd.merge(
            nlst_imaging[["PatientID", "StudyInstanceUID"]].drop_duplicates(),
            nlst_canc[["dicom_patient_id"]],
            left_on="PatientID",
            right_on="dicom_patient_id",
            how="inner",
        )
        assert len(merged) > 0

    def test_join_clinical_imaging_sql(self, client_with_all_indices):
        # Clinical tables loaded via get_clinical_table() are not auto-registered
        # in DuckDB. Register manually before joining in SQL.
        nlst_canc_df = client_with_all_indices.get_clinical_table("nlst_canc")
        client_with_all_indices._duckdb_conn.register("nlst_canc", nlst_canc_df)
        df = client_with_all_indices.sql_query("""
            SELECT index.PatientID, index.StudyInstanceUID, index.Modality
            FROM index
            JOIN nlst_canc ON index.PatientID = nlst_canc.dicom_patient_id
            WHERE index.collection_id = 'nlst' AND index.Modality = 'CT'
        """)
        assert len(df) > 0

    def test_chemo_collections(self, client_with_all_indices):
        chemo = client_with_all_indices.clinical_index[
            client_with_all_indices.clinical_index["column_label"].str.contains(
                "[Cc]hemotherapy", na=False
            )
        ]["collection_id"].unique()
        assert chemo is not None  # may be empty – just verify it runs

    def test_patient_overlap_nlst(self, client_with_all_indices):
        nlst_canc = client_with_all_indices.get_clinical_table("nlst_canc")
        imaging_patients = set(
            client_with_all_indices.index[
                client_with_all_indices.index["collection_id"] == "nlst"
            ]["PatientID"].unique()
        )
        clinical_patients = set(nlst_canc["dicom_patient_id"].unique())
        overlap = imaging_patients & clinical_patients
        assert len(overlap) > 0


# ===========================================================================
# use_cases.md
# ===========================================================================

class TestUseCases:
    """references/use_cases.md – end-to-end workflows.

    Only the selection queries are covered: every use case ends in
    download_from_selection() or pydicom/SimpleITK processing of downloaded
    files, both excluded per the module docstring. Use Case 5's query is
    identical to TestBatchAndManifest::test_batch_filter_query.
    """

    def test_uc1_nlst_lung_ct_training_set(self, client):
        df = client.sql_query("""
            SELECT PatientID, SeriesInstanceUID, SeriesDescription
            FROM index
            WHERE collection_id = 'nlst'
              AND Modality = 'CT'
              AND BodyPartExamined = 'CHEST'
              AND license_short_name = 'CC BY 4.0'
            ORDER BY PatientID
            LIMIT 100
        """)
        assert len(df) == 100
        assert df["PatientID"].nunique() > 0

    @pytest.fixture(scope="class")
    def brain_mr_manufacturers(self, client):
        return client.sql_query("""
            SELECT Manufacturer, ManufacturerModelName,
                   COUNT(DISTINCT SeriesInstanceUID) as num_series,
                   COUNT(DISTINCT PatientID) as num_patients
            FROM index
            WHERE Modality = 'MR' AND BodyPartExamined LIKE '%BRAIN%'
            GROUP BY Manufacturer, ManufacturerModelName
            HAVING num_series >= 10
            ORDER BY num_series DESC
        """)

    def test_uc2_brain_mr_by_manufacturer(self, brain_mr_manufacturers):
        assert len(brain_mr_manufacturers) > 0
        assert (brain_mr_manufacturers["num_series"] >= 10).all()

    def test_uc2_sample_per_manufacturer(self, client, brain_mr_manufacturers):
        # The guide interpolates each row into a follow-up query.
        row = brain_mr_manufacturers.iloc[0]
        df = client.sql_query(f"""
            SELECT SeriesInstanceUID
            FROM index
            WHERE Manufacturer = '{row['Manufacturer']}'
              AND ManufacturerModelName = '{row['ManufacturerModelName']}'
              AND Modality = 'MR'
              AND BodyPartExamined LIKE '%BRAIN%'
            LIMIT 5
        """)
        assert len(df) > 0

    def test_uc3_preview_before_download(self, client):
        df = client.sql_query("""
            SELECT SeriesInstanceUID, PatientID, SeriesDescription
            FROM index
            WHERE collection_id = 'acrin_nsclc_fdg_pet' AND Modality = 'PT'
            LIMIT 10
        """)
        assert len(df) > 0
        url = client.get_viewer_URL(seriesInstanceUID=df.iloc[0]["SeriesInstanceUID"])
        assert url.startswith("http")

    def test_uc4_license_aware_selection(self, client):
        df = client.sql_query("""
            SELECT SeriesInstanceUID, collection_id, PatientID, Modality
            FROM index
            WHERE license_short_name LIKE 'CC BY%'
              AND license_short_name NOT LIKE '%NC%'
              AND Modality IN ('CT', 'MR')
              AND BodyPartExamined IN ('CHEST', 'BRAIN', 'ABDOMEN')
            LIMIT 200
        """)
        assert len(df) > 0
        assert set(df["Modality"]) <= {"CT", "MR"}


# ===========================================================================
# digital_pathology_guide.md
# ===========================================================================

class TestDigitalPathologyGuide:
    """references/digital_pathology_guide.md."""

    def test_sm_metadata_by_collection(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, COUNT(*) as slides,
                   MIN(s.min_PixelSpacing_2sf) as min_resolution
            FROM sm_index s
            JOIN index i ON s.SeriesInstanceUID = i.SeriesInstanceUID
            GROUP BY i.collection_id
            ORDER BY slides DESC
        """)
        assert len(df) > 0

    def test_sm_objective_lens_power(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, i.PatientID, s.ObjectiveLensPower,
                   s.min_PixelSpacing_2sf
            FROM sm_index s
            JOIN index i ON s.SeriesInstanceUID = i.SeriesInstanceUID
            WHERE s.ObjectiveLensPower >= 40
            ORDER BY s.min_PixelSpacing_2sf
            LIMIT 20
        """)
        assert len(df) > 0

    def test_sm_staining_array_filter(self, client_with_all_indices):
        # Specimen preparation columns are arrays – array_to_string() + LIKE.
        df = client_with_all_indices.sql_query("""
            SELECT i.PatientID,
                   s.staining_usingSubstance_CodeMeaning as staining,
                   s.embeddingMedium_CodeMeaning as embedding,
                   s.tissueFixative_CodeMeaning as fixative
            FROM sm_index s
            JOIN index i ON s.SeriesInstanceUID = i.SeriesInstanceUID
            WHERE i.collection_id = 'tcga_brca'
              AND array_to_string(s.staining_usingSubstance_CodeMeaning, ', ')
                  LIKE '%hematoxylin%'
            LIMIT 10
        """)
        assert len(df) > 0

    def test_sm_embedding_medium_breakdown(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, s.embeddingMedium_CodeMeaning as embedding,
                   COUNT(*) as slide_count
            FROM sm_index s
            JOIN index i ON s.SeriesInstanceUID = i.SeriesInstanceUID
            GROUP BY i.collection_id, embedding
            ORDER BY i.collection_id, slide_count DESC
        """)
        assert len(df) > 0

    def test_tissue_type_values(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT s.primaryAnatomicStructureModifier_CodeMeaning as tissue_type,
                   COUNT(*) as slide_count
            FROM sm_index s
            WHERE s.primaryAnatomicStructureModifier_CodeMeaning IS NOT NULL
            GROUP BY tissue_type
            ORDER BY slide_count DESC
        """)
        assert "Neoplasm, Primary" in set(df["tissue_type"])

    def test_tcga_brca_tissue_breakdown(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT s.primaryAnatomicStructureModifier_CodeMeaning as tissue_type,
                   COUNT(*) as slide_count,
                   COUNT(DISTINCT i.PatientID) as patient_count
            FROM sm_index s
            JOIN index i ON s.SeriesInstanceUID = i.SeriesInstanceUID
            WHERE i.collection_id = 'tcga_brca'
            GROUP BY tissue_type
            ORDER BY slide_count DESC
        """)
        counts = dict(zip(df["tissue_type"], df["slide_count"]))
        # The guide quotes these counts inline – fails if the data release moves them.
        assert counts["Neoplasm, Primary"] == 2704
        assert counts["Normal"] == 399

    def test_tcga_barcode_sample_type(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT SUBSTRING(SPLIT_PART(s.ContainerIdentifier, '-', 4), 1, 2)
                       as sample_type_code,
                   s.primaryAnatomicStructureModifier_CodeMeaning as tissue_type,
                   COUNT(*) as slide_count
            FROM sm_index s
            JOIN index i ON s.SeriesInstanceUID = i.SeriesInstanceUID
            WHERE i.collection_id = 'tcga_brca'
            GROUP BY sample_type_code, tissue_type
            ORDER BY sample_type_code
        """)
        counts = dict(zip(df["sample_type_code"], df["slide_count"]))
        # Guide: 01 -> 2704 tumor, 06 -> 8 metastatic (tissue_type NULL), 11 -> 399 normal.
        assert counts == {"01": 2704, "06": 8, "11": 399}

    def test_ann_series_discovery(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT a.SeriesInstanceUID as ann_series, a.AnnotationCoordinateType,
                   a.referenced_SeriesInstanceUID as source_series
            FROM ann_index a
            LIMIT 10
        """)
        assert len(df) > 0

    def test_ann_group_statistics(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT GraphicType, SUM(NumberOfAnnotations) as total_annotations,
                   COUNT(*) as group_count
            FROM ann_group_index
            GROUP BY GraphicType
            ORDER BY total_annotations DESC
        """)
        assert len(df) > 0

    def test_ann_with_source_slide_context(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, g.GraphicType,
                   g.AnnotationPropertyType_CodeMeaning, g.AlgorithmName,
                   g.NumberOfAnnotations
            FROM ann_group_index g
            JOIN ann_index a ON g.SeriesInstanceUID = a.SeriesInstanceUID
            JOIN index i ON a.referenced_SeriesInstanceUID = i.SeriesInstanceUID
            WHERE g.AlgorithmName IS NOT NULL
            LIMIT 10
        """)
        assert len(df) > 0

    def test_segmentations_on_slide_microscopy(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT seg.SeriesInstanceUID as seg_series, seg.AlgorithmName,
                   seg.total_segments, src.collection_id,
                   src.Modality as source_modality
            FROM seg_index seg
            JOIN index src ON seg.segmented_SeriesInstanceUID = src.SeriesInstanceUID
            WHERE src.Modality = 'SM'
            LIMIT 20
        """)
        assert len(df) > 0
        assert set(df["source_modality"]) == {"SM"}

    def test_pathology_analysis_results(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT ar.analysis_result_id, ar.analysis_result_title, ar.modalities,
                   ar.subjects, ar.collections
            FROM analysis_results_index ar
            WHERE ar.modalities LIKE '%ANN%' OR ar.modalities LIKE '%SEG%'
            ORDER BY ar.subjects DESC
        """)
        assert len(df) > 0

    def test_derived_data_for_collection(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.analysis_result_id, i.PatientID,
                   a.referenced_SeriesInstanceUID as source_slide,
                   g.AnnotationGroupLabel, g.NumberOfAnnotations, g.AlgorithmName
            FROM ann_group_index g
            JOIN ann_index a ON g.SeriesInstanceUID = a.SeriesInstanceUID
            JOIN index i ON a.SeriesInstanceUID = i.SeriesInstanceUID
            WHERE i.collection_id = 'tcga_brca'
            LIMIT 10
        """)
        assert len(df) > 0

    def test_annotation_group_label_filter(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT g.SeriesInstanceUID, g.AnnotationGroupLabel, g.GraphicType,
                   g.NumberOfAnnotations, g.AlgorithmName
            FROM ann_group_index g
            WHERE LOWER(g.AnnotationGroupLabel) LIKE '%blast%'
            ORDER BY g.NumberOfAnnotations DESC
        """)
        assert len(df) > 0

    def test_annotation_label_with_collection_context(self, client_with_all_indices):
        # The guide uses 'your_collection_id'/'keyword' placeholders here.
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, g.AnnotationGroupLabel, g.GraphicType,
                   g.NumberOfAnnotations, g.AnnotationPropertyType_CodeMeaning
            FROM ann_group_index g
            JOIN ann_index a ON g.SeriesInstanceUID = a.SeriesInstanceUID
            JOIN index i ON a.SeriesInstanceUID = i.SeriesInstanceUID
            WHERE i.collection_id = 'tcga_brca'
              AND LOWER(g.AnnotationGroupLabel) LIKE '%nucle%'
            ORDER BY g.NumberOfAnnotations DESC
        """)
        assert len(df) > 0

    def test_sm_ann_cross_reference(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, s.ObjectiveLensPower, g.AnnotationGroupLabel,
                   g.NumberOfAnnotations, g.GraphicType
            FROM ann_group_index g
            JOIN ann_index a ON g.SeriesInstanceUID = a.SeriesInstanceUID
            JOIN sm_index s ON a.referenced_SeriesInstanceUID = s.SeriesInstanceUID
            JOIN index i ON a.SeriesInstanceUID = i.SeriesInstanceUID
            WHERE i.collection_id = 'tcga_brca'
            ORDER BY g.NumberOfAnnotations DESC
            LIMIT 10
        """)
        assert len(df) > 0

    def test_sm_join_pattern(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, i.PatientID, s.ObjectiveLensPower,
                   s.min_PixelSpacing_2sf
            FROM index i
            JOIN sm_index s ON i.SeriesInstanceUID = s.SeriesInstanceUID
            LIMIT 10
        """)
        assert len(df) > 0

    def test_ann_join_pattern(self, client_with_all_indices):
        df = client_with_all_indices.sql_query("""
            SELECT i.collection_id, g.AnnotationGroupLabel, g.GraphicType,
                   g.NumberOfAnnotations,
                   a.referenced_SeriesInstanceUID as source_series
            FROM ann_group_index g
            JOIN ann_index a ON g.SeriesInstanceUID = a.SeriesInstanceUID
            JOIN index i ON a.SeriesInstanceUID = i.SeriesInstanceUID
            LIMIT 10
        """)
        assert len(df) > 0


# ===========================================================================
# parquet_access_guide.md – DuckDB against the public Parquet artifacts
# ===========================================================================

PARQUET_BASE = (
    "https://storage.googleapis.com/idc-index-data-artifacts/current/release_artifacts"
)


class TestParquetAccessGuide:
    """references/parquet_access_guide.md (idc-index not used – DuckDB over HTTPS)."""

    def test_listed_files_exist(self):
        import urllib.request
        for name in [
            "idc_index", "volume_geometry_index", "rtstruct_index", "seg_index",
            "sm_index", "contrast_index", "ann_index", "ann_group_index",
            "collections_index", "analysis_results_index", "clinical_index",
            "ct_index", "mr_index", "pt_index", "prior_versions_index",
            "sm_instance_index", "version_metadata_index",
            "gdc_idc_mapping", "tcia_idc_subset",
        ]:
            url = f"{PARQUET_BASE}/{name}.parquet"
            request = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(request, timeout=30) as response:
                assert response.status == 200, f"{name}.parquet missing at {url}"

    def test_current_resolves_to_installed_data_release(self):
        # The guide states current/ always resolves to the latest data release.
        import idc_index_data
        pinned = (
            "https://storage.googleapis.com/idc-index-data-artifacts/"
            f"{idc_index_data.__version__}/release_artifacts"
        )
        current_rows = duckdb.sql(
            f"SELECT COUNT(*) FROM read_parquet('{PARQUET_BASE}/idc_index.parquet')"
        ).fetchone()[0]
        pinned_rows = duckdb.sql(
            f"SELECT COUNT(*) FROM read_parquet('{pinned}/idc_index.parquet')"
        ).fetchone()[0]
        assert current_rows == pinned_rows

    def test_modality_counts(self):
        df = duckdb.sql(f"""
            SELECT Modality, COUNT(*) as series_count,
                   ROUND(SUM(series_size_MB)/1000, 1) as size_GB
            FROM read_parquet('{PARQUET_BASE}/idc_index.parquet')
            GROUP BY Modality
            ORDER BY series_count DESC
        """).df()
        assert len(df) > 0

    def test_ct_collections_by_size(self):
        df = duckdb.sql(f"""
            SELECT collection_id,
                   COUNT(DISTINCT PatientID) as patients,
                   COUNT(*) as series,
                   ROUND(SUM(series_size_MB)/1000, 1) as size_GB
            FROM read_parquet('{PARQUET_BASE}/idc_index.parquet')
            WHERE Modality = 'CT'
            GROUP BY collection_id
            ORDER BY size_GB DESC
            LIMIT 10
        """).df()
        assert len(df) == 10

    def test_volume_geometry_join(self):
        df = duckdb.sql(f"""
            SELECT i.collection_id, i.SeriesInstanceUID, i.BodyPartExamined,
                   v.obliquity_degrees, v.regularly_spaced_3d_volume
            FROM read_parquet('{PARQUET_BASE}/idc_index.parquet') i
            JOIN read_parquet('{PARQUET_BASE}/volume_geometry_index.parquet') v
                ON i.SeriesInstanceUID = v.SeriesInstanceUID
            WHERE i.Modality = 'CT'
              AND v.regularly_spaced_3d_volume = TRUE
            LIMIT 10
        """).df()
        assert len(df) == 10

    def test_volume_geometry_fraction_per_collection(self):
        df = duckdb.sql(f"""
            SELECT i.collection_id, i.Modality, COUNT(*) as total,
                   SUM(CASE WHEN v.regularly_spaced_3d_volume THEN 1 ELSE 0 END) as valid_3d
            FROM read_parquet('{PARQUET_BASE}/idc_index.parquet') i
            JOIN read_parquet('{PARQUET_BASE}/volume_geometry_index.parquet') v
                ON i.SeriesInstanceUID = v.SeriesInstanceUID
            WHERE i.Modality IN ('CT', 'MR', 'PT')
            GROUP BY i.collection_id, i.Modality
            ORDER BY total DESC
            LIMIT 10
        """).df()
        assert len(df) == 10

    def test_rtstruct_roi_details(self):
        df = duckdb.sql(f"""
            SELECT i.collection_id, i.SeriesInstanceUID, r.total_rois, r.ROINames,
                   r.RTROIInterpretedTypes, r.referenced_SeriesInstanceUID
            FROM read_parquet('{PARQUET_BASE}/idc_index.parquet') i
            JOIN read_parquet('{PARQUET_BASE}/rtstruct_index.parquet') r
                ON i.SeriesInstanceUID = r.SeriesInstanceUID
            WHERE i.Modality = 'RTSTRUCT'
            LIMIT 5
        """).df()
        assert len(df) == 5

    def test_rtstruct_collections(self):
        df = duckdb.sql(f"""
            SELECT i.collection_id, COUNT(*) as rtstruct_series,
                   ROUND(AVG(r.total_rois), 1) as avg_rois_per_struct
            FROM read_parquet('{PARQUET_BASE}/idc_index.parquet') i
            JOIN read_parquet('{PARQUET_BASE}/rtstruct_index.parquet') r
                ON i.SeriesInstanceUID = r.SeriesInstanceUID
            GROUP BY i.collection_id
            ORDER BY rtstruct_series DESC
            LIMIT 10
        """).df()
        assert len(df) == 10


class TestProvenance:
    """references/index_tables_guide.md + sql_patterns.md — provenance, new in IDC v25.

    Guards the two claims the guides make that a reader would otherwise have to
    take on faith: that provenance is reachable by unnesting collections_index,
    and that a NULL struct there is a pointer to analysis_results_index rather
    than missing data.
    """

    PROV_FIELDS = (
        "data_contributor",
        "source_data_provider",
        "deidentification_party",
        "dicom_conversion_by",
    )

    def test_provenance_struct_fields_present(self, client_with_all_indices):
        fields = ", ".join(f"src.provenance.{f}" for f in self.PROV_FIELDS)
        df = client_with_all_indices.sql_query(
            f"SELECT {fields} "
            "FROM (SELECT unnest(sources) AS src FROM collections_index) LIMIT 5"
        )
        assert list(df.columns) == list(self.PROV_FIELDS)

    def test_analysis_results_provenance_fully_populated(self, client_with_all_indices):
        df = client_with_all_indices.sql_query(
            "SELECT COUNT(*) AS total, "
            "COUNT(provenance.data_contributor) AS with_prov "
            "FROM analysis_results_index"
        )
        assert df["total"][0] > 0
        assert df["with_prov"][0] == df["total"][0]

    def test_null_collection_provenance_is_an_analysis_result(self, client_with_all_indices):
        """The guides tell readers to treat NULL as a pointer, not as unknown."""
        df = client_with_all_indices.sql_query("""
            WITH s AS (SELECT unnest(sources) AS src FROM collections_index),
            n AS (SELECT lower(src.source_doi) AS doi FROM s
                  WHERE src.provenance.data_contributor IS NULL)
            SELECT COUNT(*) AS unexplained FROM n
            WHERE doi NOT IN (SELECT lower(source_DOI) FROM analysis_results_index)
        """)
        assert df["unexplained"][0] == 0

    def test_idc_contributed_sources_are_idc_converted(self, client_with_all_indices):
        """SKILL guides state the two coincide; a release that breaks it fails here."""
        df = client_with_all_indices.sql_query("""
            SELECT COUNT(*) AS mismatched
            FROM (SELECT unnest(sources) AS src FROM collections_index)
            WHERE src.provenance.data_contributor = 'IDC'
              AND src.provenance.dicom_conversion_by IS DISTINCT FROM 'IDC'
        """)
        assert df["mismatched"][0] == 0

    def test_series_join_to_source_provenance(self, client_with_all_indices):
        """tcga_brca mixes TCIA-contributed radiology with IDC-converted pathology."""
        df = client_with_all_indices.sql_query("""
            SELECT DISTINCT s.src.provenance.data_contributor AS contributed_by,
                            s.src.provenance.dicom_conversion_by AS converted_by
            FROM index i
            JOIN (SELECT collection_id, unnest(sources) AS src
                  FROM collections_index) s
              ON s.collection_id = i.collection_id
             AND lower(s.src.source_doi) = lower(i.source_DOI)
            WHERE i.collection_id = 'tcga_brca'
        """)
        pairs = set(zip(df["contributed_by"], df["converted_by"]))
        assert ("TCIA", "NOT_APPLICABLE") in pairs
        assert ("IDC", "IDC") in pairs
