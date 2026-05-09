from odoo import models


class StockPicking(models.Model):
    _inherit = ["stock.picking", "universal.approval.mixin"]

    def button_validate(self):
        self._approval_check_before_confirm()
        return super().button_validate()
