# -*- coding: utf-8 -*-
"""
Purchase Order integration for the universal approval engine.
"""

from odoo import fields, models, _
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'univ.approval.mixin']

    can_confirm_with_approval = fields.Boolean(
        string='Can Confirm With Approval',
        compute='_compute_can_confirm_with_approval',
    )

    def _compute_can_confirm_with_approval(self):
        for order in self:
            order.can_confirm_with_approval = order._is_po_confirmation_allowed()

    def _get_po_blocking_cycles(self):
        """Return approval cycles that must block PO confirmation."""
        self.ensure_one()
        cycles = self._get_matching_approval_cycles(action_name='button_confirm')
        return cycles.filtered(lambda c: c.enforce_on_action and c.blocking_action_name == 'button_confirm')

    def _get_po_pending_cycle_requests(self):
        """Return non-approved approval requests for blocking PO cycles."""
        self.ensure_one()
        requests = self.env['univ.approval.request']
        for cycle in self._get_po_blocking_cycles():
            request = self._ensure_approval_request_for_cycle(cycle)
            if request and request.state != 'approved':
                requests |= request
        return requests

    def _is_po_confirmation_allowed(self):
        """Whether this PO can be confirmed under the approval policy."""
        self.ensure_one()
        return not bool(self._get_po_pending_cycle_requests())

    def _check_purchase_state_approval_lock(self, target_state):
        """Block purchase confirmation state transitions until approval completes."""
        blocked_states = {'to approve', 'purchase', 'done'}
        if target_state not in blocked_states:
            return
        for order in self:
            order._check_po_confirmation_allowed()

    def _check_po_confirmation_allowed(self):
        """Hard block PO confirmation until all required approvals are complete."""
        self.ensure_one()
        pending_requests = self._get_po_pending_cycle_requests()
        if not pending_requests:
            return True

        pending_request = pending_requests[0]
        if pending_request.state == 'pending':
            raise ValidationError(_(
                'This purchase order cannot be confirmed until approval cycle "%(cycle)s" '
                'is completed. Current stage: %(stage)s. Pending approvers: %(approvers)s.'
            ) % {
                'cycle': pending_request.cycle_id.name,
                'stage': pending_request.current_stage_id.name or _('Unknown'),
                'approvers': ', '.join(pending_request.pending_approver_ids.mapped('name')) or _('No approvers assigned'),
            })
        raise ValidationError(_(
            'This purchase order cannot be confirmed because approval cycle "%(cycle)s" '
            'is in state "%(state)s".'
        ) % {
            'cycle': pending_request.cycle_id.name,
            'state': pending_request.state,
        })

    def write(self, vals):
        target_state = vals.get('state')
        if target_state:
            self._check_purchase_state_approval_lock(target_state)
        return super().write(vals)

    def button_confirm(self):
        for order in self:
            order._check_po_confirmation_allowed()
        return super().button_confirm()

    def button_approve(self, force=False):
        for order in self:
            order._check_po_confirmation_allowed()
        return super().button_approve(force=force)
