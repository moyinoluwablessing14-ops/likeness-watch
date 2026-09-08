"""
Runs the ACTUAL agent.py / schema.py logic offline, with Parallel calls
monkeypatched (fake_search) so no network/API keys are needed. Verifies:
  1. compile_final_report produces correct red/yellow/green flags
  2. The three search tools shape raw Parallel results into the expected dicts
"""

import os
os.environ.setdefault("PARALLEL_API_KEY", "test-dummy-key")

import _offline_shims  # noqa: F401 — must run before importing agent
from likeness_watch_agent import agent


def fake_result(url, title, excerpt):
    class R:
        pass
    r = R()
    r.url, r.title, r.excerpts = url, title, [excerpt]
    return r


class FakeSearchResponse:
    def __init__(self, results):
        self.results = results


passed, failed = 0, 0


def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")


# --- Test 1: RED — unverified claim + scam pattern match ---
print("Scenario: RED (scam pattern matched)")
report = agent.compile_final_report(
    talent_name="Jane Anchor",
    findings=[{
        "claim": "Jane Anchor endorses MiracleGlucose supplement",
        "source": {"url": "https://example.com/ad1", "title": "Fake ad", "excerpt": "..."},
        "scam_pattern_matched": True,
    }],
    victim_reports=[],
)
check("risk_flag == red", report["risk_flag"] == "red")
check("reason mentions scam pattern", "scam-language pattern" in report["reason"])
check("recommended_action present for red", "bbb.org" in report["recommended_action"].lower())
check("findings preserved", len(report["findings"]) == 1)
check("generated_at present", bool(report.get("generated_at")))

# --- Test 2: YELLOW — unverified claim, no pattern match ---
print("\nScenario: YELLOW (unverified, no pattern match)")
report = agent.compile_final_report(
    talent_name="Jane Anchor",
    findings=[{
        "claim": "Jane Anchor promotes a new watch brand",
        "source": {"url": "https://example.com/ad2", "title": "Watch ad", "excerpt": "..."},
        "scam_pattern_matched": False,
    }],
    victim_reports=[],
)
check("risk_flag == yellow", report["risk_flag"] == "yellow")

# --- Test 3: GREEN — nothing found ---
print("\nScenario: GREEN (nothing found)")
report = agent.compile_final_report(talent_name="Jane Anchor", findings=[], victim_reports=[])
check("risk_flag == green", report["risk_flag"] == "green")
check("findings empty list, not null", report["findings"] == [])

# --- Test 4: tool shaping — search_name_product_pairings ---
print("\nScenario: search_name_product_pairings shapes raw results correctly")
agent._client.search = lambda objective, search_queries: FakeSearchResponse([
    fake_result("https://example.com/x", "Some ad", "Jane Anchor promotes X"),
])
out = agent.search_name_product_pairings("Jane Anchor", ["RealBrand"])
check("candidates key present", "candidates" in out)
check("one candidate shaped correctly", out["candidates"][0]["url"] == "https://example.com/x")

# --- Test 5: tool shaping — cross_reference_scam_patterns with no results ---
print("\nScenario: cross_reference_scam_patterns with zero hits -> matched=False")
agent._client.search = lambda objective, search_queries: FakeSearchResponse([])
out = agent.cross_reference_scam_patterns("MiracleGlucose supplement")
check("matched == False", out["matched"] is False)
check("pattern_matches empty", out["pattern_matches"] == [])

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
