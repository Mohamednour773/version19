from odoo import api, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    @api.model
    def _load_pos_data_domain(self, data, config):
        domain = super()._load_pos_data_domain(data, config)
        if not config.airport_currency_mode:
            return domain

        currency_ids = set()
        currency_ids.add(config.company_id.currency_id.id)
        currency_ids.add(config.currency_id.id)

        if config.use_pricelist:
            currency_ids.update(config._get_available_pricelists().mapped("currency_id").ids)

        currency_ids.update(config.payment_method_ids.mapped("airport_currency_id").ids)
        return [("id", "in", list(currency_ids))]
