# POS Multi Currency Payments for Odoo 19

This addon provides a conservative, accounting-safe multi-currency payment layer for Odoo 19 POS.

The POS order, taxes, and session move stay in the POS currency. Each foreign payment line stores:

- `payment_currency_id`
- `foreign_amount`
- `exchange_rate`
- `exchange_rate_date`
- `amount` in the POS currency

That keeps the core POS session balanced while preserving the real tendered currency for cashier closing, audit, and later bank/cash reconciliation work.

## Accounting Position

Do not treat this as a display-only currency switch. The correct accounting path is:

1. Sales and taxes are recognized in the POS currency, which is usually the company currency.
2. Foreign tender is converted into the POS currency on the payment line at the captured rate.
3. The original currency and amount are retained for session closing and audit.
4. If the business keeps real foreign-currency cash boxes or bank accounts, configure operational payment methods per currency and extend the statement/payment creation layer to post journal-currency amounts.

See `docs/accounting_design_ar.md` for the accounting notes, operating assumptions, and phase-two ledger design.
