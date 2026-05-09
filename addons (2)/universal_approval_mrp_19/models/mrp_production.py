from odoo import models


class MrpProduction(models.Model):
    _inherit = ["mrp.production", "universal.approval.mixin"]

    def action_confirm(self):
        self._approval_check_before_confirm()
        return super().action_confirm()

    def button_mark_done(self):
        self._approval_check_before_confirm()
        return super().button_mark_done()
