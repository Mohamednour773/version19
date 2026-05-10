from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    custody_receivable_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Employee Custody Receivable Account",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Shared receivable account used to track employee custody balances by partner.",
    )
    custody_default_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Default Custody Journal",
        domain="[('is_custody_journal', '=', True)]",
        check_company=True,
        help="Default journal used when paying vendor bills from employee custody.",
    )
    custody_first_time_limit = fields.Monetary(
        string="First-Time Custody Limit",
        default=30000.0,
        currency_field="currency_id",
        help="Maximum amount allowed for the first custody issued to an employee.",
    )
    custody_require_settlement_before_new = fields.Boolean(
        string="Require Settlement Before New Custody",
        default=True,
        help="Block issuing a new custody to an employee while another custody remains open.",
    )
