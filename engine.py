"""
P10 - Prepaid Meter Recharge Advisor : tariff engine.

The tariff is fixed by the problem statement and is NOT read from any external source.

  Slabs (per calendar month, on the month's cumulative units):
      units    1 -  75 : 4.63 tk/unit
      units   76 - 200 : 5.26
      units  201 - 300 : 5.63
      units  301 - 400 : 5.83
      units  401 - 600 : 9.30
      units  601 +     : 10.70
  Demand charge : 42.00 tk, once a month, on the first recharge of that month
  Meter rent    : 40.00 tk, once a month, on the first recharge of that month
  VAT           : 5% of the energy amount
  The slab counter resets on the 1st of each calendar month. A recharge does NOT reset it.

Modelling decisions (documented, applied everywhere):
  A1. Slab pricing is positional / marginal: unit #75 of a month costs 4.63 and unit #76
      costs 5.26, so a single day's consumption is split across a slab boundary when it
      crosses one. Direct reading of "units 1 to 75 in a month cost 4.63 taka each".
  A2. Within a day a recharge is credited at the START of the day, then that day's energy
      is deducted. Ruling R-33 defines the habit comparison this way; the historical
      rebuild uses the same order so every part of the tool is consistent.
  A3. Demand charge + meter rent (82.00 tk together) are deducted at the moment of the
      first recharge of a calendar month. A month with no recharge in it carries no fixed
      charge. This is the only thing that can make the two habits in item 4 differ.
  A4. VAT is 5% of the energy amount only, exactly as written. It is not applied to the
      demand charge or the meter rent.
  A5. The balance is allowed to go negative in the rebuild; a real meter would cut off,
      but clamping would hide the arrears the family actually ran up.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

D = Decimal

# ---------------------------------------------------------------- tariff ----
SLABS = [
    (75,   D("4.63")),    # units 1..75
    (200,  D("5.26")),    # units 76..200
    (300,  D("5.63")),    # units 201..300
    (400,  D("5.83")),    # units 301..400
    (600,  D("9.30")),    # units 401..600
    (None, D("10.70")),   # units 601+
]
DEMAND_CHARGE = D("42.00")
METER_RENT = D("40.00")
FIXED_MONTHLY = DEMAND_CHARGE + METER_RENT       # 82.00, on first recharge of a month
VAT_RATE = D("0.05")                             # on the energy amount
BASE_RATE = SLABS[0][1]                          # 4.63 - the "no higher slab" reference


def rate_for_unit(n: int) -> Decimal:
    """Price of the n-th unit (1-based) of a calendar month."""
    for upper, rate in SLABS:
        if upper is None or n <= upper:
            return rate
    raise AssertionError


def slab_index(cum_units: int) -> int:
    """Index of the slab the NEXT unit falls into, given cum_units already used."""
    n = cum_units + 1
    for i, (upper, _) in enumerate(SLABS):
        if upper is None or n <= upper:
            return i
    raise AssertionError


def slab_label(i: int) -> str:
    lo = 1 if i == 0 else SLABS[i - 1][0] + 1
    hi = SLABS[i][0]
    return f"{lo}-{hi}" if hi is not None else f"{lo}+"


def slab_bounds(i: int):
    lo = 1 if i == 0 else SLABS[i - 1][0] + 1
    return lo, SLABS[i][0]


def energy_cost(cum_before: int, units: int):
    """
    Cost of consuming `units` when `cum_before` units are already on this month's counter.
    Splits across slab boundaries (assumption A1).
    Returns (cost, [(slab_index, units_in_slab, rate, cost_in_slab), ...]).
    """
    cost = D("0")
    parts = []
    n = cum_before
    left = units
    while left > 0:
        i = slab_index(n)
        upper = SLABS[i][0]
        take = left if upper is None else min(left, upper - n)
        rate = SLABS[i][1]
        c = rate * take
        parts.append((i, take, rate, c))
        cost += c
        n += take
        left -= take
    return cost, parts


def money(x) -> Decimal:
    return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def f2(x) -> float:
    return float(money(x))


# ------------------------------------------------------------ date helpers --
def parse_date(s: str) -> date:
    y, m, d = (int(p) for p in s.split("-"))
    return date(y, m, d)


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def ym(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


# ------------------------------------------------------------- simulation ---
def new_month_row(key):
    return dict(month=key, units=0, energy=D("0"), vat=D("0"), fixed=D("0"),
                demand=D("0"), rent=D("0"), recharged=D("0"), recharge_count=0)


def simulate(days, recharges, opening_balance, fixed_months_seen=None, cum_start=0):
    """
    Day-by-day rebuild of the meter balance.

    days            : list of (date, units), consecutive
    recharges       : dict date -> Decimal amount, credited at the start of the day
    opening_balance : Decimal, balance before the first day
    fixed_months_seen : months ('YYYY-MM') whose fixed charge was already taken before
                        this window, so a recharge inside the window does not re-take it
    cum_start       : units already on the slab counter for the first day's month
    """
    bal = D(opening_balance)
    fixed_taken = set(fixed_months_seen or ())
    cum = cum_start
    cur_month = None
    ledger = []
    months = OrderedDict()
    tot = dict(energy=D("0"), vat=D("0"), fixed=D("0"), recharged=D("0"), units=0)

    for d, units in days:
        key = ym(d)
        if key != cur_month:                       # slab counter resets on the 1st
            if cur_month is not None:
                cum = 0
            cur_month = key
            months.setdefault(key, new_month_row(key))
        m = months[key]

        # --- start of day: recharge (A2) ---
        rec = D(recharges.get(d, 0))
        fixed_today = D("0")
        if rec > 0:
            bal += rec
            tot["recharged"] += rec
            m["recharged"] += rec
            m["recharge_count"] += 1
            if key not in fixed_taken:             # first recharge of this month (A3)
                fixed_taken.add(key)
                fixed_today = FIXED_MONTHLY
                bal -= fixed_today
                tot["fixed"] += fixed_today
                m["fixed"] += fixed_today
                m["demand"] += DEMAND_CHARGE
                m["rent"] += METER_RENT

        # --- consumption ---
        cum_before = cum
        e, parts = energy_cost(cum_before, units)
        v = e * VAT_RATE
        bal -= (e + v)
        cum += units
        tot["energy"] += e
        tot["vat"] += v
        tot["units"] += units
        m["units"] += units
        m["energy"] += e
        m["vat"] += v

        ledger.append(dict(
            date=d.isoformat(), month=key, units=units,
            cum_before=cum_before, cum_units_month=cum,
            recharge=rec, fixed=fixed_today,
            demand=DEMAND_CHARGE if fixed_today else D("0"),
            rent=METER_RENT if fixed_today else D("0"),
            energy=e, vat=v, day_cost=e + v + fixed_today,
            slab=slab_index(cum - 1) if units else slab_index(cum),
            balance=bal, parts=parts,
        ))

    return dict(
        ledger=ledger, months=months, end_balance=bal,
        total_energy=tot["energy"], total_vat=tot["vat"], total_fixed=tot["fixed"],
        total_recharged=tot["recharged"], total_units=tot["units"],
        total_cost=tot["energy"] + tot["vat"] + tot["fixed"],
        fixed_months=sorted(fixed_taken),
    )


# --------------------------------------------------- item 3: run-out date ---
def project_runout(start_after: date, balance, daily_units: int,
                   cum_month_units: int, horizon_days: int = 3650):
    """
    From the day after `start_after`, burn `daily_units` a day with no further recharge
    (so no further fixed charges - they are only taken on a recharge) and find the day the
    balance runs out: the first day whose end-of-day balance is <= 0, i.e. the first day
    the meter can no longer pay for in full.

    `cum_month_units` is the month-to-date counter as of `start_after`, so the slab
    position carries over correctly and resets on the 1st.
    """
    bal = D(balance)
    cum = cum_month_units
    d = start_after + timedelta(days=1)
    month = ym(start_after)
    rows = []
    if bal <= 0:
        return dict(runout_date=None, already_empty=True, days_left=0, rows=[],
                    last_full_day=None)
    for _ in range(horizon_days):
        if ym(d) != month:
            month = ym(d)
            cum = 0
        e, _ = energy_cost(cum, daily_units)
        v = e * VAT_RATE
        bal -= (e + v)
        cum += daily_units
        rows.append(dict(date=d.isoformat(), units=daily_units, energy=e, vat=v,
                         balance=bal, cum_units_month=cum))
        if bal <= 0:
            return dict(runout_date=d.isoformat(), already_empty=False,
                        days_left=len(rows), rows=rows,
                        last_full_day=(d - timedelta(days=1)).isoformat())
        d += timedelta(days=1)
    return dict(runout_date=None, already_empty=False, days_left=None, rows=rows,
                last_full_day=None)


# ------------------------------- item 3: recharge needed to reach a target ---
def recharge_needed(today: date, target: date, balance, daily_units: int,
                    cum_month_units: int, fixed_due: bool):
    """
    Cost of covering every day from today+1 through `target` at `daily_units` a day, and
    the recharge that has to go in today to cover it.

    fixed_due : True when today's recharge is the FIRST recharge of today's calendar
                month, in which case it triggers the 82.00 tk demand charge + meter rent.
                A single recharge today triggers no other month's fixed charge.

    The gross requirement is broken up as the problem asks:
        energy_at_base   - every unit valued at the first-slab rate, 4.63
        slab_premium     - what being further up the slab ladder adds on top
        fixed            - demand charge + meter rent (0 or 82.00)
        vat              - 5% of the real energy amount
    """
    cum = cum_month_units
    month = ym(today)
    energy = D("0")
    units_total = 0
    per_slab = OrderedDict()
    days = []
    d = today + timedelta(days=1)
    while d <= target:
        if ym(d) != month:
            month = ym(d)
            cum = 0
        e, parts = energy_cost(cum, daily_units)
        for i, u, rate, c in parts:
            row = per_slab.setdefault(i, dict(slab=i, label=slab_label(i), rate=rate,
                                              units=0, cost=D("0")))
            row["units"] += u
            row["cost"] += c
        energy += e
        cum += daily_units
        units_total += daily_units
        days.append(dict(date=d.isoformat(), energy=e, vat=e * VAT_RATE,
                         cum_units_month=cum))
        d += timedelta(days=1)

    energy_base = BASE_RATE * units_total
    slab_premium = energy - energy_base
    fixed = FIXED_MONTHLY if fixed_due else D("0")
    vat = energy * VAT_RATE
    gross = energy + vat + fixed
    bal = D(balance)
    amount = gross - bal
    if amount < 0:
        amount = D("0")
    return dict(
        days_covered=len(days), units=units_total,
        energy=energy, energy_at_base=energy_base, slab_premium=slab_premium,
        fixed=fixed, demand=DEMAND_CHARGE if fixed_due else D("0"),
        rent=METER_RENT if fixed_due else D("0"), vat=vat,
        gross=gross, balance_credit=bal, amount=amount,
        per_slab=list(per_slab.values()), day_rows=days,
        covered_by_balance=bal >= gross,
    )


# --------------------------------------------- item 4: habit comparison ------
def compare_habits(days, opening_balance, low_threshold, low_amount, monthly_amount):
    """
    Two recharge habits on IDENTICAL consumption and the same calendar-month slab counter
    (ruling R-16). `days` is the list of (date, units) for the three comparison months,
    starting on the 1st of the first one.

      low balance : recharge `low_amount` at the start of any day whose balance is below
                    `low_threshold` (R-33)
      monthly     : recharge `monthly_amount` on the 1st of each month (R-33)

    Cost is the money the meter consumes - energy + VAT + the monthly fixed charges that
    actually get triggered (R-33). It is not the amount deposited.
    """
    opening = D(opening_balance)
    low_threshold = D(low_threshold)
    low_amount = D(low_amount)
    monthly_amount = D(monthly_amount)

    # --- habit A: recharge whenever the balance is low (decided day by day) ---
    bal = opening
    cum = 0
    cur_month = None
    fixed_taken = set()
    a_recharges = {}
    for d, units in days:
        key = ym(d)
        if key != cur_month:
            if cur_month is not None:
                cum = 0
            cur_month = key
        if bal < low_threshold:                    # start-of-day test, R-33
            bal += low_amount
            a_recharges[d] = low_amount
            if key not in fixed_taken:
                fixed_taken.add(key)
                bal -= FIXED_MONTHLY
        e, _ = energy_cost(cum, units)
        bal -= e * (D("1") + VAT_RATE)
        cum += units
    low = simulate(days, a_recharges, opening)

    # --- habit B: recharge on the 1st of each month ---
    b_recharges = {d: monthly_amount for d, _ in days if d.day == 1}
    monthly = simulate(days, b_recharges, opening)

    diff = low["total_cost"] - monthly["total_cost"]
    if diff < 0:
        cheaper, saving = "low_balance", -diff
    elif diff > 0:
        cheaper, saving = "monthly", diff
    else:
        cheaper, saving = "equal", D("0")

    return dict(
        low_balance=low, monthly=monthly, cheaper=cheaper, saving=saving,
        cost_difference=diff,
        energy_identical=(low["total_energy"] == monthly["total_energy"]),
        vat_identical=(low["total_vat"] == monthly["total_vat"]),
        fixed_months_low=len(low["fixed_months"]), fixed_months_monthly=len(monthly["fixed_months"]),
        low_recharges=[(d.isoformat(), a_recharges[d]) for d in sorted(a_recharges)],
        monthly_recharges=[(d.isoformat(), b_recharges[d]) for d in sorted(b_recharges)],
    )


# ------------------------------------------------- bonus: slab proximity -----
def slab_warning(cum_units: int, daily_units: int = 0, warn_within: int = 40):
    """
    How close this month's counter is to the next slab, and what the next unit costs on
    each side of the line.
    """
    i = slab_index(cum_units)
    lo, hi = slab_bounds(i)
    cur_rate = SLABS[i][1]
    if hi is None:
        return dict(slab=i, label=slab_label(i), rate=cur_rate, units_to_next=None,
                    next_rate=None, next_label=None, warn=False, days_to_next=None,
                    cum_units=cum_units)
    units_to_next = hi - cum_units
    nxt = i + 1
    days_to_next = None
    if daily_units > 0:
        days_to_next = -(-units_to_next // daily_units)   # ceil
    return dict(
        slab=i, label=slab_label(i), rate=cur_rate,
        units_to_next=units_to_next, next_rate=SLABS[nxt][1], next_label=slab_label(nxt),
        step_up=SLABS[nxt][1] - cur_rate, warn=units_to_next <= warn_within,
        days_to_next=days_to_next, cum_units=cum_units,
    )
