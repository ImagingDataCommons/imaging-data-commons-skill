"""
Contract tests for the hosted IDC MCP server documented in SKILL.md and
references/mcp_guide.md.

The skill identifies the server by its `idc://guide` resource and by a fingerprint of
IDC-specific tool names. Those names are a contract with a service that versions
independently of this repository, so they can go stale silently. These tests read the
expectations out of the documentation and check them against the live server.

The server is at beta (3.0.0b5) and its tool set may still move. A drift failure here means
the docs need updating, not that the skill is broken — the skill falls back to idc-index
whenever identification fails.

Network tests skip (not fail) when the server is unreachable, so an outage does not turn CI
red. Tests that only compare documentation files run offline.
"""

import json
import os
import re
import urllib.error
import urllib.request

import pytest

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_SKILL_MD = os.path.join(_ROOT, "SKILL.md")
_MCP_GUIDE = os.path.join(_ROOT, "references", "mcp_guide.md")
_USAGE_MD = os.path.join(_ROOT, "USAGE.md")

MCP_URL = "https://api.imaging.datacommons.cancer.gov/mcp"
# The REST API lives on the same host; SKILL.md and USAGE.md may reference it too.
REST_PREFIX = "https://api.imaging.datacommons.cancer.gov/v3"

# Names generic enough that another MCP server could plausibly expose them. The skill must
# never rely on these to identify IDC; see "Identifying the server" in mcp_guide.md.
GENERIC_TOOL_NAMES = {"run_sql", "get_stats", "list_tables", "get_citations"}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _section(text, heading):
    """Return the body of a Markdown section, up to the next same-or-higher heading."""
    level = heading.split(" ", 1)[0]
    match = re.search(
        rf"^{re.escape(heading)}\s*$(.*?)(?=^#{{1,{len(level)}}} |\Z)",
        text,
        re.M | re.S,
    )
    assert match, f"section {heading!r} not found"
    return match.group(1)


# ---------------------------------------------------------------------------
# Expectations parsed out of the documentation
# ---------------------------------------------------------------------------

def documented_fingerprint():
    """Tool names SKILL.md tells the agent to identify the server by."""
    body = _section(_read(_SKILL_MD), "## IDC MCP Server")
    match = re.search(r"three or more of the tool names\s+(.+?)\.\s", body, re.S)
    assert match, "could not locate the tool-name fingerprint in SKILL.md"
    return set(re.findall(r"`([a-z_]+)`", match.group(1)))


def documented_inventory():
    """Every tool listed in the mcp_guide.md inventory table."""
    body = _section(_read(_MCP_GUIDE), "## Tool inventory")
    names = set()
    for line in body.splitlines():
        if line.startswith("|"):
            names.update(re.findall(r"`([a-z_]+)`", line))
    assert names, "could not parse the tool inventory table in mcp_guide.md"
    return names


# ---------------------------------------------------------------------------
# Live server
# ---------------------------------------------------------------------------

def _rpc(method, timeout=20):
    """Single JSON-RPC call. The server needs no session handshake and no auth."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    request = urllib.request.Request(
        MCP_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode()
    # Streamable HTTP may frame the reply as a single SSE event.
    if body.lstrip().startswith("event:") or body.lstrip().startswith("data:"):
        body = "\n".join(
            line[len("data:"):].strip()
            for line in body.splitlines()
            if line.startswith("data:")
        )
    return json.loads(body)["result"]


@pytest.fixture(scope="session")
def server_tools():
    try:
        result = _rpc("tools/list")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"IDC MCP server unreachable: {exc}")
    return {tool["name"] for tool in result["tools"]}


@pytest.fixture(scope="session")
def server_resources():
    try:
        result = _rpc("resources/list")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"IDC MCP server unreachable: {exc}")
    return {resource["uri"] for resource in result["resources"]}


# ===========================================================================
# Documentation-only checks (no network)
# ===========================================================================

class TestDocumentedContract:
    """Internal consistency of the MCP guidance across the skill's files."""

    def test_endpoint_url_is_consistent_across_docs(self):
        # Every api.imaging.datacommons.cancer.gov URL in these files must be either the MCP
        # endpoint or a /v3 REST path — a bare host or a stale /v1, /v2 path is a typo.
        for path in (_SKILL_MD, _MCP_GUIDE, _USAGE_MD):
            urls = set(re.findall(r"https://api\.imaging\.datacommons\.cancer\.gov[\w/.-]*", _read(path)))
            assert MCP_URL in urls, f"{os.path.basename(path)} does not reference the MCP URL"
            stray = {url for url in urls if url != MCP_URL and not url.startswith(REST_PREFIX)}
            assert not stray, f"{os.path.basename(path)} references unexpected IDC API URLs: {sorted(stray)}"

    def test_fingerprint_excludes_generic_tool_names(self):
        # Guards the design decision in mcp_guide.md: a name another server could also
        # expose must never become evidence that this is IDC.
        overlap = documented_fingerprint() & GENERIC_TOOL_NAMES
        assert not overlap, f"fingerprint in SKILL.md relies on generic tool names: {sorted(overlap)}"

    def test_fingerprint_is_large_enough_for_its_own_threshold(self):
        # SKILL.md asks for "three or more of" these names.
        assert len(documented_fingerprint()) >= 3

    def test_fingerprint_is_covered_by_the_inventory(self):
        missing = documented_fingerprint() - documented_inventory()
        assert not missing, f"fingerprint names absent from the mcp_guide.md inventory: {sorted(missing)}"


# ===========================================================================
# Live server contract
# ===========================================================================

class TestLiveServer:
    """The documented contract still holds against the deployed server."""

    def test_fingerprint_tool_names_still_exist(self, server_tools):
        missing = documented_fingerprint() - server_tools
        assert not missing, (
            f"identification would fail: {sorted(missing)} no longer exist on the server. "
            f"Update the fingerprint in SKILL.md and references/mcp_guide.md."
        )

    def test_guide_resource_still_exists(self, server_resources):
        assert "idc://guide" in server_resources, (
            "the idc://guide resource is gone; it is the strongest identification signal "
            "documented in references/mcp_guide.md"
        )

    def test_documented_tools_still_exist(self, server_tools):
        missing = documented_inventory() - server_tools
        assert not missing, (
            f"mcp_guide.md documents tools the server no longer exposes: {sorted(missing)}"
        )

    def test_inventory_covers_every_server_tool(self, server_tools):
        undocumented = server_tools - documented_inventory()
        assert not undocumented, (
            f"the server exposes tools missing from the mcp_guide.md inventory table: "
            f"{sorted(undocumented)}"
        )
