"""
P10 - runs all four required items over every case in the public case file.

    python solve.py                       # readable report for every case
    python solve.py PUB-01                # one case, in detail
    python solve.py --json results.json   # machine-readable results for all cases
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal as D

import engine as E
from engine import f2, money, parse_date, ym

CASE_FILE = "P10_prepaid_meter_public.json"


def load_cases(path=CASE_FILE):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def prep(case):
    days = [(parse_date(x["date"]), int(x["units"])) for x in case["days"]]
    recharges = {}
    for r in case["recharges"]:
        d = parse_date(r["date"])
        recharges[d] = recharges.get(d, D("0")) + D(str(r["amount_bdt"]))
    return days, recharges


def solve_case(case):
    days, recharges = prep(case)
    opening = D(str(case["opening_balance_bdt"]))
    today = parse_date(case["today"])
    target = parse_date(case["target_date"])
    daily = int(case["usual_daily_units"])

    # ---- item 2 : rebuild the balance day by day -------------------------------
    sim = E.simulate(days, recharges, opening)
    last = sim["ledger"][-1]
    assert last["date"] == today.isoformat(), "case 'today' is not the last reading date"
    balance_today = last["balance"]
    cum_today = last["cum_units_month"]

    # ---- item 3a : when does the balance run out -------------------------------
    runout = E.project_runout(today, balance_today, daily, cum_today)

    # ---- item 3b : what must go in today to reach the target date --------------
    fixed_due = ym(today) not in set(ym(d) for d in recharges)
    need = E.recharge_needed(today, target, balance_today, daily, cum_today, fixed_due)

    # ---- item 4 : two recharge habits, identical consumption -------------------
    comp = case["comparison"]
    cmonths = set(comp["months"])
    if comp.get("source") == "readings" or comp.get("daily_units") in (None, ""):
        cdays = [(d, u) for d, u in days if ym(d) in cmonths]
    else:                                     # synthetic flat consumption
        du = int(comp["daily_units"])
        cdays = [(d, du) for d, _ in days if ym(d) in cmonths]
    cdays.sort()
    habits = E.compare_habits(
        cdays,
        D(str(comp["opening_balance_bdt"])),
        D(str(comp["low_threshold_bdt"])),
        D(str(comp["low_amount_bdt"])),
        D(str(comp["monthly_amount_bdt"])),
    )

    return dict(case=case, days=days, recharges=recharges, sim=sim,
                balance_today=balance_today, cum_today=cum_today, today=today,
                target=target, daily=daily, runout=runout, need=need,
                fixed_due=fixed_due, habits=habits, comparison_days=cdays)


# ------------------------------------------------------------------ output ---
def tk(x):
    return f"{money(x):,}"


def report(r, verbose=False):
    c = r["case"]
    out = []
    p = out.append
    p(f"=== {c['case_id']} " + "=" * 52)
    sim = r["sim"]
    p(f"  readings   {r['days'][0][0]} -> {r['days'][-1][0]}  "
      f"({len(r['days'])} days, {sim['total_units']} units)")
    p(f"  opening    {tk(c['opening_balance_bdt'])} tk    "
      f"recharges {len(c['recharges'])} totalling {tk(sim['total_recharged'])} tk")

    p("  -- item 2 : rebuilt ledger ------------------------------------------")
    p(f"     energy {tk(sim['total_energy'])} + VAT {tk(sim['total_vat'])} "
      f"+ fixed {tk(sim['total_fixed'])} = {tk(sim['total_cost'])} tk consumed")
    p(f"     balance on {r['today']} : {tk(r['balance_today'])} tk"
      f"   (month-to-date {r['cum_today']} units, slab "
      f"{E.slab_label(E.slab_index(r['cum_today']))} @ "
      f"{E.SLABS[E.slab_index(r['cum_today'])][1]} tk/unit)")
    p("     month        units   energy      VAT     fixed   recharged  end balance")
    for m in sim["months"].values():
        endbal = [x["balance"] for x in sim["ledger"] if x["month"] == m["month"]][-1]
        p(f"     {m['month']}   {m['units']:6d} {money(m['energy']):>9} "
          f"{money(m['vat']):>8} {money(m['fixed']):>9} {money(m['recharged']):>11} "
          f"{money(endbal):>12}")

    p("  -- item 3a : when does the balance run out ---------------------------")
    ro = r["runout"]
    if ro["already_empty"]:
        p(f"     balance is already {tk(r['balance_today'])} tk - the meter is out now")
    elif ro["runout_date"]:
        p(f"     at {r['daily']} units/day with no recharge, {tk(r['balance_today'])} tk "
          f"runs out on {ro['runout_date']} ({ro['days_left']} days from {r['today']})")
    else:
        p("     does not run out inside the projection horizon")

    p("  -- item 3b : recharge today to last until the target date ------------")
    n = r["need"]
    p(f"     target {r['target']}  ({n['days_covered']} days, {n['units']} units "
      f"at {r['daily']}/day)")
    p(f"     energy at first-slab rate 4.63 ..... {money(n['energy_at_base']):>10}")
    p(f"     extra from higher slabs ............ {money(n['slab_premium']):>10}")
    p(f"     fixed (demand 42 + rent 40) ........ {money(n['fixed']):>10}"
      + ("" if r["fixed_due"] else "   (already taken this month)"))
    p(f"     VAT 5% of energy ................... {money(n['vat']):>10}")
    p(f"     total needed ....................... {money(n['gross']):>10}")
    bal = n["balance_credit"]
    label = "plus arrears to clear" if bal < 0 else "less balance in hand"
    p(f"     {(label + ' ').ljust(36, '.')} {money(-bal):>10}")
    p(f"     RECHARGE TODAY ..................... {money(n['amount']):>10} tk")

    p("  -- item 4 : two habits, identical consumption ------------------------")
    h = r["habits"]
    cm = c["comparison"]
    p(f"     months {', '.join(cm['months'])}  |  identical units: "
      f"{h['low_balance']['total_units']} both sides "
      f"({'energy equal' if h['energy_identical'] else 'ENERGY DIFFERS - BUG'})")
    p(f"     low-balance : recharge {tk(cm['low_amount_bdt'])} whenever balance < "
      f"{tk(cm['low_threshold_bdt'])}")
    p(f"        {len(h['low_recharges'])} recharges, fixed charges in "
      f"{h['fixed_months_low']} month(s) -> cost {tk(h['low_balance']['total_cost'])} tk")
    p(f"     monthly     : recharge {tk(cm['monthly_amount_bdt'])} on the 1st")
    p(f"        {len(h['monthly_recharges'])} recharges, fixed charges in "
      f"{h['fixed_months_monthly']} month(s) -> cost {tk(h['monthly']['total_cost'])} tk")
    if h["cheaper"] == "equal":
        p("     VERDICT: the two habits cost exactly the same "
          f"({tk(h['low_balance']['total_cost'])} tk) - same units, same slabs, "
          "same number of monthly fixed charges")
    else:
        name = "low-balance" if h["cheaper"] == "low_balance" else "monthly"
        p(f"     VERDICT: {name} is cheaper by {tk(h['saving'])} tk "
          f"(energy and VAT are identical; the whole difference is "
          f"{h['fixed_months_low']} vs {h['fixed_months_monthly']} monthly fixed charges)")

    if verbose:
        p("  -- daily ledger ------------------------------------------------------")
        p("     date         units  cum   slab      energy    VAT  recharge  fixed"
          "     balance")
        for x in sim["ledger"]:
            p(f"     {x['date']}  {x['units']:4d} {x['cum_units_month']:5d}  "
              f"{E.slab_label(x['slab']):>8}  {money(x['energy']):>8} "
              f"{money(x['vat']):>6} {money(x['recharge']):>9} "
              f"{money(x['fixed']):>6} {money(x['balance']):>11}")
    return "\n".join(out)


def to_json(r):
    c = r["case"]
    sim = r["sim"]
    h = r["habits"]
    n = r["need"]
    ro = r["runout"]
    return dict(
        case_id=c["case_id"],
        item2=dict(
            end_balance_bdt=f2(sim["end_balance"]),
            balance_on_today_bdt=f2(r["balance_today"]),
            month_to_date_units=r["cum_today"],
            total_units=sim["total_units"],
            total_energy_bdt=f2(sim["total_energy"]),
            total_vat_bdt=f2(sim["total_vat"]),
            total_fixed_bdt=f2(sim["total_fixed"]),
            total_cost_bdt=f2(sim["total_cost"]),
            total_recharged_bdt=f2(sim["total_recharged"]),
            months=[dict(month=m["month"], units=m["units"], energy_bdt=f2(m["energy"]),
                         vat_bdt=f2(m["vat"]), demand_charge_bdt=f2(m["demand"]),
                         meter_rent_bdt=f2(m["rent"]),
                         bill_bdt=f2(m["energy"] + m["vat"] + m["fixed"]),
                         recharged_bdt=f2(m["recharged"]),
                         recharges=m["recharge_count"])
                    for m in sim["months"].values()],
            daily=[dict(date=x["date"], units=x["units"], cum_units_month=x["cum_units_month"],
                        slab=E.slab_label(x["slab"]), energy_bdt=f2(x["energy"]),
                        vat_bdt=f2(x["vat"]), recharge_bdt=f2(x["recharge"]),
                        fixed_bdt=f2(x["fixed"]), balance_bdt=f2(x["balance"]))
                   for x in sim["ledger"]],
        ),
        item3a=dict(today=c["today"], balance_bdt=f2(r["balance_today"]),
                    usual_daily_units=r["daily"], runout_date=ro["runout_date"],
                    days_left=ro["days_left"], already_empty=ro["already_empty"]),
        item3b=dict(target_date=c["target_date"], days_covered=n["days_covered"],
                    units=n["units"],
                    energy_at_base_rate_bdt=f2(n["energy_at_base"]),
                    higher_slab_part_bdt=f2(n["slab_premium"]),
                    energy_total_bdt=f2(n["energy"]),
                    demand_charge_bdt=f2(n["demand"]), meter_rent_bdt=f2(n["rent"]),
                    fixed_bdt=f2(n["fixed"]), vat_bdt=f2(n["vat"]),
                    total_required_bdt=f2(n["gross"]),
                    balance_in_hand_bdt=f2(n["balance_credit"]),
                    recharge_today_bdt=f2(n["amount"])),
        item4=dict(
            months=c["comparison"]["months"],
            units_both=h["low_balance"]["total_units"],
            low_balance=dict(cost_bdt=f2(h["low_balance"]["total_cost"]),
                             energy_bdt=f2(h["low_balance"]["total_energy"]),
                             vat_bdt=f2(h["low_balance"]["total_vat"]),
                             fixed_bdt=f2(h["low_balance"]["total_fixed"]),
                             fixed_months=h["fixed_months_low"],
                             recharges=len(h["low_recharges"]),
                             deposited_bdt=f2(h["low_balance"]["total_recharged"]),
                             end_balance_bdt=f2(h["low_balance"]["end_balance"])),
            monthly=dict(cost_bdt=f2(h["monthly"]["total_cost"]),
                         energy_bdt=f2(h["monthly"]["total_energy"]),
                         vat_bdt=f2(h["monthly"]["total_vat"]),
                         fixed_bdt=f2(h["monthly"]["total_fixed"]),
                         fixed_months=h["fixed_months_monthly"],
                         recharges=len(h["monthly_recharges"]),
                         deposited_bdt=f2(h["monthly"]["total_recharged"]),
                         end_balance_bdt=f2(h["monthly"]["end_balance"])),
            cheaper=h["cheaper"], saving_bdt=f2(h["saving"]),
            energy_identical=h["energy_identical"]),
    )


def main(argv):
    cases = load_cases()
    if "--json" in argv:
        i = argv.index("--json")
        path = argv[i + 1] if len(argv) > i + 1 else "results.json"
        out = [to_json(solve_case(c)) for c in cases]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(dict(problem_id="P10", results=out), fh, indent=1)
        print(f"wrote {path} ({len(out)} cases)")
        return
    wanted = [a for a in argv if a.startswith("PUB-")]
    verbose = "-v" in argv
    for c in cases:
        if wanted and c["case_id"] not in wanted:
            continue
        print(report(solve_case(c), verbose=verbose))
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
