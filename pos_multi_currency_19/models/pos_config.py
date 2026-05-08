from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = "pos.config"

    multi_currency_payment = fields.Boolean(
        string="Multi-Currency Payments",
        help="Allow cashiers to record POS payment lines in selected foreign currencies.",
    )
    multi_currency_ids = fields.Many2many(
        "res.currency",
        "pos_config_multi_currency_rel",
        "config_id",
        "currency_id",
        string="Accepted Payment Currencies",
        help="Currencies cashiers can select on the POS payment screen.",
    )

    @api.constrains("multi_currency_payment", "multi_currency_ids")
    def _check_multi_currency_ids(self):
        for config in self:
            if config.multi_currency_payment and not config.multi_currency_ids:
                raise ValidationError(
                    _("Select at least one accepted currency or disable multi-currency payments.")
                )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if not fields_list:
            return fields_list
        return fields_list + ["multi_currency_payment", "multi_currency_ids"]
