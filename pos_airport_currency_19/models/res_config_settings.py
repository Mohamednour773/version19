from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_airport_currency_mode = fields.Boolean(
        related="pos_config_id.airport_currency_mode",
        readonly=False,
    )
    pos_airport_auto_payment_currency = fields.Boolean(
        related="pos_config_id.airport_auto_payment_currency",
        readonly=False,
    )
    pos_airport_show_base_equivalent = fields.Boolean(
        related="pos_config_id.airport_show_base_equivalent",
        readonly=False,
    )

    @api.depends(
        "pos_use_pricelist",
        "pos_config_id",
        "pos_journal_id",
        "pos_airport_currency_mode",
    )
    def _compute_pos_pricelist_id(self):
        airport_records = self.filtered("pos_airport_currency_mode")
        regular_records = self - airport_records
        if regular_records:
            super(ResConfigSettings, regular_records)._compute_pos_pricelist_id()

        for res_config in airport_records:
            if not res_config.pos_use_pricelist:
                res_config.pos_pricelist_id = False
                res_config.pos_available_pricelist_ids = (
                    res_config.pos_config_id.available_pricelist_ids
                )
            else:
                res_config.pos_available_pricelist_ids = (
                    res_config.pos_config_id.available_pricelist_ids
                )
                res_config.pos_pricelist_id = res_config.pos_config_id.pricelist_id
