"""
Builds the compact data payload the web tool ships with, and injects it into
template.html to produce the single self-contained index.html.

    python build_data.py

Payload per household:
    id, name, opening (tk), start (YYYY-MM-DD), units [ints, consecutive days],
    recharges [[date, amount], ...], today, daily (usual units/day), target,
    comparison { months, opening, threshold, lowAmount, monthlyAmount }
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import solve

OUT_JSON = "household_data.json"
TEMPLATE = "template.html"
INDEX = "index.html"


# --------------------------------------------------------------------------
# Item 1: a household built to order - six-plus months of daily readings with a
# light month, a heavy summer month, and a month whose big recharge lands in the
# last week. Deterministic, no randomness, so the numbers are reproducible.
# --------------------------------------------------------------------------
def demo_household():
    """Mirpur, Dhaka: four adults and two children, one AC used only in summer."""
    # Dec 2025 -> Jul 2026. Per-month (base weekday units, weekend bump, shape).
    profile = {
        "2025-12": 5,    # cool, fans off                    ~155 units
        "2026-01": 4,    # lightest month of the year        ~124 units
        "2026-02": 5,    #                                   ~140 units
        "2026-03": 9,    # fans on                           ~279 units
        "2026-04": 16,   # AC starts                         ~480 units
        "2026-05": 22,   # heavy summer month                ~682 units
        "2026-06": 20,   # monsoon, still hot                ~600 units
        "2026-07": 17,   #                                   ~527 units
    }
    days = []
    d = date(2025, 12, 1)
    end = date(2026, 7, 31)
    while d <= end:
        base = profile[f"{d.year:04d}-{d.month:02d}"]
        u = base + (2 if d.weekday() >= 4 else 0)          # heavier Fri/Sat/Sun
        u += (d.day % 3) - 1                               # small day-to-day wobble
        days.append((d.isoformat(), max(1, u)))
        d += timedelta(days=1)

    # Recharge history: small top-ups whenever the meter beeps. In June the family
    # lets it run down - the meter sits in arrears for four days - and then puts a
    # large amount in during the last week, every unit of it billed at the top slab.
    recharges = [
        ("2025-12-03", "500.00"), ("2025-12-16", "400.00"), ("2025-12-28", "400.00"),
        ("2026-01-11", "400.00"), ("2026-01-24", "400.00"),
        ("2026-02-06", "400.00"), ("2026-02-19", "500.00"),
        ("2026-03-04", "700.00"), ("2026-03-17", "700.00"), ("2026-03-29", "600.00"),
        ("2026-04-05", "1000.00"), ("2026-04-15", "1200.00"), ("2026-04-26", "1500.00"),
        ("2026-05-04", "2000.00"), ("2026-05-14", "2000.00"), ("2026-05-25", "2000.00"),
        ("2026-06-10", "1200.00"), ("2026-06-26", "4000.00"),   # big, late, expensive
        ("2026-07-07", "2000.00"), ("2026-07-20", "2000.00"),
    ]
    return dict(
        case_id="HOME-DHK",
        name="Mirpur household (built for item 1)",
        opening_balance_bdt="450.00",
        days=[dict(date=x, units=u) for x, u in days],
        recharges=[dict(date=x, amount_bdt=a) for x, a in recharges],
        today="2026-07-31",
        usual_daily_units=18,
        target_date="2026-08-31",
        comparison=dict(months=["2026-05", "2026-06", "2026-07"], source="readings",
                        daily_units=None, opening_balance_bdt="0.00",
                        low_threshold_bdt="150.00", low_amount_bdt="4000.00",
                        monthly_amount_bdt="2500.00"),
    )


def pack(case, name=None):
    days = case["days"]
    start = days[0]["date"]
    # readings are consecutive, so a start date plus a flat unit array is enough
    d0 = solve.parse_date(start)
    for i, x in enumerate(days):
        assert solve.parse_date(x["date"]) == d0 + timedelta(days=i), "gap in readings"
    c = case["comparison"]
    return dict(
        id=case["case_id"],
        name=name or f"Household {case['case_id'].split('-')[-1]}",
        opening=float(case["opening_balance_bdt"]),
        start=start,
        units=[int(x["units"]) for x in days],
        recharges=[[r["date"], float(r["amount_bdt"])] for r in case["recharges"]],
        today=case["today"],
        daily=int(case["usual_daily_units"]),
        target=case["target_date"],
        comparison=dict(months=c["months"],
                        source=c.get("source", "readings"),
                        dailyUnits=c.get("daily_units"),
                        opening=float(c["opening_balance_bdt"]),
                        threshold=float(c["low_threshold_bdt"]),
                        lowAmount=float(c["low_amount_bdt"]),
                        monthlyAmount=float(c["monthly_amount_bdt"])),
    )


def main():
    cases = solve.load_cases()
    payload = [pack(demo_household(), "Mirpur household — built for item 1")]
    payload += [pack(c) for c in cases]

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    blob = json.dumps(payload, separators=(",", ":"))
    print(f"{OUT_JSON}: {len(payload)} households, {len(blob) / 1024:.1f} KB")

    with open(TEMPLATE, encoding="utf-8") as fh:
        html = fh.read()
    assert "/*__DATA__*/" in html, "template is missing the /*__DATA__*/ marker"
    html = html.replace("/*__DATA__*/", blob)
    with open(INDEX, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"{INDEX}: {len(html) / 1024:.1f} KB")

    # the demo household must actually meet item 1's three conditions
    r = solve.solve_case(demo_household())
    months = list(r["sim"]["months"].values())
    light = min(months, key=lambda m: m["units"])
    heavy = max(months, key=lambda m: m["units"])
    late = [m for m in months
            if any(d.day >= 24 and amt >= 3000
                   for d, amt in r["recharges"].items()
                   if solve.ym(d) == m["month"])]
    print(f"  lightest month {light['month']} = {light['units']} units")
    print(f"  heaviest month {heavy['month']} = {heavy['units']} units")
    print(f"  big last-week recharge in {[m['month'] for m in late]}")
    assert len(months) >= 6 and light["units"] < 200 and heavy["units"] > 600 and late


if __name__ == "__main__":
    main()
