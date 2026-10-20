"""
SELF-IMPROVEMENT ENGINE
========================
Analyses outcomes.csv each morning to:
  1. Calculate hit rates by category and edge bucket
  2. Identify what's working vs what's not
  3. Adjust probability model confidence multipliers
  4. Optionally call Claude AI for pattern insight
  5. Log every threshold/model change with a reason
"""

import json
import datetime
import os
from pathlib import Path

import config
from outcomes import hit_rate_summary, read_all
from logger import log

MODELS_JSON    = config.MODELS_JSON
AI_JSON        = config.AI_SUGGESTIONS
CHANGES_LOG    = config.BASE_DIR / "model_changes.log"
MIN_SAMPLE     = 10   # minimum outcomes before adjusting a model


def load_models() -> dict:
    config.DATA_DIR.mkdir(exist_ok=True)
    if MODELS_JSON.exists():
        try:
            return json.loads(MODELS_JSON.read_text())
        except Exception:
            pass
    return _default_models()


def save_models(models: dict) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    MODELS_JSON.write_text(json.dumps(models, indent=2))


def _default_models() -> dict:
    return {
        "version": 1,
        "updated_at": "",
        "category_confidence": {
            # Multiplier applied to our model's edge estimate for each category.
            # 1.0 = trust the model. < 1.0 = shrink toward implied prob.
            "Crypto":     1.0,
            "Financials": 1.0,
            "Economics":  1.0,
            "Weather":    0.7,   # rough model — start conservative
        },
        "min_edge_overrides": {
            # Per-category minimum edge override (None = use global config)
        },
        "notes": [],
    }


def _log_change(reason: str) -> None:
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    line = f"[{ts}] {reason}"
    log(f"MODEL CHANGE: {reason}")
    with open(CHANGES_LOG, "a") as f:
        f.write(line + "\n")


def run_statistical_improvement() -> dict:
    """
    Analyse outcomes and adjust category_confidence multipliers.
    Returns summary of changes made.
    """
    summary = hit_rate_summary()
    models  = load_models()
    changes = []

    # Judge each category by realized ROI per DISTINCT market, priced on the
    # side actually bet. Raw hit rate was misleading twice over: duplicate
    # daily re-alerts inflated samples ~6x, and a NO bet at 90c needs a 90%+
    # hit rate just to break even, so "hit rate >= 65% = good" was meaningless.
    from outcomes import read_all, realized_return
    first = {}
    for r in read_all():
        if (r.get("outcome") or "").strip() in ("0", "1"):
            first.setdefault(r.get("ticker"), r)
    by_cat: dict = {}
    for r in first.values():
        c = (r.get("category") or "Unknown").strip() or "Unknown"
        d = by_cat.setdefault(c, {"n": 0, "ret": 0.0})
        d["n"]   += 1
        d["ret"] += realized_return(r.get("direction"), r.get("implied_prob"), r["outcome"] == "1")

    for cat, d in by_cat.items():
        count = d["n"]
        if count < MIN_SAMPLE:
            continue
        roi = d["ret"] / count * 100            # % return per $1 staked
        current_conf = models["category_confidence"].get(cat, 1.0)

        if roi >= 5:
            new_conf = min(1.2, current_conf + 0.05)
        elif roi <= -5:
            new_conf = max(0.3, current_conf - 0.10)
        else:
            continue
        if abs(new_conf - current_conf) > 0.01:
            reason = (f"Category {cat}: ROI {roi:+.1f}% over {count} distinct markets "
                      f"→ confidence {current_conf:.2f} → {new_conf:.2f}")
            _log_change(reason)
            models["category_confidence"][cat] = round(new_conf, 3)
            changes.append(reason)

    models["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    models["notes"].append({
        "date":    datetime.datetime.utcnow().strftime("%Y-%m-%d"),
        "changes": changes if changes else ["No adjustments needed"],
    })
    models["notes"] = models["notes"][-30:]   # keep 30 days of notes

    save_models(models)
    log(f"Self-improvement: {len(changes)} model adjustments made")
    return {"changes": changes, "summary": summary}


def run_ai_brain() -> str:
    """
    Call Claude API with recent outcomes to identify patterns.
    Returns the AI's insight as a string (saved to ai_suggestions.json).
    Requires ANTHROPIC_API_KEY env var.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log("No ANTHROPIC_API_KEY — skipping AI brain")
        return ""

    try:
        import anthropic
    except ImportError:
        log("anthropic package not installed — skipping AI brain", "WARN")
        return ""

    rows = read_all()
    rated = [r for r in rows if r.get("outcome") in ("0", "1")]

    if len(rated) < 10:
        log(f"AI brain: only {len(rated)} rated outcomes — need 10+ to analyse")
        return ""

    # Build a concise summary for the AI
    recent = rated[-50:]   # last 50 rated outcomes
    outcome_lines = []
    for r in recent:
        outcome_lines.append(
            f"  {r['ticker']} | {r['category']} | edge={r['edge_pct']}% "
            f"| conf={r['confidence']} | result={'✅' if r['outcome']=='1' else '❌'}"
        )

    prompt = f"""You are the brain of a Kalshi prediction market trading bot.
Below are the last {len(recent)} rated trade outcomes (alerts the bot fired,
rated correct ✅ or incorrect ❌):

{chr(10).join(outcome_lines)}

Analyse this data and provide:
1. PATTERNS: What signal types / categories / edge sizes are working?
2. STOP: What should the bot stop doing based on this data?
3. TEST: One specific thing to test today (a new filter, threshold, or pattern to watch).
4. CONFIDENCE: Are the models calibrated? (Do 70% confidence calls win ~70% of the time?)

Be specific, data-driven, and concise. Max 300 words total."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model   = "claude-opus-4-6",
            max_tokens = 500,
            messages = [{"role": "user", "content": prompt}],
        )
        ai_text = msg.content[0].text.strip()
        log(f"AI brain response received ({len(ai_text)} chars)")

        # Save to JSON for dashboard
        config.DATA_DIR.mkdir(exist_ok=True)
        ai_data = {
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "text":         ai_text,
            "n_outcomes":   len(rated),
        }
        AI_JSON.write_text(json.dumps(ai_data, indent=2))
        return ai_text

    except Exception as exc:
        log(f"AI brain API error: {exc}", "WARN")
        return ""


def run_morning_analysis() -> dict:
    """Main entry point for the 8am self-improvement run."""
    log("Running morning self-improvement analysis")

    # Statistical improvement
    stat_result = run_statistical_improvement()

    # AI brain (if key available + enough data)
    ai_text = run_ai_brain()

    return {
        "stat_changes": stat_result["changes"],
        "hit_rate_summary": stat_result["summary"],
        "ai_summary": ai_text,
    }
