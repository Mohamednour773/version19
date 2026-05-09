from odoo import models


class StockScrap(models.Model):
    _inherit = ["stock.scrap", "universal.approval.mixin"]

    def action_validate(self):
        self._approval_check_before_confirm()
        return super().action_validate()
