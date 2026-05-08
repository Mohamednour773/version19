from odoo import api, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    @api.model
    def _load_pos_data_domain(self, data, config):
        domain = super()._load_pos_data_domain(data, config)
        currency_ids = set(config.multi_currency_ids.ids)
        if not currency_ids:
            return domain
        currency_ids.update([config.company_id.currency_id.id, config.currency_id.id])
        return [("id", "in", list(currency_ids))]

