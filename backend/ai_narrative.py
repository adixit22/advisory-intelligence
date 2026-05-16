import anthropic
import os
import json


def generate_client_brief(client: dict, market_data: dict, market_narrative: str, feedback: dict | None = None) -> dict:

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    claude = anthropic.Anthropic(api_key=api_key)

    holdings_text    = "\n".join(
        [f"  - {h['asset']}: {h['allocation']}% (${h['value']:,.0f})" for h in client["holdings"]]
    )
    goals_text       = "\n".join([f"  - {g}" for g in client["goals"]])
    life_events_text = "\n".join([f"  - {e}" for e in client["life_events"]])

    # Top-5 holdings summary for the prompt
    top_holdings = ", ".join(
        [f"{h['asset']} ({h['allocation']}%)" for h in client["holdings"][:5]]
    )

    # Extract the 5 market factor values for easy reference in the prompt
    sp    = market_data.get("sp500",        {})
    tnx   = market_data.get("treasury_10y", {})
    vix   = market_data.get("vix",          {})
    gold  = market_data.get("gold",         {})
    btc   = market_data.get("bitcoin",      {})

    # Build feedback section if prior meeting notes exist
    feedback_section = ""
    if feedback:
        feedback_section = f"""
PREVIOUS MEETING FEEDBACK (incorporate these into this brief — address concerns, lean into what resonated, act on agreed actions):
- Meeting date: {feedback.get('meeting_date', 'N/A')}
- Overall meeting rating: {feedback.get('rating', 'N/A')}/5
- Topics that resonated most with {client['name'].split()[0]}: {feedback.get('resonated_topics', 'N/A')}
- Concerns {client['name'].split()[0]} raised: {feedback.get('client_concerns', 'None noted')}
- What to focus on more next time: {feedback.get('focus_next_time', 'None specified')}
- Actions agreed in last meeting: {feedback.get('agreed_actions', 'None')}
- Advisor notes from last meeting: {feedback.get('advisor_notes', 'None')}

Use this feedback to make this brief noticeably more tailored. Reference the previous concerns directly, confirm progress on agreed actions, and give extra weight to the topics the client cared about.
"""

    prompt = f"""You are a senior wealth management advisor preparing a personalized video brief for a client meeting.
{feedback_section}

CLIENT PROFILE:
- Name: {client['name']}
- Age: {client['age']}
- Occupation: {client['occupation']}
- Location: {client['location']}
- Marital Status: {client['marital_status']}, Dependents: {client['dependents']}
- AUM: ${client['aum']:,.0f}
- Risk Profile: {client['risk_profile']} (Score: {client['risk_score']}/10)
- Annual Income: ${client['annual_income']:,.0f}
- YTD Return: {client['ytd_return']}% vs Benchmark: {client['benchmark_return']}%

PORTFOLIO HOLDINGS:
{holdings_text}

CLIENT GOALS:
{goals_text}

KEY LIFE EVENTS:
{life_events_text}

ADVISOR NOTES:
{client['advisor_notes']}

LIVE MARKET CONDITIONS (use exact numbers below — these appear on the market slide):
- S&P 500: {sp.get('value','N/A')} ({'+' if (sp.get('change_pct',0) or 0) >= 0 else ''}{sp.get('change_pct','N/A')}%)
- 10-Year Treasury Yield: {tnx.get('value','N/A')}%
- VIX Volatility Index: {vix.get('value','N/A')}
- Gold: ${gold.get('value','N/A')}/oz
- Bitcoin: ${btc.get('value','N/A')} ({'+' if (btc.get('change_pct',0) or 0) >= 0 else ''}{btc.get('change_pct','N/A')}%)

THE VIDEO HAS EXACTLY 4 SLIDES IN THIS ORDER:
  Slide 1 — COVER: shows {client['name']}'s name, occupation ({client['occupation']}), location, AUM (${client['aum']:,.0f}), risk profile ({client['risk_profile']})
  Slide 2 — PERFORMANCE: shows YTD return ({client['ytd_return']}% vs {client['benchmark_return']}% benchmark) and top holdings ({top_holdings})
  Slide 3 — MARKET CONDITIONS: shows all 5 live market figures listed above
  Slide 4 — INSIGHTS: shows the advisor talking points and recommended next action

Generate the following JSON with EXACTLY these keys. The four slide scripts must be tightly aligned with what is VISUALLY SHOWN on each slide:

{{
  "client_summary": "A warm, personalized 3-paragraph narrative written directly to {client['name']} in second person. Start with portfolio performance, weave in 2-3 live market factors, connect to their specific goals and life situation. Write like a trusted advisor, not a robot. Plain English, no jargon.",

  "advisor_talking_points": [
    "Talking point 1 — specific, actionable, references real numbers",
    "Talking point 2 — specific, actionable",
    "Talking point 3 — specific, actionable",
    "Talking point 4 — specific, actionable"
  ],

  "slide_1_script": "30-40 spoken words ONLY for the cover slide. Warm greeting using {client['name']}'s first name, mention their role as {client['occupation']}, state their portfolio value of ${client['aum']:,.0f}, and their {client['risk_profile']} risk profile. Nothing else — this slide only shows identity and AUM.",

  "slide_2_script": "70-90 spoken words ONLY for the performance slide. Discuss the {client['ytd_return']}% YTD return vs the {client['benchmark_return']}% benchmark. Name the specific holdings shown ({top_holdings}) and explain which are driving the performance. Keep it tightly tied to the numbers on screen.",

  "slide_3_script": "70-90 spoken words ONLY for the market conditions slide. Walk through each of the 5 market factors shown on screen — S&P 500, Treasury yield, VIX, Gold, and Bitcoin — using the exact values listed above. Explain how each one specifically affects {client['name']}'s portfolio given their {client['risk_profile']} profile.",

  "slide_4_script": "70-90 spoken words ONLY for the insights slide. Summarise 2-3 of the advisor talking points you listed above and close with the recommended next action. This is the call-to-action slide — end with a warm sign-off.",

  "next_action": "One specific, concrete recommended action the advisor should take before or after this meeting (1-2 sentences).",

  "market_impact_summary": "One sentence explaining how today's market conditions specifically affect this client's portfolio."
}}

Return only valid JSON, no markdown, no extra text."""

    message = claude.messages.create(
        model="claude-opus-4-6",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)
