"""Trace tier-matching internals for a given player id."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.data.repository import JsonRepository
from app.fairness.stats_value import stats_value
from app.fairness.tier import tier_stats_value, _peak_recent, _matches, assign_tier

repo = JsonRepository()
rubric = repo.get_rubric()
for pid in sys.argv[1:] or ["gaffoda01"]:
    p = repo.get_player(pid)
    if not p:
        print(f"{pid}: not found")
        continue
    sv = stats_value(p)
    tsv = tier_stats_value(p, sv)
    peak_bpm = _peak_recent(p, "bpm")
    print(f"\n=== {p.name} (age {p.age}) ===")
    print(f"  raw stats_value      = {sv:.2f}")
    print(f"  tier_stats_value     = {tsv:.2f}  (used for tier matching)")
    print(f"  current_bpm          = {p.stats.bpm:.2f}")
    print(f"  peak_recent_bpm      = {peak_bpm:.2f}")
    for rule in sorted(rubric.rules, key=lambda r: r.tier):
        m = _matches(rule, p, tsv, sv)
        print(f"    rule T{rule.tier} ({rule.label}) min_sv={rule.min_stats_value} min_bpm={rule.min_bpm} -> matches={m}")
    tier, label = assign_tier(p, rubric)
    print(f"  ASSIGNED TIER: {tier} {label}")
