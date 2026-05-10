from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CustodyCategory(models.Model):
    _name = "custody.category"
    _description = "Custody Category"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(required=True, translate=True, tracking=True)
    code = fields.Char(required=True, tracking=True)
    description = fields.Text(translate=True)
    disbursement_limit = fields.Monetary(
        string="Single Disbursement Limit",
        currency_field="currency_id",
        tracking=True,
        help="Maximum allowed open custody balance after issuing this category. Leave zero for no limit.",
    )
    analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Default Analytic Account",
        check_company=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    _code_company_uniq = models.Constraint(
        "UNIQUE(code, company_id)",
        "The category code must be unique per company.",
    )

    @api.constrains("disbursement_limit")
    def _check_disbursement_limit(self):
        """Ensure that category limits are never negative."""
        for category in self:
            if category.disbursement_limit < 0:
                raise ValidationError(_("The custody category limit cannot be negative."))
