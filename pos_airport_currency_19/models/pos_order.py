from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    airport_currency_id = fields.Many2one(
        "res.currency",
        string="Sale Currency",
        help="Currency displayed to the cashier/customer, normally taken from the selected pricelist.",
    )
    airport_amount_untaxed = fields.Monetary(
        string="Sale Untaxed Amount",
        currency_field="airport_currency_id",
    )
    airport_amount_tax = fields.Monetary(
        string="Sale Tax Amount",
        currency_field="airport_currency_id",
    )
    airport_amount_total = fields.Monetary(
        string="Sale Total",
        currency_field="airport_currency_id",
    )
    airport_amount_paid = fields.Monetary(
        string="Sale Paid",
        currency_field="airport_currency_id",
    )
    airport_amount_return = fields.Monetary(
        string="Sale Change",
        currency_field="airport_currency_id",
    )
    airport_exchange_rate = fields.Float(
        string="Sale to POS Rate",
        digits=(12, 8),
    )
    airport_exchange_rate_date = fields.Date(string="Sale Rate Date")

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if not fields_list:
            return fields_list
        return fields_list + [
            "airport_currency_id",
            "airport_amount_untaxed",
            "airport_amount_tax",
            "airport_amount_total",
            "airport_amount_paid",
            "airport_amount_return",
            "airport_exchange_rate",
            "airport_exchange_rate_date",
        ]

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._normalize_airport_order_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if any(field in vals for field in ("airport_currency_id", "amount_total", "airport_amount_total")):
            vals = self._normalize_airport_order_vals(vals, existing_record=self)
        return super().write(vals)

    def _normalize_airport_order_vals(self, vals, existing_record=False):
        vals = dict(vals)
        currency_id = vals.get("airport_currency_id")
        if not currency_id:
            return vals

        sale_currency = self.env["res.currency"].browse(currency_id)
        if not sale_currency.exists():
            return vals

        order = existing_record if existing_record and len(existing_record) == 1 else self.env["pos.order"]
        company = order.company_id if order else self.env.company
        pos_currency = order.currency_id if order else self.env.company.currency_id
        rate_date = vals.get("airport_exchange_rate_date") or fields.Date.context_today(self)
        rate_date = fields.Date.to_date(rate_date)
        vals.setdefault("airport_exchange_rate_date", rate_date)
        vals.setdefault(
            "airport_exchange_rate",
            sale_currency._convert(1.0, pos_currency, company, rate_date, round=False),
        )

        amount_map = {
            "amount_total": "airport_amount_total",
            "amount_tax": "airport_amount_tax",
            "amount_paid": "airport_amount_paid",
            "amount_return": "airport_amount_return",
        }
        for base_field, sale_field in amount_map.items():
            if sale_field not in vals and base_field in vals:
                vals[sale_field] = sale_currency.round(
                    pos_currency._convert(vals[base_field], sale_currency, company, rate_date)
                )
        if "airport_amount_untaxed" not in vals:
            if "amount_total" in vals and "amount_tax" in vals:
                vals["airport_amount_untaxed"] = sale_currency.round(
                    pos_currency._convert(
                        vals["amount_total"] - vals["amount_tax"],
                        sale_currency,
                        company,
                        rate_date,
                    )
                )
        return vals


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    airport_currency_id = fields.Many2one(
        "res.currency",
        string="Sale Currency",
    )
    airport_price_unit = fields.Monetary(
        string="Sale Unit Price",
        currency_field="airport_currency_id",
    )
    airport_price_subtotal = fields.Monetary(
        string="Sale Subtotal",
        currency_field="airport_currency_id",
    )
    airport_price_subtotal_incl = fields.Monetary(
        string="Sale Subtotal Incl.",
        currency_field="airport_currency_id",
    )
    airport_exchange_rate = fields.Float(
        string="Sale to POS Rate",
        digits=(12, 8),
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if not fields_list:
            return fields_list
        return fields_list + [
            "airport_currency_id",
            "airport_price_unit",
            "airport_price_subtotal",
            "airport_price_subtotal_incl",
            "airport_exchange_rate",
        ]
