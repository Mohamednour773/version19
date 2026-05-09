from odoo import models


class HrLeave(models.Model):
    _inherit = ["hr.leave", "universal.approval.mixin"]

    def action_validate(self):
        self._approval_check_before_confirm()
        return super().action_validate()
