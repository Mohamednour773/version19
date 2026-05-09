# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ApwMixin(models.AbstractModel):
    """
    Abstract mixin that adds APW approval awareness to any target model.
    Inherit this in a target model or bridge module to get:
      - action_submit_for_apw_approval()
      - _check_apw_block(method_name)
      - Computed apw_state field
    Namespace: apw.mixin  (no conflict with Odoo 19 approval.* models)
    """
    _name = 'apw.mixin'
    _description = 'APW Approval Mixin'

    apw_request_ids = fields.One2many(
        'apw.request',
        'res_id',
        string='APW Approval Requests',
        domain=lambda self: [('res_model', '=', self._name)],
        copy=False
    )
    apw_state = fields.Selection([
        ('none', 'No Approval'),
        ('pending', 'Pending Approval'),
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
    ], string='Approval Status', compute='_compute_apw_state', store=False)

    apw_request_count = fields.Integer(
        compute='_compute_apw_state', string='# APW Requests'
    )

    @api.depends('apw_request_ids', 'apw_request_ids.state')
    def _compute_apw_state(self):
        for rec in self:
            active = rec.apw_request_ids.filtered(
                lambda r: r.state != 'cancelled'
            ).sorted('create_date', reverse=True)
            rec.apw_request_count = len(active)
            if not active:
                rec.apw_state = 'none'
            else:
                latest = active[0]
                state_map = {
                    'draft': 'pending',
                    'pending': 'pending',
                    'in_progress': 'in_progress',
                    'approved': 'approved',
                    'refused': 'refused',
                }
                rec.apw_state = state_map.get(latest.state, 'none')

    def action_submit_for_apw_approval(self):
        """Create and submit an APW approval request for this record."""
        self.ensure_one()
        config = self.env['apw.config'].get_config_for_model(self._name)
        if not config:
            raise UserError(_(
                'No APW workflow is configured for model "%s". '
                'Please configure one under APW Approvals → Configuration.'
            ) % self._name)

        existing = self.env['apw.request'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('state', 'in', ('draft', 'pending', 'in_progress')),
        ], limit=1)
        if existing:
            raise UserError(_(
                'An active approval request already exists (Ref: %s).'
            ) % existing.name)

        request = self.env['apw.request'].create({
            'config_id': config.id,
            'res_model': self._name,
            'res_id': self.id,
            'requester_id': self.env.user.id,
        })
        request.action_submit()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Request'),
            'res_model': 'apw.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_apw_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('APW Approval Requests'),
            'res_model': 'apw.request',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
        }

    def _check_apw_block(self, method_name):
        """
        Raise UserError if an active APW request is blocking this method.
        Call this at the top of write(), unlink(), action_confirm(), etc.
        """
        config = self.env['apw.config'].get_config_for_model(self._name)
        if not config:
            return
        if method_name not in config.get_blocked_methods():
            return
        if self.env.su:
            return

        for rec in self:
            blocking = self.env['apw.request'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', rec.id),
                ('state', 'in', ('pending', 'in_progress')),
            ], limit=1)
            if blocking:
                raise UserError(_(
                    'Action blocked: A pending approval request exists for this document '
                    '(Ref: %(ref)s, Waiting on: %(who)s).\n\n'
                    'Complete all approvals before performing "%(action)s".'
                ) % {
                    'ref': blocking.name,
                    'who': blocking.waiting_on or _('approver'),
                    'action': method_name,
                })


class ApwEnforcer(models.TransientModel):
    """
    Stateless helper used by bridge modules to check approval blocking
    without inheriting apw.mixin.
    Namespace: apw.enforcer
    """
    _name = 'apw.enforcer'
    _description = 'APW Enforcer'

    @api.model
    def check_and_block(self, model_name, record_ids, method_name):
        """
        Check if approval blocking applies. Raises UserError if blocked.
        Use this in bridge modules:

            self.env['apw.enforcer'].check_and_block(
                self._name, self.ids, 'action_confirm'
            )
        """
        config = self.env['apw.config'].get_config_for_model(model_name)
        if not config:
            return
        if method_name not in config.get_blocked_methods():
            return
        if self.env.su:
            return

        blocking = self.env['apw.request'].search([
            ('res_model', '=', model_name),
            ('res_id', 'in', list(record_ids)),
            ('state', 'in', ('pending', 'in_progress')),
        ], limit=1)

        if blocking:
            raise UserError(_(
                'Action blocked: A pending APW approval request exists '
                '(Ref: %(ref)s, Waiting on: %(who)s).\n\n'
                'Complete all approvals before performing "%(action)s".'
            ) % {
                'ref': blocking.name,
                'who': blocking.waiting_on or _('approver'),
                'action': method_name,
            })
