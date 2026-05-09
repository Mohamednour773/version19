from odoo import models


class AccountPayment(models.Model):
    _inherit = ["account.payment", "universal.approval.mixin"]

    def action_post(self):
        self._approval_check_before_confirm()
        return super().action_post()
