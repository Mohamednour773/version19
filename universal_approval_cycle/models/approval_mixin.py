# -*- coding: utf-8 -*-
"""
Approval Mixin
An AbstractModel mixin that can be inherited by any Odoo model to gain
approval-cycle capabilities: smart button, status field, and auto-trigger.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ApprovalMixin(models.AbstractModel):
    """
    Mixin to add approval workflow support to any Odoo model.

    Usage in your model:
        _inherit = ['your.model', 'approval.mixin']

    This adds:
        - approval_request_ids (computed): related approval requests
        - approval_count: count for smart button
        - approval_state: current aggregated state
        - Auto-trigger on create (if configured in cycle)
    """
    _name = 'approval.mixin'
    _description = 'Approval Mixin'

    approval_request_ids = fields.One2many(
        comodel_name='approval.request',
        string='Approval Requests',
        compute='_compute_approval_requests',
    )
    approval_count = fields.Integer(
        string='Approvals',
        compute='_compute_approval_requests',
    )
    approval_state = fields.Selection(
        selection=[
            ('none', 'No Approval'),
            ('draft', 'Draft'),
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Approval Status',
        compute='_compute_approval_state',
        store=False,
    )

    # -------------------------------------------------------------------------
    # Computed
    # -------------------------------------------------------------------------

    def _compute_approval_requests(self):
        model_name = self._name
        for rec in self:
            requests = self.env['approval.request'].search([
                ('model_name', '=', model_name),
                ('res_id', '=', rec.id),
            ])
            rec.approval_request_ids = requests
            rec.approval_count = len(requests)

    def _compute_approval_state(self):
        for rec in self:
            requests = rec.approval_request_ids
            if not requests:
                rec.approval_state = 'none'
            elif any(r.state == 'pending' for r in requests):
                rec.approval_state = 'pending'
            elif all(r.state == 'approved' for r in requests):
                rec.approval_state = 'approved'
            elif any(r.state == 'rejected' for r in requests):
                rec.approval_state = 'rejected'
            elif any(r.state == 'draft' for r in requests):
                rec.approval_state = 'draft'
            else:
                rec.approval_state = 'none'

    # -------------------------------------------------------------------------
    # Auto-trigger on Create
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._auto_trigger_approval()
        return records

    def _auto_trigger_approval(self):
        """
        Check if any approval cycle is configured with auto_trigger for this model.
        If so, create and submit an approval request automatically.
        """
        model_name = self._name
        cycles = self.env['approval.cycle'].search([
            ('model_name', '=', model_name),
            ('auto_trigger', '=', True),
            ('active', '=', True),
        ])
        if not cycles:
            return

        for rec in self:
            for cycle in cycles:
                if self._matches_trigger_domain(rec, cycle):
                    try:
                        request = self.env['approval.request'].create({
                            'cycle_id': cycle.id,
                            'res_id': rec.id,
                            'requester_id': self.env.user.id,
                        })
                        request.action_submit()
                    except Exception as e:
                        _logger.warning(
                            'Auto-trigger failed for cycle %s on record %s: %s',
                            cycle.name, rec.id, e
                        )

    def _matches_trigger_domain(self, record, cycle):
        """Check if a record matches the cycle's trigger domain."""
        try:
            domain = eval(cycle.trigger_domain or '[]')
            if not domain:
                return True
            return bool(self.env[cycle.model_name].search(
                [('id', '=', record.id)] + domain
            ))
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Smart Button Action
    # -------------------------------------------------------------------------

    def action_view_approvals(self):
        """Open approval requests for this record."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Approval Requests'),
            'res_model': 'approval.request',
            'view_mode': 'list,form',
            'domain': [('model_name', '=', self._name), ('res_id', '=', self.id)],
            'context': {
                'default_model_name': self._name,
                'default_res_id': self.id,
            },
        }
        return action

    def action_start_approval(self):
        """Launch wizard to create a new approval request for this record."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Start Approval'),
            'res_model': 'approval.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }
