from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    airport_currency_id = fields.Many2one(
        "res.currency",
        string="Airport Currency",
        help=(
            "Physical currency accepted by this payment method. Use one cash journal per "
            "foreign currency when you need the cash drawer and bank statement in that currency."
        ),
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if not fields_list:
            return fields_list
        if "airport_currency_id" not in fields_list:
            fields_list += ["airport_currency_id"]
        return fields_list

    @api.constrains("airport_currency_id", "journal_id")
    def _check_airport_currency_journal(self):
        for method in self:
            journal_currency = method.journal_id.currency_id
            if (
                method.airport_currency_id
                and journal_currency
                and journal_currency != method.airport_currency_id
            ):
                raise ValidationError(
                    _(
                        "Airport Currency must match the payment journal currency. "
                        "Leave the journal without a currency for company-currency accounting."
                    )
                )
