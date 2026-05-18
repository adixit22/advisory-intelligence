import os
import threading
import textwrap
import math
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
import tempfile

# Support moviepy 1.x and 2.x
try:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
    MOVIEPY_V2 = False
except ImportError:
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
    MOVIEPY_V2 = True

# Video dimensions — 16:9 HD
WIDTH, HEIGHT = 1280, 720

# Color palette — professional fintech dark theme
BG_DARK = (10, 16, 38)
BG_CARD = (20, 30, 60)
ACCENT_BLUE = (99, 102, 241)
ACCENT_GREEN = (16, 185, 129)
ACCENT_AMBER = (245, 158, 11)
ACCENT_RED = (239, 68, 68)
WHITE = (255, 255, 255)
GRAY_LIGHT = (180, 190, 210)
GRAY_MED = (100, 115, 140)


def load_font(size: int, bold: bool = False):
    """Load a font, fallback to default if not found."""
    font_paths = [
        # Windows
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default(size)


def draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2 * radius, y0 + 2 * radius], fill=fill)
    draw.ellipse([x1 - 2 * radius, y0, x1, y0 + 2 * radius], fill=fill)
    draw.ellipse([x0, y1 - 2 * radius, x0 + 2 * radius, y1], fill=fill)
    draw.ellipse([x1 - 2 * radius, y1 - 2 * radius, x1, y1], fill=fill)


def draw_progress_bar(draw, x, y, w, h, pct, color):
    draw_rounded_rect(draw, [x, y, x + w, y + h], 4, BG_CARD)
    fill_w = int(w * min(pct / 100, 1.0))
    if fill_w > 8:
        draw_rounded_rect(draw, [x, y, x + fill_w, y + h], 4, color)


def _fmt_speech(text: str) -> str:
    """Convert text to TTS-friendly spoken form: fix ranges, currencies, special chars."""
    import re
    # Normalise any corrupted/unicode dash-like chars to a plain en-dash
    text = re.sub(r'[–—‒―■⨂�]', '–', text)

    # $XM–$YM  or  $XK–$YM  ranges  →  "X million to Y million dollars"
    def _money_range(m):
        def _label(n, s):
            w = {'M': 'million', 'K': 'thousand', 'B': 'billion'}.get(s.upper(), '')
            return f"{n} {w} dollars" if w else f"{n} dollars"
        return f"{_label(m.group(1), m.group(2))} to {_label(m.group(3), m.group(4))}"
    text = re.sub(
        r'\$(\d+(?:\.\d+)?)\s*([MKBmkb])\s*–\s*\$(\d+(?:\.\d+)?)\s*([MKBmkb])',
        _money_range, text)

    # Remaining single $XM / $XK / $XB
    def _money_single(m):
        w = {'M': 'million', 'K': 'thousand', 'B': 'billion'}.get(m.group(2).upper(), '')
        return f"{m.group(1)} {w} dollars" if w else f"{m.group(1)} dollars"
    text = re.sub(r'\$(\d+(?:\.\d+)?)\s*([MKBmkb])\b', _money_single, text)

    # $1,234,567  →  spoken amount
    def _money_full(m):
        n = int(m.group(1).replace(',', ''))
        if n >= 1_000_000:
            v = f"{n/1_000_000:.2f}".rstrip('0').rstrip('.')
            return f"{v} million dollars"
        if n >= 1_000:
            return f"{n // 1_000} thousand dollars"
        return f"{n} dollars"
    text = re.sub(r'\$(\d{1,3}(?:,\d{3})+)', _money_full, text)

    # Any remaining bare en-dash between numbers → "to"
    text = re.sub(r'(\d)\s*–\s*(\d)', r'\1 to \2', text)

    # Remove leftover stray dashes that aren't between numbers
    text = re.sub(r'\s*–\s*', ' ', text)

    return text


def _clean_display(text: str) -> str:
    """Replace Unicode chars Arial/DejaVu can't render with safe ASCII equivalents."""
    import re
    # Numeric ranges: $2.5–$3M, 4–6 months → use "to"
    text = re.sub(r'(\d)\s*[–—–—■⨂�⊠□■]\s*(\$|\d)', r'\1 to \2', text)
    # Any remaining unprintable dash-like chars → plain hyphen
    text = re.sub(r'[–—–—■⨂�⊠□■]', '-', text)
    return text


def _shorten_tp_display(text: str, max_chars: int = 100) -> str:
    """
    Truncate a long talking point to its first meaningful clause for slide display.
    Cuts at ' - ', ' using ', '; ' etc. so the displayed text ends at a natural break,
    not mid-sentence. Adds '...' when truncated.
    """
    text = _clean_display(text)
    # Common separators that signal methodology/detail starting — cut before these
    stop_phrases = [' - ', '; ', ' using ', ' through ', ' while ', ' targeting ',
                    ' consistent with ', ' building ']
    earliest = len(text)
    for sep in stop_phrases:
        idx = text.find(sep)
        if 25 < idx < earliest:  # Must have meaningful content before the cut
            earliest = idx
    if earliest < len(text):
        return text[:earliest].rstrip('.,;:') + '...'
    # No separator found — truncate at max_chars at a word boundary
    if len(text) > max_chars:
        cut = text[:max_chars].rfind(' ')
        return text[:max(cut, 40)].rstrip('.,;:') + '...'
    return text


def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ── Slide 1: Cover ─────────────────────────────────────────────────────────────

def make_cover_slide(client: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)

    # Gradient overlay strip
    for i in range(HEIGHT):
        alpha = int(30 * (1 - i / HEIGHT))
        draw.line([(0, i), (WIDTH, i)], fill=(99, 102, 241, alpha))

    # Logo / brand text
    font_brand = load_font(18)
    draw.text((60, 40), "ADVISORY INTELLIGENCE", font=font_brand, fill=WHITE)

    # Accent line
    draw.rectangle([60, 70, 200, 73], fill=ACCENT_BLUE)

    # Avatar circle
    avatar_x, avatar_y, avatar_r = 640, 200, 70
    draw.ellipse([avatar_x - avatar_r, avatar_y - avatar_r, avatar_x + avatar_r, avatar_y + avatar_r],
                 fill=tuple(int(client.get("avatar_color", "#6366f1").lstrip("#")[i:i+2], 16) for i in (0, 2, 4)))
    font_avatar = load_font(40, bold=True)
    initials = client.get("avatar_initials", "??")
    bbox = draw.textbbox((0, 0), initials, font=font_avatar)
    draw.text((avatar_x - (bbox[2] - bbox[0]) // 2, avatar_y - (bbox[3] - bbox[1]) // 2 - 5),
              initials, font=font_avatar, fill=WHITE)

    # Client name
    font_name = load_font(48, bold=True)
    bbox = draw.textbbox((0, 0), client["name"], font=font_name)
    draw.text(((WIDTH - bbox[2]) // 2, 295), client["name"], font=font_name, fill=WHITE)

    # Subtitle
    subtitle = f"{client['occupation']}  •  {client['location']}"
    font_sub = load_font(22)
    bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
    draw.text(((WIDTH - bbox[2]) // 2, 360), subtitle, font=font_sub, fill=GRAY_LIGHT)

    # AUM badge
    aum_text = f"Portfolio Value: ${client['aum']:,.0f}"
    font_aum = load_font(26, bold=True)
    draw_rounded_rect(draw, [370, 410, 910, 460], 12, BG_CARD)
    bbox = draw.textbbox((0, 0), aum_text, font=font_aum)
    draw.text(((WIDTH - bbox[2]) // 2, 422), aum_text, font=font_aum, fill=ACCENT_GREEN)

    # Risk profile tag
    risk_text = f"Risk Profile: {client['risk_profile']}"
    font_risk = load_font(20)
    draw_rounded_rect(draw, [460, 480, 820, 520], 10, ACCENT_BLUE)
    bbox = draw.textbbox((0, 0), risk_text, font=font_risk)
    draw.text(((WIDTH - bbox[2]) // 2, 490), risk_text, font=font_risk, fill=WHITE)

    # Date and label
    from datetime import datetime
    date_str = datetime.now().strftime("Personalized Brief  •  %B %d, %Y")
    font_date = load_font(18)
    bbox = draw.textbbox((0, 0), date_str, font=font_date)
    draw.text(((WIDTH - bbox[2]) // 2, 580), date_str, font=font_date, fill=WHITE)

    # Bottom border
    draw.rectangle([0, HEIGHT - 4, WIDTH, HEIGHT], fill=ACCENT_BLUE)

    return img


# ── Slide 2: Portfolio Performance ────────────────────────────────────────────

def make_performance_slide(client: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)

    # Header
    font_title = load_font(36, bold=True)
    draw.text((60, 45), "Portfolio Performance", font=font_title, fill=WHITE)
    draw.rectangle([60, 90, 350, 93], fill=ACCENT_BLUE)

    # YTD Return vs Benchmark
    ytd = client["ytd_return"]
    bench = client["benchmark_return"]
    outperforming = ytd >= bench
    diff = abs(ytd - bench)

    font_label = load_font(20)
    font_big = load_font(72, bold=True)
    font_med = load_font(28, bold=True)

    # YTD card
    draw_rounded_rect(draw, [60, 115, 420, 310], 14, BG_CARD)
    draw.text((90, 130), "Your YTD Return", font=font_label, fill=GRAY_LIGHT)
    ytd_color = ACCENT_GREEN if ytd >= 0 else ACCENT_RED
    draw.text((90, 165), f"+{ytd}%" if ytd >= 0 else f"{ytd}%", font=font_big, fill=ytd_color)
    draw.text((90, 270), "Year-to-date", font=font_label, fill=GRAY_MED)

    # Benchmark card
    draw_rounded_rect(draw, [440, 115, 800, 310], 14, BG_CARD)
    draw.text((470, 130), "Benchmark Return", font=font_label, fill=GRAY_LIGHT)
    draw.text((470, 165), f"+{bench}%" if bench >= 0 else f"{bench}%", font=font_big, fill=GRAY_LIGHT)
    draw.text((470, 270), "S&P 500 / Blended Index", font=font_label, fill=GRAY_MED)

    # Performance delta badge
    delta_color = ACCENT_GREEN if outperforming else ACCENT_AMBER
    badge_text = f"{'Outperforming' if outperforming else 'Underperforming'} benchmark by {diff:.1f}%"
    draw_rounded_rect(draw, [820, 175, 1220, 260], 12, delta_color)
    font_badge = load_font(20, bold=True)
    lines = wrap_text(badge_text, font_badge, 360, draw)
    y_badge = 195
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_badge)
        draw.text((1020 - bbox[2] // 2, y_badge), line, font=font_badge, fill=WHITE)
        y_badge += 30

    # Holdings breakdown bars
    draw.text((60, 340), "Holdings Allocation", font=font_label, fill=GRAY_LIGHT)
    draw.rectangle([60, 365, 1220, 367], fill=GRAY_MED)

    colors = [ACCENT_BLUE, ACCENT_GREEN, ACCENT_AMBER, (236, 72, 153), (14, 165, 233)]
    y_pos = 385
    for i, holding in enumerate(client["holdings"][:5]):
        color = colors[i % len(colors)]
        name = holding["asset"]
        if len(name) > 40:
            name = name[:40] + "…"
        alloc = holding["allocation"]
        val = holding["value"]

        draw.text((60, y_pos), name, font=load_font(18), fill=GRAY_LIGHT)
        draw.text((730, y_pos), f"${val:,.0f}", font=load_font(18, bold=True), fill=WHITE)
        draw.text((920, y_pos), f"{alloc}%", font=load_font(18, bold=True), fill=color)
        draw_progress_bar(draw, 980, y_pos + 4, 220, 14, alloc, color)
        y_pos += 48

    draw.rectangle([0, HEIGHT - 4, WIDTH, HEIGHT], fill=ACCENT_BLUE)
    return img


# ── Slide 3: Market Context ────────────────────────────────────────────────────

def make_market_slide(market_data: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)

    font_title = load_font(36, bold=True)
    draw.text((60, 45), "Live Market Conditions", font=font_title, fill=WHITE)
    draw.rectangle([60, 90, 360, 93], fill=ACCENT_BLUE)

    from datetime import datetime
    font_time = load_font(16)
    draw.text((60, 103), f"As of {market_data.get('fetched_at', 'today')}", font=font_time, fill=GRAY_MED)

    factors = {k: v for k, v in market_data.items() if k != "fetched_at"}
    factor_list = list(factors.values())

    card_w = 360
    card_h = 200
    padding = 30
    start_x = 60
    start_y = 140

    for i, factor in enumerate(factor_list[:5]):
        col = i % 3
        row = i // 3
        x = start_x + col * (card_w + padding)
        y = start_y + row * (card_h + padding)

        if x + card_w > WIDTH:
            continue

        draw_rounded_rect(draw, [x, y, x + card_w, y + card_h], 14, BG_CARD)

        font_flabel = load_font(16)
        font_fval = load_font(38, bold=True)
        font_fchg = load_font(20)

        label = factor.get("label", "")
        value = factor.get("value", "N/A")
        chg = factor.get("change_pct", 0)
        impact = factor.get("impact", "neutral")
        unit = factor.get("unit", "")

        val_color = ACCENT_GREEN if impact == "positive" else ACCENT_RED if impact == "negative" else GRAY_LIGHT
        chg_color = ACCENT_GREEN if chg >= 0 else ACCENT_RED

        draw.text((x + 18, y + 16), label, font=font_flabel, fill=GRAY_MED)

        val_str = f"${value:,.0f}" if isinstance(value, (int, float)) and value > 1000 else f"{value}{unit}" if isinstance(value, (int, float)) else str(value)
        draw.text((x + 18, y + 45), val_str, font=font_fval, fill=val_color)

        chg_str = f"{'▲' if chg >= 0 else '▼'} {abs(chg):.2f}%"
        draw.text((x + 18, y + 110), chg_str, font=font_fchg, fill=chg_color)

        desc = factor.get("description", "")
        if len(desc) > 45:
            desc = desc[:45] + "…"
        draw.text((x + 18, y + 148), desc, font=load_font(14), fill=GRAY_MED)

    draw.rectangle([0, HEIGHT - 4, WIDTH, HEIGHT], fill=ACCENT_BLUE)
    return img


# ── Slide 4: Insights & Next Steps ────────────────────────────────────────────

def make_insights_slide(client: dict, brief: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)

    font_title = load_font(36, bold=True)
    draw.text((60, 45), "Key Insights & Next Steps", font=font_title, fill=WHITE)
    draw.rectangle([60, 90, 420, 93], fill=ACCENT_BLUE)

    # Market impact — box tall enough for 3 lines
    font_label = load_font(18)
    font_body = load_font(19)
    market_impact = brief.get("market_impact_summary", "")
    draw_rounded_rect(draw, [60, 110, 1220, 220], 10, BG_CARD)
    draw.text((80, 118), "Market Impact", font=font_label, fill=ACCENT_AMBER)
    mi_lines = wrap_text(_clean_display(market_impact), font_body, 1110, draw)
    for k, line in enumerate(mi_lines[:3]):
        draw.text((80, 140 + k * 26), line, font=font_body, fill=WHITE)

    # Talking points — show 3 only so they always fit above the banner
    draw.text((60, 235), "Our Recommendations", font=load_font(22, bold=True), fill=ACCENT_BLUE)
    talking_points = brief.get("advisor_talking_points", [])

    dot_colors = [ACCENT_GREEN, ACCENT_BLUE, ACCENT_AMBER, (236, 72, 153)]
    y_tp = 272
    for i, point in enumerate(talking_points[:3]):
        color = dot_colors[i % len(dot_colors)]
        draw.ellipse([60, y_tp + 6, 74, y_tp + 20], fill=color)
        # Use shortened display version so each bullet ends at a natural break point
        display_text = _shorten_tp_display(point)
        lines = wrap_text(display_text, font_body, 1100, draw)
        for j, line in enumerate(lines[:2]):
            draw.text((90, y_tp + j * 26), line, font=font_body, fill=WHITE if j == 0 else GRAY_LIGHT)
        y_tp += 70 + (len(lines[:2]) - 1) * 26

    # Next action banner — tall enough for 3 lines, with white label on green bg
    next_action = brief.get("next_action", "")
    banner_y0, banner_y1 = 560, 700
    draw_rounded_rect(draw, [60, banner_y0, 1220, banner_y1], 12, ACCENT_GREEN)
    draw.text((85, banner_y0 + 10), "Next Action",
              font=load_font(18, bold=True), fill=WHITE)
    na_lines = wrap_text(_clean_display(next_action), font_body, 1110, draw)
    for k, line in enumerate(na_lines[:3]):
        draw.text((85, banner_y0 + 36 + k * 30), line, font=font_body, fill=WHITE)

    draw.rectangle([0, HEIGHT - 4, WIDTH, HEIGHT], fill=ACCENT_BLUE)
    return img


# ── TTS helper — platform-aware: Windows=pyttsx3 first, Linux=gTTS first ──────

import sys as _sys
_IS_WINDOWS = _sys.platform == "win32"

def _tts_to_file(text: str, tmpdir: str, idx: int) -> str | None:
    """
    Returns path to generated audio file, or None if all methods fail.
    Windows: pyttsx3 (offline Zira, ~2s) → gTTS fallback
    Linux:   gTTS (30s timeout) → pyttsx3 fallback (usually unavailable)
    """
    wav_path = os.path.join(tmpdir, f"audio_{idx}.wav")
    mp3_path = os.path.join(tmpdir, f"audio_{idx}.mp3")

    def _try_pyttsx3():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 160)
            voices = engine.getProperty("voices") or []
            female_keywords = ["zira", "aria", "jenny", "hazel", "susan", "eva", "helena", "female"]
            male_keywords   = ["david", "mark", "richard", "george"]
            chosen = None
            for v in voices:
                if any(k in v.name.lower() for k in female_keywords):
                    chosen = v.id; break
            if not chosen:
                for v in voices:
                    if any(k in v.name.lower() for k in male_keywords):
                        chosen = v.id; break
            if chosen:
                engine.setProperty("voice", chosen)
            engine.save_to_file(text, wav_path)
            engine.runAndWait()
            engine.stop()
            del engine
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 500:
                return wav_path
        except Exception:
            return None

    def _try_gtts(timeout=30):
        success = [False]
        def _run():
            try:
                gTTS(text=text, lang="en", slow=False).save(mp3_path)
                success[0] = True
            except Exception:
                pass
        t = threading.Thread(target=_run, daemon=True)
        t.start(); t.join(timeout=timeout)
        if success[0] and os.path.exists(mp3_path):
            return mp3_path
        return None

    if _IS_WINDOWS:
        return _try_pyttsx3() or _try_gtts(timeout=15)
    else:
        return _try_gtts(timeout=30) or _try_pyttsx3()


# ── Main video generator ──────────────────────────────────────────────────────

def generate_video(client: dict, market_data: dict, brief: dict, output_path: str) -> str:
    """Generate an animated narrated video for the client brief."""

    # Use per-slide scripts if available (new format) — guarantees voice matches visuals.
    # Fall back to splitting video_script for any older cached briefs.
    if brief.get("slide_1_script"):
        parts = [
            brief.get("slide_1_script", ""),
            brief.get("slide_2_script", ""),
            brief.get("slide_3_script", ""),
            brief.get("slide_4_script", ""),
        ]
    else:
        script = brief.get("video_script", "") or brief.get("client_summary", "No summary.")
        words  = script.split()
        chunk  = max(len(words) // 4, 1)
        parts  = [
            " ".join(words[:chunk]),
            " ".join(words[chunk:chunk * 2]),
            " ".join(words[chunk * 2:chunk * 3]),
            " ".join(words[chunk * 3:]),
        ]

    # Always rebuild slide 4 narration — conversational, second-person, speech-friendly.
    import re as _re

    first_name = client.get("name", "").split()[0]

    def _to_2p(text: str) -> str:
        """Third-person → second-person for the client."""
        if first_name:
            text = _re.sub(rf"\b{_re.escape(first_name)}'s\b", "your", text, flags=_re.IGNORECASE)
            text = _re.sub(rf"\b{_re.escape(first_name)}\b",   "you",  text, flags=_re.IGNORECASE)
        text = _re.sub(r"\bhis\b", "your", text)
        text = _re.sub(r"\bhim\b", "you",  text)
        text = _re.sub(r"\bhe\b",  "you",  text)
        return text

    # Gerund converter so "Deploy" → "deploying" after "we recommend"
    _gerund_exc = {
        'commit': 'committing', 'run': 'running', 'set': 'setting',
        'get': 'getting', 'put': 'putting', 'begin': 'beginning',
        'plan': 'planning', 'add': 'adding', 'cut': 'cutting',
        'drop': 'dropping', 'sit': 'sitting', 'hit': 'hitting',
    }
    def _to_gerund(word: str) -> str:
        w = word.lower()
        if w in _gerund_exc:
            return _gerund_exc[w]
        if w.endswith('ing'):
            return w
        if w.endswith('e') and len(w) > 2 and not w.endswith('ee'):
            return w[:-1] + 'ing'
        return w + 'ing'

    def _tp_to_speech(text: str, idx: int) -> str:
        """
        Convert a verbose talking point to a short, natural spoken sentence.
        Extracts just the core action + primary amount + destination (≤ 16 words),
        converts the imperative verb to gerund, and prepends an ordinal.
        """
        ordinals = ["First,", "Second,", "And third,"]
        prefix = ordinals[idx % len(ordinals)]

        cleaned = _fmt_speech(_to_2p(text))

        # Cut at first clause separator so we only speak the core action
        stop_seps = [' - ', ' using ', ' through ', ' while ', ' targeting ',
                     ' consistent with ', ' building ', '; ']
        earliest = len(cleaned)
        for sep in stop_seps:
            pos = cleaned.find(sep)
            if 20 < pos < earliest:
                earliest = pos

        core = cleaned[:earliest].strip()

        # Hard cap at 16 words so we never over-speak
        words = core.split()
        core = ' '.join(words[:16]).rstrip('.,;:')

        # Convert first word to gerund ("Deploy" → "deploying")
        parts_core = core.split()
        if parts_core:
            parts_core[0] = _to_gerund(parts_core[0])
        core = ' '.join(parts_core)

        return f"{prefix} we recommend {core}."

    _tps    = brief.get("advisor_talking_points", [])
    _impact = brief.get("market_impact_summary",  "")
    _action = brief.get("next_action",             "")

    # Build a short, conversational slide 4 narration — NOT reading bullets word-for-word
    _s4 = ["Let me walk you through our key insights and recommendations."]

    if _impact:
        # Max 20 words of market context as a spoken intro
        _mi_words = _fmt_speech(_to_2p(_impact)).split()
        _mi_short = ' '.join(_mi_words[:20]).rstrip('.,;') + '.'
        _s4.append(_mi_short)

    if _tps:
        _s4.append(f"Based on this, here are our {"three" if len(_tps) >= 3 else "key"} recommendations.")
        for i, _tp in enumerate(_tps[:3]):
            _s4.append(_tp_to_speech(_tp, i))

    if _action:
        _act_clean = _fmt_speech(_to_2p(_action))
        _act_words = _act_clean.split()
        _act_short = ' '.join(_act_words[:15]).rstrip('.,;')
        _s4.append(f"Your next step is to {_act_short[0].lower()}{_act_short[1:]}.")

    _s4.append("We look forward to discussing all of this with you at our next meeting.")
    parts[3] = ' '.join(_s4)

    slides_fns = [make_cover_slide, make_performance_slide, make_market_slide, make_insights_slide]
    slide_args = [(client,), (client,), (market_data,), (client, brief)]

    with tempfile.TemporaryDirectory() as tmpdir:

        # Step 1: Generate all slide images (fast PIL, no network)
        img_paths = []
        for i, (fn, args) in enumerate(zip(slides_fns, slide_args)):
            path = os.path.join(tmpdir, f"slide_{i}.png")
            fn(*args).save(path)
            img_paths.append(path)

        # Step 2: Generate audio for each slide sequentially via _tts_to_file
        # pyttsx3 is near-instant so sequential is fine; avoids COM threading issues
        actual_audio = []
        for i, part in enumerate(parts):
            apath = _tts_to_file(part.strip(), tmpdir, i) if part.strip() else None
            actual_audio.append(apath)

        # Step 3: Build clips — duration is locked to real audio length (no drift)
        clips = []
        for i in range(4):
            apath = actual_audio[i]
            audio_clip = AudioFileClip(apath) if apath else None
            duration = (audio_clip.duration + 0.3) if audio_clip else 4.0

            if MOVIEPY_V2:
                img_clip = ImageClip(img_paths[i], duration=duration)
                if audio_clip:
                    img_clip = img_clip.with_audio(audio_clip)
            else:
                img_clip = ImageClip(img_paths[i]).set_duration(duration)
                if audio_clip:
                    img_clip = img_clip.set_audio(audio_clip)

            clips.append(img_clip)

        # Step 4: "chain" concatenation — no audio drift unlike "compose"
        final = concatenate_videoclips(clips, method="chain")
        final.write_videofile(
            output_path,
            fps=15,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            preset="ultrafast",
            threads=4,
            temp_audiofile=os.path.join(tmpdir, "temp_audio.m4a"),
        )

    return output_path
