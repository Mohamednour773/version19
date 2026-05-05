# -*- coding: utf-8 -*-
"""
Purchase Order integration for the universal approval engine.
"""

from odoo import models, _


class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'univ.approval.mixin']

    def button_confirm(self):
        for order in self:
            order._check_approval_action_allowed(
                action_name='button_confirm',
                action_label=_('confirm this purchase order'),
            )
        return super().button_confirm()
