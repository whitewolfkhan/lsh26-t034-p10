# P10 — Prepaid Meter Recharge Advisor

A practical, calculator-first tool for understanding a Dhaka prepaid electricity meter: when the balance is expected to run out, how much needs to be recharged, and how different recharge habits affect the final outcome.

This project models the tariff rules exactly as described in the specification and includes a browser-based interface plus a Python validation engine.

## Overview

The tool answers the following questions:

- When will the prepaid balance be exhausted under current usage?
- How much recharge is needed to reach a chosen future date?
- How do fixed charges, slab-based energy pricing, and VAT affect the balance?
- How do different recharge habits compare over time?

The project includes two implementations of the same tariff logic:

- `engine.py` — the core tariff engine with decimal arithmetic and no I/O
- `index.html` — the browser-based UI for end users
- `solve.py` — batch processing for all public cases
- `tests.py` — 252 verification checks covering the rules and edge cases

## Project Structure

| File | Purpose |
|---|---|
| `engine.py` | Core tariff calculation engine |
| `solve.py` | Runs tariff calculations over the public dataset |
| `tests.py` | Validation suite with 252 checks |
| `build_data.py` | Builds the embedded household data for the browser UI |
| `template.html` | UI template that receives the generated dataset |
| `index.html` | Final static web app ready to open in a browser |
| `results.json` | Machine-readable outputs for all test cases |
| `household_data.json` | Household and source data |

## Business Rules Implemented

The calculator follows the tariff assumptions exactly as given:

- Units 1–75 at 4.63
- Units 76–200 at 5.26
- Units 201–300 at 5.63
- Units 301–400 at 5.83
- Units 401–600 at 9.30
- Units 601+ at 10.70
- Demand charge: 42 tk once per month on first recharge
- Meter rent: 40 tk once per month on first recharge
- VAT: 5% of energy amount

The logic applies the calendar-month counter correctly, including:

- slab progression across monthly unit totals
- first-recharge fixed charge behavior
- daily recharge credit timing
- negative balance handling for arrears visibility

## Features

### 1. Household analysis
The app analyzes a household profile across multiple months and identifies:

- low-usage months
- high-usage months
- arrears situations
- slab transitions throughout the month

### 2. Daily ledger rebuild
The system rebuilds the meter history daily, including:

- recharge credit at the start of the day
- monthly fixed charges when due
- slab-based unit billing
- VAT calculation
- final balance trend

### 3. Recharge planning
The calculator estimates:

- run-out date from present balance and normal daily usage
- recharge required to reach a specific future date
- cost components including energy, fixed charges, and VAT

### 4. Habit comparison
The app compares two recharge habits and shows:

- equal energy cost in some cases
- differences caused by fixed charges and timing
- arrears outcomes even when total cost appears similar

### 5. Reconciliation and audit support
The tool can compare expected vs. actual recharge records to identify gaps and mismatches in the meter history.

## Validation

The project includes a strong verification layer:

```bash
python tests.py
```

This runs 252 checks covering:

- tariff calculations
- monthly totals
- balance rebuild logic
- recharge decision correctness
- invariants across the known public cases

Additional commands:

```bash
python solve.py
python solve.py PUB-01 -v
python solve.py --json results.json
python build_data.py
```

These commands provide:

- a readable summary across all cases
- a detailed ledger for one case
- JSON output for automation
- regeneration of the browser data payload from the source template

## Running Locally

To run the project locally:

1. Open the repository folder.
2. Open `index.html` in a browser.
3. Or run the Python tools from the terminal.

```bash
python tests.py
python solve.py
```

The browser version is a static web app and does not require a backend or package installation.

## Deployment on Netlify

This project is suitable for Netlify as a static site.

### Recommended deployment method

1. Create a GitHub repository for the project.
2. Push the contents of this folder to GitHub.
3. Open Netlify and choose “Add new site” → “Import from Git”.
4. Select the repository.
5. Use:
   - Build command: leave blank
   - Publish directory: `.`
6. Deploy.

### Optional `netlify.toml`

```toml
[build]
  publish = "."
```

This works because the app is static and does not require a framework build step.

## Notes

- The app uses a Google font but falls back gracefully to system fonts if offline.
- The calculations are deterministic and do not rely on any external tariff source.
- The generated UI is self-contained, making it easy to review, validate, and deploy.

## License

This project is provided for educational and evaluation use within the project context. Please review repository policies before broader redistribution.

## Summary

This is a compact but rigorous prepaid meter tariff and recharge advisor designed to make tariff logic transparent, auditable, and easy to deploy. It combines a mathematically precise Python engine with a static browser interface, making it suitable for both analysis and straightforward hosting on Netlify.
