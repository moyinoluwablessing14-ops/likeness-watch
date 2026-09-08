# Likeness Watch

Monitors the public web for unauthorized use of a media personality's likeness
in scam ads — built for mid-tier talent (local anchors, growing
YouTubers/podcasters, indie musicians) who can't afford enterprise
brand-protection tools like Loti AI or Vermillio.

Built for **Agentic Cinema: The Blockbuster Hackathon** — Parallel track.

## How it works

Give it a talent name + their known real endorsements. The agent:

1. Searches the open web for new product/claim mentions of that name
   (`search_name_product_pairings`)
2. Cross-references each mention against known scam-language patterns
   (`cross_reference_scam_patterns`)
3. Searches for prior victim/news reports about the person's likeness being
   misused (`find_victim_reports`)
4. Applies a rule-based risk score (`compute_risk_flag`) — red / yellow / green

Every claim in the output is tied to a cited source URL from Parallel Search.

## Stack

- `google-adk` + `google-genai` — Gemini 2.5 Flash, called via the Gemini
  Developer API (simple key auth, no Vertex/IAM setup required — this still
  satisfies the hackathon's Google Cloud AI requirement, per the accepted
  package list in the rules)
- `parallel-web` — Parallel Search API, called live at runtime for every
  finding in the report

## Running it (Google Cloud Shell — works entirely from a phone browser)

No laptop, no local install. Open `shell.cloud.google.com` in Chrome on your
phone, then:

```bash
git clone <your-repo-url>
cd likeness-watch
pip install -r requirements.txt

export GEMINI_API_KEY="your_key_from_aistudio.google.com/apikey"
export PARALLEL_API_KEY="your_key_from_platform.parallel.ai"

# Run the test suite first — no keys/network needed, proves the logic works
PYTHONPATH=.:tests python3 tests/test_agent.py

# Then start the real server (talks to live Gemini + Parallel)
python3 main.py
```

Open the Cloud Shell "Web Preview" on port 8080 to use the UI, or hit the API
directly:

```bash
curl -X POST localhost:8080/report \
  -H "Content-Type: application/json" \
  -d '{"talent_name": "Jane Anchor", "known_endorsements": ["RealBrand Watches"]}'
```

To push this repo to GitHub from Cloud Shell (git is preinstalled):

```bash
gh auth login          # device-code flow, works fine on mobile
git init
git add .
git commit -m "Likeness Watch: initial agent"
gh repo create likeness-watch --public --source=. --push
```

## Hackathon compliance

- Google Cloud AI tools only (`google-adk`, `google-genai`) — no other model
  vendors used anywhere in the running agent
- Parallel Search API imported and actually called at runtime (not just
  referenced) — 3 separate live calls per report
- Solves a documented real-world M&E workflow problem (see below)
- New project, built entirely during the contest window

## Why this problem

Celebrity/public-figure impersonation in fraudulent ads accounts for over
$1B in reported deepfake fraud losses (Surfshark analysis of AI Incident
Database + OECD data, through March 2026). Victims already include on-air
personalities like CNN's Wolf Blitzer and CBS's Gayle King — but the
underserved tier is everyone below A-list: local anchors, growing creators,
and their small managers, who have no monitoring budget and often only find
out when a follower sends them a screenshot.

## License

MIT — see [LICENSE](./LICENSE).
