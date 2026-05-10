from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    custody_payment_ids = fields.Many2many(
        comodel_name="account.payment",
        compute="_compute_custody_payment_info",
        string="Custody Payments",
    )
    custody_payment_count = fields.Integer(compute="_compute_custody_payment_info")
    custody_paid_amount = fields.Monetary(
        compute="_compute_custody_payment_info",
        currency_field="currency_id",
        string="Custody Paid Amount",
    )

    @api.constrains("partner_id", "move_type")
    def _check_custody_partner_not_commercial_invoice(self):
        """Prevent employee custody partners from being used on customer/vendor invoices."""
        for move in self.filtered(lambda item: item.move_type in ("out_invoice", "out_refund", "in_invoice", "in_refund")):
            if move.partner_id.is_custody_holder:
                raise ValidationError(_(
                    "The partner %(partner)s is reserved for employee custody ledger tracking and cannot be used "
                    "on customer or vendor invoices.",
                    partner=move.partner_id.display_name,
                ))

    @api.depends("matched_payment_ids.is_custody_payment", "matched_payment_ids.amount", "matched_payment_ids.currency_id")
    def _compute_custody_payment_info(self):
        """Compute custody payments linked to vendor bills."""
        for move in self:
            payments = move.matched_payment_ids.filtered("is_custody_payment")
            move.custody_payment_ids = payments
            move.custody_payment_count = len(payments)
            move.custody_paid_amount = sum(
                payment.currency_id._convert(payment.amount, move.currency_id, move.company_id, payment.date)
                for payment in payments
            )

    def action_view_custody_payments(self):
        """Open custody payments that paid this bill."""
        self.ensure_one()
        return self.custody_payment_ids._get_records_action(name=_("Custody Payments"))
