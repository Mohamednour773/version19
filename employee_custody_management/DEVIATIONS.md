# Implementation Deviations

This addon keeps the mandatory partner-based custody architecture.

## Odoo 19 payment hook

The local Odoo 19 source confirms that `account.payment._prepare_move_line_default_vals` exists with the signature:

```python
def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
```

The custody override therefore keeps the same signature and rewrites the first liquidity line returned by Odoo.

## Custody journal default account

The build prompt asks custody journals to auto-set `default_account_id` to the custody receivable account. Odoo 19 prevents receivable/payable accounts from being used as the default cash/bank journal account. The addon therefore keeps normal cash/bank journal accounts intact and rewrites the payment liquidity line only for custody payments, which preserves standard Odoo accounting constraints while delivering the required journal entry:

- Dr Accounts Payable, partner = vendor
- Cr Employee Custody Receivable, partner = custody employee

## Translation export command

This Odoo 19 build no longer accepts the legacy server option `--i18n-export`. The equivalent command used for this addon is:

```bash
odoo-bin --addons-path=... i18n export -c odoo.conf -d DB_NAME employee_custody_management -l pot
```
