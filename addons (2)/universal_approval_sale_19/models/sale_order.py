from odoo import models


class SaleOrder(models.Model):
    _inherit = ["sale.order", "universal.approval.mixin"]

    def action_confirm(self):
        self._approval_check_before_confirm()
        return super().action_confirm()
