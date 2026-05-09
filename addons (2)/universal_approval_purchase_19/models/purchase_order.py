from odoo import models


class PurchaseOrder(models.Model):
    _inherit = ["purchase.order", "universal.approval.mixin"]

    def button_confirm(self):
        self._approval_check_before_confirm()
        return super().button_confirm()
