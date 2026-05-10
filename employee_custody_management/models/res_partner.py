from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_custody_holder = fields.Boolean(
        string="Custody Holder",
        default=False,
        index=True,
        copy=False,
        help="Marks partners used only to track employee custody balances.",
    )
    custody_employee_ids = fields.One2many(
        comodel_name="hr.employee",
        inverse_name="work_contact_id",
        string="Custody Employees",
        readonly=True,
    )

    @api.constrains("is_custody_holder")
    def _check_partner_no_dual_role(self):
        """Prevent custody partners from being reused as normal commercial partners."""
        AccountMove = self.env["account.move"].sudo()
        for partner in self:
            if not partner.is_custody_holder:
                continue
            commercial_moves = AccountMove.search_count([
                ("partner_id", "=", partner.id),
                ("move_type", "in", ("out_invoice", "out_refund", "in_invoice", "in_refund")),
                ("state", "!=", "cancel"),
            ])
            if commercial_moves:
                raise ValidationError(_(
                    "The partner %(partner)s is already used on customer/vendor invoices. Custody holders need a "
                    "dedicated partner so the Partner Ledger remains auditable.",
                    partner=partner.display_name,
                ))
