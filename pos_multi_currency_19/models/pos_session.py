from collections import defaultdict

from odoo import api, fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    multi_currency_payment_summary = fields.Json(
        string="Multi-Currency Payment Summary",
        compute="_compute_multi_currency_payment_summary",
    )

    @api.depends(
        "order_ids.payment_ids.payment_currency_id",
        "order_ids.payment_ids.foreign_amount",
        "order_ids.payment_ids.amount",
        "order_ids.payment_ids.payment_method_id",
        "order_ids.state",
    )
    def _compute_multi_currency_payment_summary(self):
        for session in self:
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
            payments = session.order_ids.filtered(
                lambda order: order.state in ("paid", "done")
            ).payment_ids.filtered("payment_currency_id")
            for payment in payments:
                currency = payment.payment_currency_id
                bucket = summary[currency.id]
                bucket["currency"] = currency.name
                bucket["symbol"] = currency.symbol
                bucket["foreign_amount"] += payment.foreign_amount
                bucket["pos_amount"] += payment.amount
                bucket["payment_count"] += 1
                bucket["methods"][payment.payment_method_id.display_name] += payment.foreign_amount

            session.multi_currency_payment_summary = [
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
        payments = self._get_closed_orders().payment_ids.filtered("payment_currency_id")
        if not payments:
            return data

        def summarize(method_payments):
            summary = defaultdict(
                lambda: {
                    "currency": "",
                    "symbol": "",
                    "foreign_amount": 0.0,
                    "pos_amount": 0.0,
                    "payment_count": 0,
                }
            )
            for payment in method_payments:
                currency = payment.payment_currency_id
                bucket = summary[currency.id]
                bucket["currency"] = currency.name
                bucket["symbol"] = currency.symbol
                bucket["foreign_amount"] += payment.foreign_amount
                bucket["pos_amount"] += payment.amount
                bucket["payment_count"] += 1
            return list(summary.values())

        default_cash_details = data.get("default_cash_details") or {}
        default_cash_method_id = default_cash_details.get("id")
        if default_cash_method_id:
            default_cash_payments = payments.filtered(
                lambda payment: payment.payment_method_id.id == default_cash_method_id
            )
            default_cash_details["multi_currency_summary"] = summarize(default_cash_payments)

        for payment_method_data in data.get("non_cash_payment_methods") or []:
            payment_method_id = payment_method_data.get("id")
            method_payments = payments.filtered(
                lambda payment: payment.payment_method_id.id == payment_method_id
            )
            payment_method_data["multi_currency_summary"] = summarize(method_payments)

        return data
