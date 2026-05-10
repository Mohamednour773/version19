# Employee Custody & Petty Cash Management

## Overview

Employee Custody & Petty Cash Management tracks petty cash issued to employees and uses Odoo's native partner ledger to keep each employee balance auditable.

## Features

- Employee custody holder flag with automatic work-contact partner creation.
- Shared Employee Custody Receivable account per company.
- Custody request workflow: draft, submitted, approved, issued, partially settled, settled, cancelled.
- Vendor bill payment from custody through the standard Register Payment wizard.
- Settlement documents for returned cash, direct expenses, and existing vendor bills.
- Smart buttons on employees, custody requests, payments, and vendor bills.
- Multi-company and multi-currency aware balances.
- English and Arabic translation files.

## Installation

Install the addon in an Odoo 19 Enterprise database with Accounting, Employees, Mail, and Analytic Accounting installed.

## Configuration

Open Accounting Settings and configure:

- Employee Custody Receivable Account.
- Default Custody Journal.
- First-time custody limit.
- Whether employees must settle open custody before new custody can be issued.

Mark cash or bank journals used for vendor bill custody payments as Custody Journal.

## Usage Walk-Through

Flow A: pay a vendor bill from employee custody.

1. Confirm a vendor bill.
2. Click Register Payment.
3. Select a Custody Journal.
4. Select the custody-holding employee.
5. Confirm the payment.

Flow B: issue and settle custody.

1. Create a Custody Request for the employee.
2. Submit, approve, and issue it.
3. Settle the custody with returned cash, expenses, or vendor bills.

## Accounting Impact

- Issue custody: Dr Employee Custody Receivable, partner = employee / Cr funding journal liquidity.
- Vendor bill: Dr Expense / Cr Accounts Payable, partner = vendor.
- Pay vendor bill from custody: Dr Accounts Payable, partner = vendor / Cr Employee Custody Receivable, partner = employee.
- Return cash: Dr Cash/Bank / Cr Employee Custody Receivable, partner = employee.

## Security & Multi-Company

Custody users see their own requests. Managers and approvers see company records. Administrators configure categories, journals, and accounting settings.

## Compatibility

Designed for Odoo 19 Enterprise and compatible with generic, Egypt, and Saudi localizations.

## Support & Changelog

Version 19.0.1.0.0: initial commercial release.
