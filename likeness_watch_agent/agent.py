"""
Likeness Watch — monitors the public web for unauthorized use of a media
personality's likeness in scam ads. Built for the Agentic Cinema hackathon
(Parallel track): Gemini + google-adk + Parallel Search API.
"""

import os
from google.adk.agents import Agent
from parallel import Parallel

from likeness_watch_agent.schema import RiskReport, Finding, Citation

_client = Parallel(api_key=os.environ["PARALLEL_API_KEY"])


def search_name_product_pairings(talent_name: str, known_endorsements: list[str]) -> dict:
    """Search the open web for products or claims attributed to this person that
    aren't in their known/verified endorsement list.

    Args:
        talent_name: Full name of the media personality being monitored.
        known_endorsements: List of products/brands this person has actually
            endorsed, used to filter out legitimate mentions.

    Returns:
        dict with 'candidates': list of {url, title, excerpt}
    """
    search = _client.search(
        objective=(
            f"Find recent web mentions of {talent_name} endorsing, promoting, or "
            f"appearing in ads for any product, investment, or health claim. "
            f"Flag anything not in this known list: {', '.join(known_endorsements)}."
        ),
        search_queries=[
            f'"{talent_name}" endorses OR promotes',
            f'"{talent_name}" ad scam OR fake',
        ],
    )
    return {
        "candidates": [
            {"url": r.url, "title": r.title, "excerpt": r.excerpts[0] if r.excerpts else ""}
            for r in search.results
        ]
    }


def cross_reference_scam_patterns(product_or_claim_text: str) -> dict:
    """Check whether language around a product/claim matches known deepfake-ad
    or investment-scam patterns (BBB Scam Tracker style language).

    Args:
        product_or_claim_text: The product name or claim text to check.

    Returns:
        dict with 'matched': bool and 'pattern_matches': list of {url, title, excerpt}
    """
    search = _client.search(
        objective=(
            f"Find BBB Scam Tracker reports, consumer fraud warnings, or news "
            f"coverage describing scam patterns involving: {product_or_claim_text}"
        ),
        search_queries=[
            f"{product_or_claim_text} scam BBB warning",
            f"{product_or_claim_text} deepfake ad fraud",
        ],
    )
    matched = len(search.results) > 0
    return {
        "matched": matched,
        "pattern_matches": [
            {"url": r.url, "title": r.title, "excerpt": r.excerpts[0] if r.excerpts else ""}
            for r in search.results
        ],
    }


def find_victim_reports(talent_name: str) -> dict:
    """Search for prior news coverage or victim complaint threads about this
    person's likeness being misused.

    Args:
        talent_name: Full name of the media personality being monitored.

    Returns:
        dict with 'reports': list of {url, title, excerpt}
    """
    search = _client.search(
        objective=(
            f"Find news coverage of {talent_name}'s likeness or image being used "
            f"without permission in ads"
        ),
        search_queries=[
            f'"{talent_name}" likeness stolen ad',
            f'"{talent_name}" deepfake report',
        ],
    )
    return {
        "reports": [
            {"url": r.url, "title": r.title, "excerpt": r.excerpts[0] if r.excerpts else ""}
            for r in search.results
        ]
    }


def compile_final_report(talent_name: str, findings: list[dict], victim_reports: list[dict]) -> dict:
    """Assemble and validate the final structured risk report. Call this LAST,
    after search_name_product_pairings and cross_reference_scam_patterns have
    been run for every candidate. Risk scoring is deterministic Python logic,
    not an LLM judgment — this guarantees well-formed JSON on every run.

    Args:
        talent_name: Full name of the media personality being monitored.
        findings: One entry per candidate mention, each shaped as
            {"claim": str, "source": {"url": str, "title": str, "excerpt": str},
             "scam_pattern_matched": bool}
        victim_reports: Results from find_victim_reports, each shaped as
            {"url": str, "title": str, "excerpt": str}

    Returns:
        dict — a validated RiskReport (talent_name, risk_flag, reason, findings,
        victim_reports, generated_at)
    """
    parsed_findings = [Finding(**f) for f in findings]
    parsed_victims = [Citation(**v) for v in victim_reports]

    any_match = any(f.scam_pattern_matched for f in parsed_findings)
    if any_match:
        flag = "red"
        reason = "Unverified product mention matches a known scam-language pattern."
        recommended_action = (
            "File a report at bbb.org/scamtracker citing the sources below, and request "
            "takedown directly from the platform hosting the ad. Given the scam-pattern "
            "match, consider escalating to a dedicated likeness-protection service "
            "(e.g. Loti AI, Vermillio) for automated takedown."
        )
    elif parsed_findings or parsed_victims:
        flag = "yellow"
        reason = "Unverified mention found, no confirmed scam-pattern match yet."
        recommended_action = (
            "Review the source directly to confirm whether this is a genuine unauthorized "
            "endorsement. If confirmed, request removal from the platform and re-run this "
            "check in a few days to see if it escalates."
        )
    else:
        flag = "green"
        reason = "No suspicious mentions found in this pass."
        recommended_action = "No action needed. Re-check periodically, especially around new product launches."

    report = RiskReport(
        talent_name=talent_name,
        risk_flag=flag,
        reason=reason,
        recommended_action=recommended_action,
        findings=parsed_findings,
        victim_reports=parsed_victims,
    )
    return report.model_dump()


root_agent = Agent(
    model="gemini-flash-lite-latest",
    name="likeness_watch_agent",
    description=(
        "Monitors the public web for unauthorized use of a media personality's "
        "likeness in scam ads."
    ),
    instruction=(
        "You are a likeness-misuse monitoring assistant for media talent managers. "
        "Given a talent name and known endorsements, call search_name_product_pairings "
        "first. For each candidate found, call cross_reference_scam_patterns on the "
        "product/claim text to check it against known scam patterns. Then call "
        "find_victim_reports once for the talent name. Finally call "
        "compile_final_report, passing every candidate as a finding (with its claim, "
        "source, and whether cross_reference_scam_patterns matched it) plus the "
        "victim reports. Return exactly what compile_final_report gives you — do not "
        "paraphrase or reformat it. Never state a claim without a source URL attached."
    ),
    tools=[
        search_name_product_pairings,
        cross_reference_scam_patterns,
        find_victim_reports,
        compile_final_report,
    ],
)
