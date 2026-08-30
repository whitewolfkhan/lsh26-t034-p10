"""
Self-checks for the P10 engine. Run: python tests.py
Every number here is hand-computed from the tariff in the problem statement.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal as D

import engine as E
import solve

ok = 0
fail = []


def eq(name, got, want):
    global ok
    try:
        same = D(str(got)) == D(str(want))
    except Exception:
        same = str(got) == str(want)
    if same:
        ok += 1
    else:
        fail.append(f"{name}: got {got}, want {want}")


def true(name, cond):
    global ok
    if cond:
        ok += 1
    else:
        fail.append(f"{name}: expected True")


# ---------------------------------------------------------- slab pricing ----
eq("75 units", E.energy_cost(0, 75)[0], "347.25")                    # 75*4.63
eq("76 units", E.energy_cost(0, 76)[0], "352.51")                    # +5.26
eq("200 units", E.energy_cost(0, 200)[0],
   D("75") * D("4.63") + D("125") * D("5.26"))
eq("300 units", E.energy_cost(0, 300)[0],
   D("75") * D("4.63") + D("125") * D("5.26") + D("100") * D("5.63"))
eq("601st unit", E.rate_for_unit(601), "10.70")
eq("600th unit", E.rate_for_unit(600), "9.30")
# a day that straddles a boundary is split, not billed wholly at one rate (A1)
eq("straddle 74+4", E.energy_cost(74, 4)[0], D("4.63") + D("3") * D("5.26"))
eq("slab index at 75", E.slab_index(75), 1)
eq("slab index at 74", E.slab_index(74), 0)

# ------------------------------------------------- month reset + fixed ------
days = [(date(2026, 1, i + 1), 10) for i in range(31)] + \
       [(date(2026, 2, i + 1), 10) for i in range(28)]
sim = E.simulate(days, {date(2026, 1, 5): D("3000"), date(2026, 1, 20): D("500"),
                        date(2026, 2, 3): D("2000")}, D("0"))
# 310 units in January: 75@4.63 + 125@5.26 + 100@5.63 + 10@5.83
jan = D("75") * D("4.63") + D("125") * D("5.26") + D("100") * D("5.63") + D("10") * D("5.83")
eq("jan energy", sim["months"]["2026-01"]["energy"], jan)
# February restarts at unit 1, so 280 units: 75@4.63 + 125@5.26 + 80@5.63
feb = D("75") * D("4.63") + D("125") * D("5.26") + D("80") * D("5.63")
eq("feb energy (counter reset)", sim["months"]["2026-02"]["energy"], feb)
eq("fixed taken twice, not thrice", sim["total_fixed"], "164.00")
eq("jan fixed once despite 2 recharges", sim["months"]["2026-01"]["fixed"], "82.00")
eq("ledger reconciles",
   E.money(sim["end_balance"]),
   E.money(sim["total_recharged"] - sim["total_cost"]))
eq("vat is 5% of energy", sim["total_vat"], sim["total_energy"] * D("0.05"))

# a month with no recharge carries no fixed charge (A3)
sim2 = E.simulate(days, {date(2026, 1, 5): D("6000")}, D("0"))
eq("no recharge in feb -> no fixed", sim2["months"]["2026-02"]["fixed"], "0.00")
eq("same energy either way", sim2["total_energy"], sim["total_energy"])

# ------------------------------------------------------------- run-out ------
# 100 tk left, 5 units/day starting fresh: 5*4.63*1.05 = 24.3075 a day -> day 5 hits 0
ro = E.project_runout(date(2026, 1, 31), D("100"), 5, 0)
eq("runout day count", ro["days_left"], 5)
eq("runout date", ro["runout_date"], date(2026, 2, 5).isoformat())

# ---------------------------------------------------- recharge needed -------
n = E.recharge_needed(date(2026, 1, 31), date(2026, 2, 10), D("0"), 10, 0, True)
# 10 days x 10 units = 100 units in February: 75@4.63 + 25@5.26
energy = D("75") * D("4.63") + D("25") * D("5.26")
eq("need energy", n["energy"], energy)
eq("need base part", n["energy_at_base"], D("100") * D("4.63"))
eq("need slab premium", n["slab_premium"], energy - D("100") * D("4.63"))
eq("need vat", n["vat"], energy * D("0.05"))
eq("need fixed", n["fixed"], "82.00")
eq("parts sum to gross",
   n["energy_at_base"] + n["slab_premium"] + n["fixed"] + n["vat"], n["gross"])
eq("amount = gross - balance", n["amount"], n["gross"])
# with balance in hand the amount drops by exactly that much
n2 = E.recharge_needed(date(2026, 1, 31), date(2026, 2, 10), D("200"), 10, 0, True)
eq("balance credited", n2["amount"], n["gross"] - D("200"))

# ------------------------------------------------- habit comparison ---------
cdays = [(date(2026, 4, 1) + timedelta(days=i), 15) for i in range(30)] + \
        [(date(2026, 5, 1) + timedelta(days=i), 15) for i in range(31)] + \
        [(date(2026, 6, 1) + timedelta(days=i), 15) for i in range(30)]
h = E.compare_habits(cdays, D("0"), D("100"), D("2000"), D("2000"))
true("energy identical across habits", h["energy_identical"])
true("vat identical across habits", h["vat_identical"])
eq("difference is only fixed charges",
   h["cost_difference"],
   h["low_balance"]["total_fixed"] - h["monthly"]["total_fixed"])
eq("difference is a multiple of 82",
   D(h["cost_difference"]) % D("82"), 0)
eq("same units both habits",
   h["low_balance"]["total_units"], h["monthly"]["total_units"])

# ------------------------------------------------- every public case --------
cases = solve.load_cases()
for c in cases:
    r = solve.solve_case(c)
    sim = r["sim"]
    cid = c["case_id"]
    eq(f"{cid} reconciles", E.money(sim["end_balance"]),
       E.money(D(str(c["opening_balance_bdt"])) + sim["total_recharged"] - sim["total_cost"]))
    eq(f"{cid} vat", sim["total_vat"], sim["total_energy"] * D("0.05"))
    eq(f"{cid} fixed = 82 per month with a recharge", sim["total_fixed"],
       D("82") * sum(1 for m in sim["months"].values() if m["recharge_count"] > 0))
    h = r["habits"]
    true(f"{cid} item4 energy identical", h["energy_identical"])
    true(f"{cid} item4 vat identical", h["vat_identical"])
    eq(f"{cid} item4 units identical",
       h["low_balance"]["total_units"], h["monthly"]["total_units"])
    eq(f"{cid} item4 difference is fixed charges only", h["cost_difference"],
       h["low_balance"]["total_fixed"] - h["monthly"]["total_fixed"])
    n = r["need"]
    eq(f"{cid} item3b parts sum",
       n["energy_at_base"] + n["slab_premium"] + n["fixed"] + n["vat"], n["gross"])
    # recharging exactly the advised amount really does reach the target date
    if n["amount"] > 0:
        check = E.project_runout(r["today"], r["balance_today"] + n["amount"] - n["fixed"],
                                 r["daily"], r["cum_today"])
        reached = check["runout_date"] is None or \
            E.parse_date(check["runout_date"]) >= r["target"]
        true(f"{cid} item3b advice reaches the target date", reached)

print(f"{ok} checks passed" + (f", {len(fail)} FAILED" if fail else ""))
for f in fail:
    print("  FAIL", f)
raise SystemExit(1 if fail else 0)
