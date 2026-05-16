import yfinance as yf
from datetime import datetime
import copy
import threading

FALLBACK_MARKET = {
    "sp500": {"label": "S&P 500", "value": 5842.47, "change_pct": 0.62, "description": "Broad US equity market performance", "impact": "positive"},
    "treasury_10y": {"label": "10-Year Treasury Yield", "value": 4.48, "change_pct": -0.22, "description": "Benchmark rate affecting bonds and mortgage rates", "impact": "positive", "unit": "%"},
    "vix": {"label": "VIX Volatility Index", "value": 18.3, "change_pct": -3.1, "description": "Market fear gauge - currently Moderate", "impact": "neutral"},
    "gold": {"label": "Gold (USD/oz)", "value": 3287.60, "change_pct": 0.41, "description": "Safe-haven demand and inflation hedge signal", "impact": "positive"},
    "bitcoin": {"label": "Bitcoin (USD)", "value": 104250, "change_pct": 1.84, "description": "Digital asset benchmark and risk-on/risk-off signal", "impact": "positive"},
}

TICKER_META = {
    "sp500":        ("^GSPC",   "S&P 500",                "Broad US equity market performance",                  None),
    "treasury_10y": ("^TNX",    "10-Year Treasury Yield", "Benchmark rate affecting bonds and mortgage rates",   "%"),
    "vix":          ("^VIX",    "VIX Volatility Index",   "Market fear gauge",                                   None),
    "gold":         ("GC=F",    "Gold (USD/oz)",          "Safe-haven demand and inflation hedge signal",         None),
    "bitcoin":      ("BTC-USD", "Bitcoin (USD)",          "Digital asset benchmark and risk-on/risk-off signal", None),
}


def _fetch_one(symbol, out, key):
    try:
        hist = yf.Ticker(symbol).history(period="5d")
        if hist.empty:
            raise ValueError("empty")
        out[key] = (float(hist["Close"].iloc[-1]), float(hist["Close"].iloc[-2]))
    except Exception:
        out[key] = None


def get_market_data():
    raw = {}
    threads = [threading.Thread(target=_fetch_one, args=(meta[0], raw, key), daemon=True)
               for key, meta in TICKER_META.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=6)

    factors = {}
    any_live = False
    for key, (symbol, label, desc, unit) in TICKER_META.items():
        pair = raw.get(key)
        if pair:
            current, prev = pair
            chg = ((current - prev) / prev) * 100
            impact = "positive" if chg >= 0 else "negative"
            if key == "vix":
                impact = "negative" if current > 25 else "neutral" if current > 15 else "positive"
            if key == "treasury_10y":
                impact = "negative" if chg > 0.5 else "positive" if chg < -0.5 else "neutral"
            entry = {"label": label, "value": round(current, 2 if current < 1000 else 0),
                     "change_pct": round(chg, 2), "description": desc, "impact": impact}
            if unit:
                entry["unit"] = unit
            factors[key] = entry
            any_live = True
        else:
            factors[key] = copy.deepcopy(FALLBACK_MARKET[key])

    factors["fetched_at"] = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    factors["is_live"] = any_live
    return factors


def get_market_narrative(factors):
    lines = []
    sp = factors.get("sp500", {})
    val = sp.get("value")
    if isinstance(val, (int, float)):
        d = "up" if sp.get("change_pct", 0) >= 0 else "down"
        chg_sp = sp.get("change_pct", 0)
        lines.append(f"The S&P 500 is {d} {abs(chg_sp):.2f}% today, at {val:,.0f}.")
    tnx = factors.get("treasury_10y", {})
    val = tnx.get("value")
    if isinstance(val, (int, float)):
        p = "puts pressure on bond prices" if tnx.get("change_pct", 0) > 0 else "offers relief for bond holders"
        lines.append(f"The 10-year Treasury yield is {val:.2f}%, which {p}.")
    vix = factors.get("vix", {})
    val = vix.get("value")
    if isinstance(val, (int, float)):
        if val > 25:
            lines.append(f"The VIX is elevated at {val:.1f}, signaling heightened market anxiety.")
        elif val < 15:
            lines.append(f"The VIX is low at {val:.1f}, reflecting calm market conditions.")
        else:
            lines.append(f"The VIX at {val:.1f} indicates moderate market uncertainty.")
    gold = factors.get("gold", {})
    val = gold.get("value")
    if isinstance(val, (int, float)):
        d = "rising" if gold.get("change_pct", 0) >= 0 else "falling"
        lines.append(f"Gold is {d} at ${val:,.0f}/oz.")
    btc = factors.get("bitcoin", {})
    val = btc.get("value")
    if isinstance(val, (int, float)):
        d = "up" if btc.get("change_pct", 0) >= 0 else "down"
        chg_btc = btc.get("change_pct", 0)
        lines.append(f"Bitcoin is {d} {abs(chg_btc):.1f}% at ${val:,.0f}.")
    return " ".join(lines) if lines else "Market data unavailable."
