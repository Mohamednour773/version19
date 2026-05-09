# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ApprovalMixin(models.AbstractModel):
    """
    Abstract mixin that can be inherited by any model to add approval awareness.
    However, the main enforcement mechanism uses the ApprovalBlocker model
    which patches models dynamically.
    """
    _name = 'approval.mixin'
    _description = 'Approval Workflow Mixin'

    approval_request_ids = fields.One2many(
        'approval.request',
        'res_id',
        string='Approval Requests',
        domain=lambda self: [('res_model', '=', self._name)],
        copy=False
    )
    approval_state = fields.Selection([
        ('none', 'No Approval'),
        ('pending', 'Pending Approval'),
        ('in_progress', 'Approval In Progress'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
    ], string='Approval Status', compute='_compute_approval_state', store=False)

    approval_request_count = fields.Integer(
        compute='_compute_approval_state',
        string='# Approval Requests'
    )

    @api.depends('approval_request_ids', 'approval_request_ids.state')
    def _compute_approval_state(self):
        for rec in self:
            active_requests = rec.approval_request_ids.filtered(
                lambda r: r.state not in ('cancelled',)
            ).sorted('create_date', reverse=True)
            rec.approval_request_count = len(active_requests)
            if not active_requests:
                rec.approval_state = 'none'
            else:
                latest = active_requests[0]
                rec.approval_state = latest.state if latest.state in (
                    'pending', 'in_progress', 'approved', 'refused'
                ) else 'none'

    def action_submit_for_approval(self):
        """Create and submit an approval request for this record."""
        self.ensure_one()
        config = self.env['approval.workflow.config'].get_config_for_model(self._name)
        if not config:
            raise UserError(_(
                'No approval workflow is configured for model "%s". '
                'Please configure one under Approvals > Configuration.'
            ) % self._name)

        # Check for existing active request
        existing = self.env['approval.request'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('state', 'in', ('pending', 'in_progress', 'draft')),
        ], limit=1)
        if existing:
            raise UserError(_(
                'An approval request already exists for this document (Ref: %s).'
            ) % existing.name)

        request = self.env['approval.request'].create({
            'workflow_config_id': config.id,
            'res_model': self._name,
            'res_id': self.id,
            'requester_id': self.env.user.id,
        })
        request.action_submit()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Request'),
            'res_model': 'approval.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_approval_requests(self):
        """Open the approval requests for this record."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Requests'),
            'res_model': 'approval.request',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }

    def _check_approval_block(self, method_name):
        """
        Raises UserError if the approval workflow is blocking the given method.
        Called from patched write/unlink/custom methods.
        """
        config = self.env['approval.workflow.config'].get_config_for_model(self._name)
        if not config:
            return  # No config → no blocking

        blocked_methods = config.get_blocked_methods()
        if method_name not in blocked_methods:
            return  # This method is not blocked

        # Superuser bypasses approval checks
        if self.env.su:
            return

        for rec in self:
            # Check if there is an active approval request that is not yet approved
            active_request = self.env['approval.request'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', rec.id),
                ('state', 'in', ('pending', 'in_progress')),
            ], limit=1)

            if active_request:
                raise UserError(_(
                    'Action blocked: This document has a pending approval request '
                    '(Ref: %(ref)s, Waiting on: %(who)s).\n\n'
                    'The action "%(action)s" cannot be performed until all approvals are granted.'
                ) % {
                    'ref': active_request.name,
                    'who': active_request.waiting_on or _('approver'),
                    'action': method_name,
                })


class ApprovalEnforcer(models.TransientModel):
    """
    Transient model used to dynamically apply approval blocking to any model.
    The actual blocking is done via ir.rule and server actions for scalability,
    but this model provides the hook mechanism.
    """
    _name = 'approval.enforcer'
    _description = 'Approval Enforcer'

    @api.model
    def check_and_block(self, model_name, record_ids, method_name):
        """
        Check if approval blocking applies to the given records for the given method.
        Returns a dict with blocking info or empty dict if not blocked.
        """
        config = self.env['approval.workflow.config'].get_config_for_model(model_name)
        if not config:
            return {}

        blocked_methods = config.get_blocked_methods()
        if method_name not in blocked_methods:
            return {}

        if self.env.su:
            return {}

        blocking_requests = self.env['approval.request'].search([
            ('res_model', '=', model_name),
            ('res_id', 'in', record_ids),
            ('state', 'in', ('pending', 'in_progress')),
        ])

        if blocking_requests:
            return {
                'blocked': True,
                'requests': blocking_requests.ids,
                'message': _('Action blocked by pending approvals.'),
            }
        return {}
