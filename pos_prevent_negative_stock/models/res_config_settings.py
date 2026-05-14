from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_prevent_negative_stock = fields.Boolean(
        related="pos_config_id.prevent_negative_stock",
        readonly=False,
    )
