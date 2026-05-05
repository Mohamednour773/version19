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


class UnivApprovalMixin(models.AbstractModel):
    """
    Mixin to add approval workflow support to any Odoo model.

    Usage in your model:
        _inherit = ['your.model', 'univ.approval.mixin']

    This adds:
        - approval_request_ids (computed): related approval requests
        - approval_count: count for smart button
        - approval_state: current aggregated state
        - Auto-trigger on create (if configured in cycle)
    """
    _name = 'univ.approval.mixin'
    _description = 'Approval Mixin'

    approval_request_ids = fields.One2many(
        comodel_name='univ.approval.request',
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
    active_approval_request_id = fields.Many2one(
        comodel_name='univ.approval.request',
        string='Active Approval Request',
        compute='_compute_approval_requests',
    )
    approval_stage_name = fields.Char(
        string='Current Approval Stage',
        compute='_compute_approval_state',
    )
    approval_current_approver_ids = fields.Many2many(
        comodel_name='res.users',
        string='Current Approvers',
        compute='_compute_approval_state',
    )
    approval_pending_approver_ids = fields.Many2many(
        comodel_name='res.users',
        string='Pending Approvers',
        compute='_compute_approval_state',
    )
    approval_last_action_summary = fields.Char(
        string='Approval Summary',
        compute='_compute_approval_state',
    )
    approval_can_start = fields.Boolean(
        string='Can Start Approval',
        compute='_compute_approval_state',
    )
    approval_is_blocked = fields.Boolean(
        string='Approval Blocks Action',
        compute='_compute_approval_state',
    )

    # -------------------------------------------------------------------------
    # Computed
    # -------------------------------------------------------------------------

    def _compute_approval_requests(self):
        model_name = self._name
        for rec in self:
            requests = self.env['univ.approval.request'].search([
                ('model_name', '=', model_name),
                ('res_id', '=', rec.id),
            ])
            rec.approval_request_ids = requests
            rec.approval_count = len(requests)
            rec.active_approval_request_id = requests.filtered(
                lambda r: r.state in ('draft', 'pending')
            )[:1]

    def _compute_approval_state(self):
        for rec in self:
            requests = rec.approval_request_ids
            active_request = rec.active_approval_request_id or requests[:1]
            rec.approval_stage_name = active_request.current_stage_id.name or ''
            rec.approval_current_approver_ids = active_request.current_approver_ids
            rec.approval_pending_approver_ids = active_request.pending_approver_ids
            rec.approval_last_action_summary = active_request.last_action_summary or ''
            rec.approval_can_start = not bool(active_request)
            rec.approval_is_blocked = False
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
            rec.approval_is_blocked = rec._approval_requires_action_block()

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
        cycles = self.env['univ.approval.cycle'].search([
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
                        request = self.env['univ.approval.request'].create({
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

    def _get_matching_approval_cycles(self, action_name=False):
        """Return active approval cycles matching this record and optional action."""
        self.ensure_one()
        cycles = self.env['univ.approval.cycle'].search([
            ('model_name', '=', self._name),
            ('active', '=', True),
        ])
        if action_name:
            cycles = cycles.filtered(
                lambda c: c.enforce_on_action and c.blocking_action_name == action_name
            )
        return cycles.filtered(lambda c: self._matches_trigger_domain(self, c))

    def _approval_requires_action_block(self, action_name=False):
        """Whether this record has a blocking approval rule."""
        self.ensure_one()
        return bool(self._get_matching_approval_cycles(action_name=action_name))

    def _get_cycle_request(self, cycle):
        """Return the latest approval request for the given cycle and record."""
        self.ensure_one()
        return self.env['univ.approval.request'].search([
            ('cycle_id', '=', cycle.id),
            ('model_name', '=', self._name),
            ('res_id', '=', self.id),
        ], order='id desc', limit=1)

    def _check_approval_action_allowed(self, action_name, action_label=False):
        """Block model actions until all matching approval cycles are approved."""
        self.ensure_one()
        cycles = self._get_matching_approval_cycles(action_name=action_name)
        if not cycles:
            return True

        action_label = action_label or action_name
        for cycle in cycles:
            request = self._get_cycle_request(cycle)
            if not request:
                raise UserError(_(
                    'This record must complete the approval cycle "%(cycle)s" before you can %(action)s.'
                ) % {
                    'cycle': cycle.name,
                    'action': action_label,
                })
            if request.state == 'approved':
                continue
            if request.state == 'pending':
                raise UserError(_(
                    'Approval cycle "%(cycle)s" is still pending at stage "%(stage)s". '
                    'Current approvers: %(approvers)s.'
                ) % {
                    'cycle': cycle.name,
                    'stage': request.current_stage_id.name or _('Unknown'),
                    'approvers': ', '.join(request.pending_approver_ids.mapped('name')) or _('No approvers assigned'),
                })
            raise UserError(_(
                'Approval cycle "%(cycle)s" is in state "%(state)s". '
                'You cannot %(action)s until it is approved.'
            ) % {
                'cycle': cycle.name,
                'state': request.state,
                'action': action_label,
            })
        return True

    # -------------------------------------------------------------------------
    # Smart Button Action
    # -------------------------------------------------------------------------

    def action_view_approvals(self):
        """Open approval requests for this record."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Approval Requests'),
            'res_model': 'univ.approval.request',
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
            'res_model': 'univ.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }

    def action_view_active_approval(self):
        """Open the most relevant approval request for this record."""
        self.ensure_one()
        request = self.active_approval_request_id or self.approval_request_ids[:1]
        if not request:
            raise UserError(_('No approval request exists for this record yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Request'),
            'res_model': 'univ.approval.request',
            'view_mode': 'form',
            'res_id': request.id,
        }
