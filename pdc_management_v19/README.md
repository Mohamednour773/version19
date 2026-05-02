# Post-Dated Checks Management

**Version:** 19.0.2.0.0  
**License:** OPL-1  
**Author:** Mostafa  

## Overview

A comprehensive Post-Dated Checks (PDC) management module for Odoo 17, designed for the Egyptian, Saudi Arabian, and GCC markets where check-based transactions are common in business operations.

## Features

- Complete lifecycle management for received and issued checks
- Check books management with sequential number tracking
- Full accounting integration with configurable intermediate accounts
- Bounced checks handling with bank charges
- Guarantee checks tracking (off-balance sheet)
- Multi-bank check printing with configurable coordinate-based layouts
- Comprehensive reporting suite (PDF + Excel)
- Automated due-date notifications and reminders
- Multi-company and multi-currency support
- Hijri date support (Saudi market)
- Arabic + English UI

## Installation

1. Copy the `pdc_management` folder to your Odoo addons directory
2. Install `num2words` Python package: `pip install num2words`
3. Update the apps list in Odoo
4. Install the module

## Configuration

After installation:
1. Configure bank journals with PDC accounts (Settings → Accounting)
2. Create check books for each bank journal
3. Configure print layouts for your banks
4. Set company PDC settings (alert days, auto-block thresholds)
5. Assign users to PDC groups

## Dashboard (Phase 5)

The **PDC Dashboard** is the main landing page under *PDC Management → Dashboard*.

### What it shows

| Section | Contents |
|---|---|
| **Primary KPIs** | Under Collection total · Due This Week · Bounced This Month · Cleared This Month — each with amount (company currency) and count |
| **Secondary KPIs** | Cash Inflow Forecast (30 / 60 / 90 days) · Cash Outflow (30 days) · Bounce Rate % · Overdue check count |
| **Analytics** | Doughnut: checks by state · Horizontal bar: top 5 partners by outstanding · Line chart: monthly inflow vs outflow (last 6 months) · Bar: top bounce reasons |
| **Quick Actions** | Register New Check · Aging Report · Overdue Checks · Under Collection · Due This Week |

### How to interpret KPIs

- **Under Collection** — received checks deposited at the bank but not yet cleared; these are receivables in transit.
- **Due This Week** — active checks (registered or under collection) whose due date falls within 7 days; use this to prepare daily collection runs.
- **Bounced This Month** — failed clearances this calendar month; investigate via *View All* to follow up with customers.
- **Cleared This Month** — successfully collected cash this month; matches the accounting entries generated on the Clear workflow step.
- **Cash Inflow Forecast** — cumulative received checks with future due dates; amounts are converted to company currency at today's FX rate.
- **Cash Outflow (30 days)** — issued checks in any active state (registered / printed / delivered) due within 30 days; represents committed future payments.
- **Bounce Rate %** — bounced ÷ (cleared + bounced + paid) over the last 12 months. Below 2 % is typically acceptable; above 5 % warrants a credit policy review.
- **Overdue Checks** — active checks whose due date has passed without being deposited; action required.

### Quick actions

| Button | What it opens |
|---|---|
| Register New Check | Blank `pdc.check` form |
| Aging Report | Aging report wizard (by partner × age bucket) |
| Overdue Checks | Filtered list of overdue active checks |
| Under Collection | Filtered list of checks under collection |
| Due This Week | Filtered list of checks due ≤ 7 days |

### Multi-currency

All monetary amounts displayed on the dashboard are converted to the **company currency** at the rate in effect on the day the dashboard is opened (Option A conversion). This is suitable for management reporting but is not used for bookkeeping entries, which use the rate at the time of the transaction.

### Technical notes

- The dashboard uses a `pdc.dashboard` TransientModel. Each click on the menu (or the **Refresh** button) creates a fresh transient record with recomputed KPIs.
- Charts are rendered client-side using **Chart.js** (bundled with Odoo 19) via three Owl 3.0 field widgets registered as `pdc_pie_chart`, `pdc_bar_chart`, `pdc_line_chart`.
- Month labels in the cash-flow chart are localised via **babel** using the logged-in user's language setting, so Arabic users see Arabic month names in the correct order.

---

## Performance Notes

The Aging Report and Partner Statement wizards execute a single `search()` call against
`pdc.check` and group results in Python. **Performance is unverified** for very large
datasets; expected to scale roughly linearly with check count (O(n)). For deployments with
1,000+ active checks, consider adding a database index on `(due_date, state, company_id)`
if report generation becomes slow. The Under Collection, Due Soon, and Bounced list reports
follow the same pattern and carry the same caveat.

## Documentation

See `CHANGELOG.md` for version history.

## License

This module is licensed under the Odoo Proprietary License v1.0 (OPL-1).
See `LICENSE` file for details.
