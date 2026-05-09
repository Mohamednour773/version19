from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero


class PosPayment(models.Model):
    _inherit = "pos.payment"

    airport_currency_id = fields.Many2one(
        "res.currency",
        string="Tender Currency",
        help="Actual currency tendered by the customer.",
    )
    airport_amount = fields.Monetary(
        string="Tender Amount",
        currency_field="airport_currency_id",
        help="Actual amount received in the tender currency.",
    )
    airport_exchange_rate = fields.Float(
        string="Tender to POS Rate",
        digits=(12, 8),
        help="Captured rate from tender currency to POS currency.",
    )
    airport_exchange_rate_date = fields.Date(
        string="Rate Date",
        help="Date used for the captured tender conversion rate.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if not fields_list:
            return fields_list
        return fields_list + [
            "airport_currency_id",
            "airport_amount",
            "airport_exchange_rate",
            "airport_exchange_rate_date",
        ]

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._normalize_airport_currency_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if any(
            field in vals
            for field in ("airport_currency_id", "airport_amount", "airport_exchange_rate")
        ):
            vals = self._normalize_airport_currency_vals(vals, existing_record=self)
        return super().write(vals)

    @api.constrains("airport_currency_id", "airport_amount", "airport_exchange_rate", "amount")
    def _check_airport_currency_payment(self):
        for payment in self:
            if not payment.airport_currency_id:
                continue
            if float_is_zero(
                payment.airport_amount,
                precision_rounding=payment.airport_currency_id.rounding,
            ):
                raise ValidationError(_("The tender amount must not be zero."))
            if payment.airport_exchange_rate <= 0:
                raise ValidationError(_("The captured exchange rate must be greater than zero."))
            expected = payment.currency_id.round(
                payment.airport_amount * payment.airport_exchange_rate
            )
            if not payment.currency_id.is_zero(expected - payment.amount):
                raise ValidationError(
                    _("The POS amount does not match the tender amount converted at the captured rate.")
                )

    def _normalize_airport_currency_vals(self, vals, existing_record=False):
        vals = dict(vals)
        currency_id = vals.get("airport_currency_id")
        tender_amount = vals.get("airport_amount")
        rate = vals.get("airport_exchange_rate")

        if not currency_id:
            return vals

        tender_currency = self.env["res.currency"].browse(currency_id)
        if not tender_currency.exists():
            return vals

        order = self.env["pos.order"]
        if vals.get("pos_order_id"):
            order = self.env["pos.order"].browse(vals["pos_order_id"])
        elif existing_record and len(existing_record) == 1:
            order = existing_record.pos_order_id

        pos_currency = order.currency_id or self.env.company.currency_id
        company = order.company_id or self.env.company
        rate_date = vals.get("airport_exchange_rate_date") or fields.Date.context_today(self)
        rate_date = fields.Date.to_date(rate_date)
        vals.setdefault("airport_exchange_rate_date", rate_date)

        if tender_amount is None and "amount" in vals:
            tender_amount = tender_currency.round(
                pos_currency._convert(vals["amount"], tender_currency, company, rate_date)
            )
            vals["airport_amount"] = tender_amount

        if tender_amount is not None and not rate:
            converted = tender_currency._convert(
                1.0,
                pos_currency,
                company,
                rate_date,
                round=False,
            )
            rate = converted
            vals["airport_exchange_rate"] = rate

        if tender_amount is not None and rate:
            vals["amount"] = pos_currency.round(tender_amount * rate)

        return vals
