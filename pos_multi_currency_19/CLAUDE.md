# Claude Code Brief

Maintain and harden this production-oriented Odoo 19 addon.

## Current State

The module contains:

- Backend fields on `pos.config`, `pos.payment`, `pos.session`, and `res.currency`.
- POS frontend patch for choosing a foreign payment currency.
- Views for POS config, POS payments, and POS sessions.
- Arabic accounting design notes in `docs/accounting_design_ar.md`.

## Accounting Rule

Keep the POS order and tax totals in the POS currency. Store the original tendered currency on `pos.payment`:

- `payment_currency_id`
- `foreign_amount`
- `exchange_rate`
- `exchange_rate_date`
- `amount` as the converted POS-currency amount

Do not post unbalanced or display-only values. If the business needs true foreign cash/bank ledgers, add a second phase that posts statement/payment entries into per-currency journals.

## Verification Tasks

1. Install the addon on a clean Odoo 19 database with Accounting and Point of Sale.
2. Confirm XML IDs and XPath targets:
   - `point_of_sale.pos_config_view_form`
   - `point_of_sale.view_pos_payment_form`
   - `point_of_sale.view_pos_payment_tree`
   - `point_of_sale.view_pos_session_form`
3. Confirm POS frontend template names and XPath targets:
   - `point_of_sale.PaymentScreen`
   - `point_of_sale.PaymentScreenPaymentLines`
   - `.payment-buttons`
   - `.paymentline`
4. Confirm `PosPayment` serialization sends the new fields to the backend.
5. Open POS offline/online, create an order, add a USD/EUR payment, validate, close session, and inspect journal items.

## Required Test Scenarios

- Full payment in one foreign currency.
- Split payment: local currency plus foreign currency.
- Refund of a foreign-currency payment.
- Rounding difference at small decimal amounts.
- Session close summary per payment method and currency.
- Disabled currency rejected by the backend.

## Phase Two: Full Foreign Journal Support

Only add this if required by the client:

- Require one POS payment method per foreign currency.
- Require journals with matching `currency_id`.
- Extend the statement/payment creation path so journal-currency amount equals `foreign_amount`.
- Ensure realized exchange differences are posted by Odoo accounting on reconciliation or currency conversion.
