# P10 — Prepaid Meter Recharge Advisor

A Dhaka household on a prepaid meter, the slab tariff it never sees, and the two questions it
actually asks: when does the balance die, and how much has to go in today.

Two implementations of one tariff engine, checked against each other:

| File | What it is |
|---|---|
| `engine.py` | The tariff engine. Decimal arithmetic, no dependencies, no I/O. |
| `solve.py` | Runs items 1–4 over every case in the public file. Report or JSON. |
| `tests.py` | 252 self-checks — hand-computed tariff figures plus invariants on all 25 cases. |
| `build_data.py` | Builds the household payload and injects it into `template.html`. |
| `template.html` | The web tool, with `/*__DATA__*/` as the data slot. |
| `index.html` | **The built tool.** One file, data and all — open it in a browser. |
| `results.json` | Every case's answers, machine-readable. |

```bash
python tests.py                  # 252 checks
python solve.py                  # readable report, all 25 cases
python solve.py PUB-01 -v        # one case with its full daily ledger
python solve.py --json results.json
python build_data.py             # rebuild index.html from template.html
```

The browser engine is a separate implementation in integer ticks of 0.0001 tk. It was run against
`results.json` for all 25 cases — every one of the 5,208 daily ledger rows, every monthly subtotal,
the run-out date, the four-part recharge breakdown and both habit costs, 17,149 comparisons in all —
with **zero mismatches**.

The only thing `index.html` asks the network for is the IBM Plex webfont. It falls back to system
fonts offline; every number is computed in the page.

## The tariff, exactly as given

Units 1–75 at 4.63, 76–200 at 5.26, 201–300 at 5.63, 301–400 at 5.83, 401–600 at 9.30, 601+ at
10.70. Demand charge 42 and meter rent 40, once a month on the first recharge. VAT 5% of the
energy amount. Nothing is read from any published tariff.

## How the rules were read

1. **The slab counter is the calendar month's running unit total.** It resets on the 1st. A
   recharge never resets it. Every part of the tool shares one counter implementation.
2. **Slabs price unit positions.** "Units 1 to 75 cost 4.63 each" means unit 75 costs 4.63 and unit
   76 costs 5.26, so a day that crosses a boundary is split across the two rates rather than billed
   wholly at one. This is the only reading under which the stated per-unit prices hold.
3. **The 82 tk of fixed charges is taken at the first recharge of a calendar month.** A month with
   no recharge in it carries neither charge. This is the only thing that can separate the two
   habits in item 4.
4. **VAT is 5% of the energy amount**, as written — not of the demand charge or the meter rent.
5. **A recharge is credited at the start of its day**, then that day's units are billed. Ruling
   R-33 defines the habit comparison this way; the historical rebuild uses the same order.
6. **Cost is what the meter consumes** — energy, VAT and the fixed charges that actually fall due —
   not what was deposited (R-33).
7. The rebuilt balance is allowed to go negative. A real meter cuts off, but clamping would hide
   the arrears the family ran up.

## The four items

**1 — The household.** All 25 public cases load, plus `HOME-DHK`, a household built for this item:
eight months of daily readings from Dec 2025, a light month (January, 152 units), a heavy summer
month (May, 712 units), and a June where the family lets the meter sit four days in arrears and
then puts 4,000 tk in on the 26th, every unit of it billed at the top slab. The month table flags
all three automatically and colours each day's bar by the slab it landed in.

**2 — The rebuild.** Day by day: recharge at the start of the day, fixed charges if it is the
month's first recharge, then the day's units billed at the slab the running total has reached, plus
VAT. Shown as a balance line with every recharge marked, backed by a full daily ledger.

**3 — The two questions.** Run-out date from today's balance at the usual daily use, with no
recharge in between and therefore no further fixed charges. Recharge-to-reach-a-date broken into
energy at the 4.63 rate, the part added by higher slabs, the fixed charges and VAT — the four
components sum to the gross, and the balance in hand is credited against it. `tests.py` checks for
every case that recharging exactly the advised amount does carry the meter to the target date.

**4 — The two habits.** Identical daily units and the same calendar-month slab counter on both
sides. Low-balance recharges the case amount at the start of any day starting below the threshold;
monthly recharges on the 1st. Energy and VAT come out identical in all 25 cases — verified as an
assertion, not an assumption — so the only possible difference is how many months trigger the 82 tk.
Twenty-two cases tie exactly; PUB-02, PUB-06 and PUB-24 differ by exactly 82.00 tk because the
low-balance habit skips a month entirely.

Equal cost does not mean equal outcome, and the tool says so: a monthly habit that deposits too
little ends the three months thousands of taka in arrears while costing the meter exactly the same.

## Extras

- **Slab proximity.** Units left in the current band, days at the current rate, and what the next
  unit costs after the crossing — with the month's units priced band by band beside it.
- **Reconciliation.** Paste a real recharge history and the balances the meter actually showed; the
  tool rebuilds and reports the gap per reading. Dropping one 400 tk recharge from the history
  produces exactly a 400 tk steady gap, which is what the diagnostic text points at.
- **One month's bill,** split into energy, demand charge, meter rent and VAT, with the energy half
  broken down by slab and compared against what the same units would have cost at 4.63 throughout.
