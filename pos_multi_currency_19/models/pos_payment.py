from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero


class PosPayment(models.Model):
    _inherit = "pos.payment"

    payment_currency_id = fields.Many2one(
        "res.currency",
        string="Payment Currency",
        help="Original currency tendered by the customer.",
    )
    foreign_amount = fields.Monetary(
        string="Foreign Amount",
        currency_field="payment_currency_id",
        help="Amount received in the original payment currency.",
    )
    exchange_rate = fields.Float(
        string="Exchange Rate",
        digits=(12, 8),
        help="Foreign amount to POS currency rate captured at payment time.",
    )
    exchange_rate_date = fields.Date(
        string="Exchange Rate Date",
        help="Date used to compute the stored exchange rate.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if not fields_list:
            return fields_list
        return fields_list + [
            "payment_currency_id",
            "foreign_amount",
            "exchange_rate",
            "exchange_rate_date",
        ]

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._normalize_multi_currency_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if any(field in vals for field in ("payment_currency_id", "foreign_amount", "exchange_rate")):
            vals = self._normalize_multi_currency_vals(vals, existing_record=self)
        return super().write(vals)

    @api.constrains("payment_currency_id", "foreign_amount", "exchange_rate", "amount")
    def _check_multi_currency_payment(self):
        for payment in self:
            if not payment.payment_currency_id:
                continue
            if float_is_zero(
                payment.foreign_amount,
                precision_rounding=payment.payment_currency_id.rounding,
            ):
                raise ValidationError(_("The foreign payment amount must not be zero."))
            if payment.exchange_rate <= 0:
                raise ValidationError(_("The captured exchange rate must be greater than zero."))
            config = payment.pos_order_id.config_id
            if config and (
                not config.multi_currency_payment
                or payment.payment_currency_id not in config.multi_currency_ids
            ):
                raise ValidationError(
                    _(
                        "Currency %(currency)s is not enabled for POS %(pos)s.",
                        currency=payment.payment_currency_id.display_name,
                        pos=config.display_name,
                    )
                )
            expected = payment.currency_id.round(payment.foreign_amount * payment.exchange_rate)
            if not payment.currency_id.is_zero(expected - payment.amount):
                raise ValidationError(
                    _(
                        "The POS amount does not match the foreign amount converted at the captured rate."
                    )
                )

    def _normalize_multi_currency_vals(self, vals, existing_record=False):
        vals = dict(vals)
        currency_id = vals.get("payment_currency_id")
        foreign_amount = vals.get("foreign_amount")
        rate = vals.get("exchange_rate")

        if not currency_id:
            return vals

        payment_currency = self.env["res.currency"].browse(currency_id)
        if not payment_currency.exists():
            return vals

        order = self.env["pos.order"]
        if vals.get("pos_order_id"):
            order = self.env["pos.order"].browse(vals["pos_order_id"])
        elif existing_record and len(existing_record) == 1:
            order = existing_record.pos_order_id

        pos_currency = order.currency_id or self.env.company.currency_id
        company = order.company_id or self.env.company
        rate_date = vals.get("exchange_rate_date") or fields.Date.context_today(self)
        vals.setdefault("exchange_rate_date", rate_date)

        if foreign_amount is not None and not rate:
            converted = payment_currency._convert(
                foreign_amount,
                pos_currency,
                company,
                rate_date,
            )
            rate = converted / foreign_amount if foreign_amount else 0.0
            vals["exchange_rate"] = rate

        if foreign_amount is not None and rate:
            vals["amount"] = pos_currency.round(foreign_amount * rate)

        return vals
