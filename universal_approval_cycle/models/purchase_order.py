# -*- coding: utf-8 -*-
"""
Purchase Order integration for the universal approval engine.
"""

from odoo import fields, models, _


class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'univ.approval.mixin']

    can_confirm_with_approval = fields.Boolean(
        string='Can Confirm With Approval',
        compute='_compute_can_confirm_with_approval',
    )

    def _compute_can_confirm_with_approval(self):
        for order in self:
            order.can_confirm_with_approval = not (
                order._approval_requires_action_block('button_confirm')
                and order.approval_state != 'approved'
            )

    def button_confirm(self):
        for order in self:
            order._check_approval_action_allowed(
                action_name='button_confirm',
                action_label=_('confirm this purchase order'),
            )
        return super().button_confirm()

    def button_approve(self, force=False):
        for order in self:
            order._check_approval_action_allowed(
                action_name='button_confirm',
                action_label=_('approve this purchase order'),
            )
        return super().button_approve(force=force)
