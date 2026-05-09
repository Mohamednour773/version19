from collections import defaultdict

from odoo import api, fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    airport_currency_payment_summary = fields.Json(
        string="Airport Currency Payment Summary",
        compute="_compute_airport_currency_payment_summary",
    )

    @api.depends(
        "order_ids.payment_ids.airport_currency_id",
        "order_ids.payment_ids.airport_amount",
        "order_ids.payment_ids.amount",
        "order_ids.payment_ids.payment_method_id",
        "order_ids.state",
    )
    def _compute_airport_currency_payment_summary(self):
        for session in self:
            session.airport_currency_payment_summary = session._get_airport_payment_summary()

    def _get_airport_payment_summary(self, payments=False):
        self.ensure_one()
        if payments is False:
            payments = self.order_ids.filtered(
                lambda order: order.state in ("paid", "done")
            ).payment_ids.filtered("airport_currency_id")

        summary = defaultdict(
            lambda: {
                "currency": "",
                "symbol": "",
                "foreign_amount": 0.0,
                "pos_amount": 0.0,
                "payment_count": 0,
                "methods": defaultdict(float),
            }
        )
        for payment in payments:
            currency = payment.airport_currency_id
            bucket = summary[currency.id]
            bucket["currency"] = currency.name
            bucket["symbol"] = currency.symbol
            bucket["foreign_amount"] += payment.airport_amount
            bucket["pos_amount"] += payment.amount
            bucket["payment_count"] += 1
            bucket["methods"][payment.payment_method_id.display_name] += payment.airport_amount

        return [
            {
                **values,
                "methods": [
                    {"payment_method": name, "foreign_amount": amount}
                    for name, amount in values["methods"].items()
                ],
            }
            for values in summary.values()
        ]

    def get_closing_control_data(self):
        data = super().get_closing_control_data()
        payments = self._get_closed_orders().payment_ids.filtered("airport_currency_id")
        if not payments:
            return data

        default_cash_details = data.get("default_cash_details") or {}
        default_cash_method_id = default_cash_details.get("id")
        if default_cash_method_id:
            default_cash_payments = payments.filtered(
                lambda payment: payment.payment_method_id.id == default_cash_method_id
            )
            default_cash_details["airport_currency_summary"] = self._get_airport_payment_summary(
                default_cash_payments
            )

        for payment_method_data in data.get("non_cash_payment_methods") or []:
            payment_method_id = payment_method_data.get("id")
            method_payments = payments.filtered(
                lambda payment: payment.payment_method_id.id == payment_method_id
            )
            payment_method_data["airport_currency_summary"] = self._get_airport_payment_summary(
                method_payments
            )

        return data

    def _get_combine_statement_line_vals(self, journal, amount, payment_method):
        vals = super()._get_combine_statement_line_vals(journal, amount, payment_method)
        journal_currency = journal.currency_id or self.company_id.currency_id
        if (
            self.config_id.airport_currency_mode
            and payment_method.airport_currency_id
            and payment_method.airport_currency_id == journal_currency
            and journal_currency != self.currency_id
        ):
            payments = self._get_closed_orders().payment_ids.filtered(
                lambda payment: payment.payment_method_id == payment_method
                and payment.airport_currency_id == journal_currency
            )
            foreign_amount = sum(payments.mapped("airport_amount"))
            if foreign_amount:
                vals.update(
                    {
                        "amount": journal_currency.round(foreign_amount),
                        "amount_currency": amount,
                        "foreign_currency_id": self.currency_id.id,
                    }
                )
        return vals

    def _get_split_statement_line_vals(self, journal, amount, payment):
        vals = super()._get_split_statement_line_vals(journal, amount, payment)
        journal_currency = journal.currency_id or self.company_id.currency_id
        if (
            self.config_id.airport_currency_mode
            and payment.airport_currency_id
            and payment.airport_currency_id == journal_currency
            and journal_currency != self.currency_id
        ):
            vals.update(
                {
                    "amount": journal_currency.round(payment.airport_amount),
                    "amount_currency": amount,
                    "foreign_currency_id": self.currency_id.id,
                }
            )
        return vals
