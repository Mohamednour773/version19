# Post-Dated Checks Management

**Version:** 17.0.1.0.0  
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
