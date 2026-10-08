"""
Contract tests for the hosted IDC REST API documented in references/rest_api_guide.md.

The guide documents an API that versions independently of this repository — endpoint paths,
filterable attributes, request body shapes, and row caps are all a contract with a beta
service (3.0.0b5) that can move without notice. These tests parse the expectations out of the
guide and check them against the live API, so drift shows up as a CI failure rather than as
wrong instructions to an agent.

A failure here means the guide needs updating, not that the skill is broken. The skill routes
read-only metadata to this API when idc-index is not installed, so drift here does reach users —
but downloads and local analysis stay on idc-index, which never touches the API.

Network tests skip (not fail) when the API is unreachable, so an outage does not turn CI red.
Tests that only read documentation files run offline.
"""

import json
import os
import re
import urllib.error
import urllib.request

import pytest

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_SKILL_MD = os.path.join(_ROOT, "SKILL.md")
_REST_GUIDE = os.path.join(_ROOT, "references", "rest_api_guide.md")

# The URL the skill hands to users; documentation assertions always check this one.
DOCUMENTED_BASE_URL = "https://api.imaging.datacommons.cancer.gov/v3"
# What the live tests probe. Override with IDC_API_BASE to verify the contract against a staging
# deployment before it reaches production.
BASE_URL = os.environ.get("IDC_API_BASE", DOCUMENTED_BASE_URL)
TIMEOUT = 30

# Every filtered endpoint takes the filter object under a single `filters` key. The endpoints
# that enumerate series additionally require at least one predicate; the aggregate ones answer an
# unfiltered filter with a warning instead.
FILTERED_ENDPOINTS = ("/cohort/counts", "/licenses", "/cohort/manifest",
                      "/cohort/manifest.txt", "/citations")
REQUIRE_A_PREDICATE = ("/cohort/manifest", "/cohort/manifest.txt")


def _filtered(path, filters, **extra):
    """POST `path` with the documented body shape: the filter under `filters`."""
    return _request(path, {"filters": filters, **extra})


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Expectations parsed out of the documentation
# ---------------------------------------------------------------------------

def documented_endpoints():
    """Method/path pairs from the endpoint reference table in rest_api_guide.md.

    The guide writes paths both bare (`GET /version`, under a heading that states the /v3
    base) and fully qualified (`GET /v3/version`, where it stands alone); both denote the
    same endpoint, so the /v3 prefix is normalized away.
    """
    body = _read(_REST_GUIDE)
    pairs = {
        (method, re.sub(r"^/v3(?=/)", "", path))
        for method, path in re.findall(r"`(GET|POST) (/[\w./{}-]+)`", body)
    }
    assert pairs, "could not parse the endpoint reference table in rest_api_guide.md"
    return pairs


def documented_attributes(kind):
    """Filterable attributes the guide lists as `term` or `range`."""
    match = re.search(rf"^\| `{kind}` \| (.+?) \|\s*$", _read(_REST_GUIDE), re.M)
    assert match, f"could not find the {kind!r} attribute row in rest_api_guide.md"
    return set(re.findall(r"`(\w+)`", match.group(1)))


def documented_limits():
    """{(endpoint, parameter): (default, cap)} from the limits table."""
    limits = {}
    for line in _read(_REST_GUIDE).splitlines():
        match = re.match(
            r"\| `(?:GET|POST) (/[\w./{}-]+)` \| `(\w+)` \| `?([\w.]+)`? \| ([\w—-]+) \|",
            line,
        )
        if match:
            path, param, default, cap = match.groups()
            limits[(path, param)] = (default, cap)
    assert limits, "could not parse the limits table in rest_api_guide.md"
    return limits


# ---------------------------------------------------------------------------
# Live API
# ---------------------------------------------------------------------------

def _request(path, payload=None, raw=False):
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if isinstance(exc, urllib.error.HTTPError):
            raise
        pytest.skip(f"IDC REST API unreachable: {exc}")
    return body if raw else json.loads(body)


@pytest.fixture(scope="session")
def version():
    return _request("/version")


@pytest.fixture(scope="session")
def attributes():
    return _request("/attributes")


# ===========================================================================
# Documentation-only checks (no network)
# ===========================================================================

class TestDocumentedContract:
    """Internal consistency of the REST API guidance across the skill's files."""

    def test_skill_md_points_at_the_guide(self):
        skill = _read(_SKILL_MD)
        assert "references/rest_api_guide.md" in skill
        assert DOCUMENTED_BASE_URL in skill, "SKILL.md does not name the REST API base URL"

    def test_guide_documents_every_surface(self):
        paths = {path for _, path in documented_endpoints()}
        for required in ("/version", "/stats", "/collections", "/attributes",
                         "/cohort/counts", "/cohort/manifest", "/cohort/manifest.txt",
                         "/sql", "/tables", "/viewer-url", "/citations", "/licenses"):
            assert required in paths, f"{required} missing from the endpoint reference"

    def test_v1_and_v2_are_marked_for_retirement(self):
        # V1/V2 are scheduled for shutdown; the skill must never hand out their URLs, and must
        # tell the agent to port rather than extend V1/V2 code it is shown.
        guide = _read(_REST_GUIDE)
        assert "V1 and V2 are being retired" in guide
        for text, name in ((guide, "rest_api_guide.md"), (_read(_SKILL_MD), "SKILL.md")):
            stale = re.findall(r"https://api\.imaging\.datacommons\.cancer\.gov/v[12]\b", text)
            assert not stale, f"{name} points at a retired API version: {stale}"

    def test_version_skew_download_workaround_is_documented(self):
        # idc-index resolves manifest URLs against its own index, so a manifest from a newer
        # API release loses rows silently. Both files must carry the direct-bucket fallback.
        guide = _read(_REST_GUIDE)
        assert "When the local index is a data release behind the API" in guide
        assert "s5cmd --no-sign-request run" in guide
        assert "s5cmd --no-sign-request" in _read(_SKILL_MD), (
            "SKILL.md must name the direct-bucket fallback; the failure it avoids is silent"
        )

    def test_single_body_shape_is_documented(self):
        # One shape for every filtered endpoint. Before this contract, a mis-shaped body was not
        # an error — it silently selected all of IDC — so the uniformity is load-bearing.
        body = _read(_REST_GUIDE)
        assert "The server reports what it filtered on" in body
        assert "always goes under a `filters` key" in body
        for path in FILTERED_ENDPOINTS:
            assert path.lstrip("/").replace("cohort/", "") in body

    def test_warnings_contract_is_inline_in_skill_md(self):
        # An agent that never reads `warnings` can still report a count that had a predicate
        # dropped, so this has to be in the always-loaded file, not only in the guide.
        skill = _read(_SKILL_MD)
        assert "always goes under `filters`" in skill, (
            "SKILL.md must state the single filter body shape"
        )
        assert "filters_applied" in skill and "warnings" in skill, (
            "SKILL.md must tell the agent to read filters_applied/warnings before "
            "reporting a count"
        )


# ===========================================================================
# Live API contract
# ===========================================================================

class TestLiveEndpoints:
    """Every documented endpoint still exists and answers."""

    def test_version_reports_an_idc_release(self, version):
        assert re.fullmatch(r"v\d+", version["idc_version"]), version
        assert version["api_version"].startswith("3."), version

    def test_idc_index_data_version_is_comparable_on_both_sides(self, version):
        # The guide tells the agent to compare idc-index-data versions rather than the coarse
        # vNN label. That only works while both sides expose the exact version.
        assert re.fullmatch(r"\d+\.\d+\.\d+", version["idc_index_data_version"]), version
        try:
            import idc_index_data
        except ImportError:
            pytest.skip("idc-index not installed; API side verified above")
        assert re.fullmatch(r"\d+\.\d+\.\d+", idc_index_data.__version__), (
            "idc_index_data.__version__ is not the plain version the guide documents"
        )
        # Deliberately not asserting equality: the two version independently, and a mismatch is
        # the case the guide teaches the agent to report, not a test failure.

    def test_guide_tested_with_header_matches_deployment(self, version):
        header = re.search(r"\*\*Tested with:\*\* API `([\w.]+)`", _read(_REST_GUIDE))
        assert header, "rest_api_guide.md lost its 'Tested with' header"
        if header.group(1) != version["api_version"]:
            pytest.skip(
                f"API moved from {header.group(1)} to {version['api_version']}; "
                f"re-verify rest_api_guide.md and update its header"
            )

    def test_stats_are_populated(self):
        stats = _request("/stats")
        for field in ("collections", "patients", "studies", "series", "instances", "size_TB"):
            assert stats[field] > 0, f"{field} is empty in /stats"

    def test_get_endpoints_respond(self):
        # Endpoints that need a path or query parameter are covered by the next test.
        needs_argument = ("/health", "/v3", "/viewer-url")
        for method, path in sorted(documented_endpoints()):
            if method != "GET" or "{" in path or path in needs_argument:
                continue
            assert _request(path) is not None, f"GET {path} returned nothing"

    def test_parameterized_get_endpoints_respond(self):
        assert _request("/collections/rider_pilot")["series"] > 0
        assert _request("/tables/index")["columns"]
        assert _request("/attributes/Modality/values?limit=3")["values"]
        assert _request("/clinical/tables?collection_id=nlst")["tables"]
        assert _request("/clinical/tables/nlst_canc")["columns"]
        assert _request("/clinical/tables/nlst_canc/rows?max_rows=5")["rows"]
        assert _request("/viewer-url?series_instance_uid=1.3.6.1.4.1.14519.5.2.1.7695.4164."
                        "174071765480311650274095134055")["viewer_url"].startswith("https://")


class TestFilterableAttributes:
    """The attribute lists quoted in the guide still match the API."""

    def test_term_attributes_still_exist(self, attributes):
        live = {a["name"] for a in attributes if a["kind"] == "term"}
        assert documented_attributes("term") == live, (
            "rest_api_guide.md's term-attribute list has drifted from GET /attributes"
        )

    def test_range_attributes_still_exist(self, attributes):
        live = {a["name"] for a in attributes if a["kind"] == "range"}
        assert documented_attributes("range") == live, (
            "rest_api_guide.md's range-attribute list has drifted from GET /attributes"
        )


class TestCohortSurface:
    """Filter semantics, and the reporting that makes a dropped predicate visible."""

    def test_every_filtered_endpoint_takes_the_same_shape(self):
        counts = _filtered("/cohort/counts", {"terms": {"collection_id": ["rider_pilot"]}})
        assert 0 < counts["series"] < 10000, counts
        assert counts["filters_applied"]["terms"] == {"collection_id": ["rider_pilot"]}
        assert counts["warnings"] == [], counts["warnings"]

    def test_a_bare_filter_is_rejected_rather_than_ignored(self):
        # This is the contract the guide rests on. Before it, the bare shape returned all of IDC
        # at HTTP 200 on these two endpoints, which an agent cannot distinguish from a real count.
        for path in ("/cohort/counts", "/licenses"):
            with pytest.raises(urllib.error.HTTPError) as exc:
                _request(path, {"terms": {"collection_id": ["rider_pilot"]}})
            assert exc.value.code == 422, f"{path} accepted a bare filter object"
            assert "filters" in exc.value.read().decode(), (
                f"the {path} 422 does not name the correct shape"
            )

    def test_unrecognized_keys_are_refused(self):
        # A misspelled range bound used to be dropped in silence.
        with pytest.raises(urllib.error.HTTPError) as exc:
            _filtered("/cohort/counts", {"ranges": {"instanceCount": {"min": 5}}})
        assert exc.value.code == 422

    def test_series_enumerating_endpoints_require_a_predicate(self):
        for path in REQUIRE_A_PREDICATE:
            with pytest.raises(urllib.error.HTTPError) as exc:
                _filtered(path, {})
            assert exc.value.code == 400, f"{path} enumerated an unfiltered cohort"

    def test_aggregate_endpoints_warn_instead_of_answering_silently(self):
        # "How big is IDC" is legitimate, so counts answers — but says what it did.
        counts = _filtered("/cohort/counts", {})
        assert counts["series"] > 1_000_000, counts
        assert any("ENTIRE IDC" in w for w in counts["warnings"]), counts["warnings"]

    def test_a_predicate_that_constrains_nothing_is_reported(self):
        # The case no shape check catches: one good predicate plus one empty list still returns a
        # plausible number, so `warnings` is the only signal that half the filter vanished.
        counts = _filtered("/cohort/counts",
                           {"terms": {"collection_id": ["rider_pilot"], "Modality": []}})
        assert counts["series"] > 0
        assert "Modality" not in counts["filters_applied"]["terms"]
        assert any("Modality" in w for w in counts["warnings"]), counts["warnings"]

    def test_manifest_pages(self):
        manifest = _filtered(
            "/cohort/manifest",
            {"terms": {"collection_id": ["rider_pilot"], "Modality": ["CT"]}},
            page=0, page_size=3,
        )
        assert manifest["returned"] == 3
        assert manifest["total_series"] < _request("/stats")["series"], "filter was dropped"
        row = manifest["series"][0]
        for field in ("SeriesInstanceUID", "series_aws_url", "series_size_MB", "crdc_series_uuid"):
            assert field in row, f"{field} missing from a manifest row"
        assert row["series_aws_url"].startswith("s3://")

    def test_ranges_filter_narrows_the_cohort(self):
        terms = {"collection_id": ["rider_pilot"], "Modality": ["CT"]}
        unranged = _filtered("/cohort/counts", {"terms": terms})
        ranged = _filtered("/cohort/counts",
                           {"terms": terms, "ranges": {"instanceCount": {"gte": 100}}})
        assert 0 < ranged["series"] < unranged["series"]

    def test_manifest_txt_returns_s3_urls(self):
        text = _request("/cohort/manifest.txt",
                        {"filters": {"terms": {"collection_id": ["rider_pilot"]}}, "limit": 5},
                        raw=True)
        lines = [line for line in text.splitlines() if line.strip()]
        assert lines and all(line.startswith("s3://") for line in lines), lines[:3]

    def test_gcs_source_also_returns_s3_urls(self):
        # Documented gotcha: source=gcs reaches GCS's S3-compatible endpoint, never gs://.
        text = _request("/cohort/manifest.txt",
                        {"filters": {"terms": {"collection_id": ["rider_pilot"]}},
                         "source": "gcs", "limit": 3},
                        raw=True)
        assert all(line.startswith("s3://") for line in text.splitlines() if line.strip())

    def test_unknown_attribute_is_rejected(self):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _filtered("/cohort/counts", {"terms": {"NotAnAttribute": ["x"]}})
        assert exc.value.code == 400
        assert json.loads(exc.value.read())["error"]["code"] == "invalid_query"

    def test_miscased_value_returns_zero_and_says_why(self):
        # Zero with a casing warning vs zero with none is what lets an agent tell a typo from a
        # genuinely empty cohort. The guide tells it to rely on that distinction.
        miscased = _filtered("/cohort/counts", {"terms": {"Modality": ["mr"]}})
        assert miscased["series"] == 0
        assert any("case-sensitive" in w for w in miscased["warnings"]), miscased["warnings"]

        absent = _filtered("/cohort/counts", {"terms": {"collection_id": ["no_such_collection"]}})
        assert absent["series"] == 0
        assert absent["warnings"] == [], (
            "a value that exists in no casing must return zero with no warning, or the "
            "zero-plus-empty-warnings signal the guide documents is not trustworthy"
        )


class TestSqlSurface:
    """Guardrails and caps the guide states as fact."""

    def test_select_runs(self):
        result = _request("/sql", {"sql": "SELECT Modality, count(*) n FROM index GROUP BY 1", "max_rows": 5})
        assert result["columns"] == ["Modality", "n"]
        assert result["row_count"] == 5 and result["truncated"] is True

    def test_non_select_is_rejected(self):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _request("/sql", {"sql": "DROP TABLE index"})
        assert exc.value.code == 400

    def test_default_and_maximum_row_caps_match_the_guide(self):
        default, cap = documented_limits()[("/sql", "max_rows")]
        assert _request("/sql", {"sql": "SELECT SeriesInstanceUID FROM index"})["max_rows"] == int(default)
        clamped = _request("/sql", {"sql": "SELECT SeriesInstanceUID FROM index",
                                    "max_rows": int(cap) * 10})
        assert clamped["max_rows"] == int(cap), (
            f"the /sql row cap moved from {cap} to {clamped['max_rows']}"
        )

    def test_page_size_cap_matches_the_guide(self):
        _, cap = documented_limits()[("/cohort/manifest", "page_size")]
        response = _request("/cohort/manifest",
                            {"filters": {"terms": {"collection_id": ["rider_pilot"]}},
                             "page_size": int(cap) * 10, "include_rows": False})
        assert response["page_size"] == int(cap)

    def test_array_column_join_pattern_still_works(self):
        # The list_contains / segmented_SeriesInstanceUID example from the guide.
        result = _request("/sql", {
            "sql": "SELECT count(DISTINCT i.SeriesInstanceUID) AS slides FROM index i "
                   "JOIN seg_index seg ON seg.segmented_SeriesInstanceUID = i.SeriesInstanceUID "
                   "WHERE i.Modality = 'SM' "
                   "AND list_contains(seg.SegmentedPropertyType_CodeMeanings, 'Nucleus')",
            "max_rows": 1})
        assert result["rows"][0]["slides"] > 0

    def test_clinical_schema_join_pattern_still_works(self):
        result = _request("/sql", {
            "sql": "SELECT count(DISTINCT i.PatientID) AS patients FROM index i "
                   "JOIN clinical.nlst_canc c ON c.dicom_patient_id = i.PatientID "
                   "WHERE i.collection_id = 'nlst' AND i.Modality = 'CT' "
                   "AND c.clinical_stag = '400'",
            "max_rows": 1})
        assert result["rows"][0]["patients"] > 0


class TestAttributionSurface:
    """Licenses and citations, which the skill tells users to check before publishing."""

    def test_licenses_are_reported_per_cohort(self):
        licenses = _filtered("/licenses", {"terms": {"collection_id": ["rider_pilot"]}})["licenses"]
        assert licenses and all({"license_short_name", "series", "size_TB"} <= set(item) for item in licenses)

    def test_citations_include_the_idc_acknowledgment(self):
        for fmt in ("apa", "bibtex"):
            result = _request("/citations", {"filters": {"terms": {"collection_id": ["rider_pilot"]}},
                                             "citation_format": fmt})
            assert result["format"] == fmt
            assert result["citations"], f"no citations returned for {fmt}"
            assert "10.1148/rg.230180" in result["idc_acknowledgment"]
