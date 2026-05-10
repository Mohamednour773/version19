from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
        string="Company Currency",
    )
    custody_receivable_account_id = fields.Many2one(
        related="company_id.custody_receivable_account_id",
        readonly=False,
        domain="[('account_type', '=', 'asset_receivable')]",
        string="Employee Custody Receivable Account",
    )
    custody_default_journal_id = fields.Many2one(
        related="company_id.custody_default_journal_id",
        readonly=False,
        domain="[('is_custody_journal', '=', True)]",
        string="Default Custody Journal",
    )
    custody_first_time_limit = fields.Monetary(
        related="company_id.custody_first_time_limit",
        readonly=False,
        currency_field="company_currency_id",
        string="First-Time Custody Limit",
    )
    custody_require_settlement_before_new = fields.Boolean(
        related="company_id.custody_require_settlement_before_new",
        readonly=False,
        string="Require Settlement Before New Custody",
    )
