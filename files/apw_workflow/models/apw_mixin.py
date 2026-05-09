# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ApwMixin(models.AbstractModel):
    """
    Abstract mixin injected dynamically into target models.
    Adds approval state fields and submit/view actions.
    """
    _name = 'apw.mixin'
    _description = 'APW Approval Mixin'

    # These fields are added to any model inheriting this mixin.
    # For dynamic injection (without code changes), use the fields below
    # via the injected ir.ui.view — they will only render if the model
    # has these fields (i.e. inherits apw.mixin).

    apw_approval_state = fields.Selection([
        ('none', 'No Approval'),
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
    ], string='Approval Status', compute='_compute_apw_approval_state', store=True)

    apw_approval_waiting = fields.Char(
        string='Waiting On', compute='_compute_apw_approval_state', store=True
    )

    apw_request_count = fields.Integer(
        compute='_compute_apw_approval_state', string='# APW Requests', store=True
    )

    @api.depends()
    def _compute_apw_approval_state(self):
        """Compute approval state from linked apw.request records."""
        for rec in self:
            requests = self.env['apw.request'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', rec.id),
                ('state', 'not in', ['cancelled']),
            ], order='create_date desc', limit=1)

            rec.apw_request_count = len(requests)

            if not requests:
                rec.apw_approval_state = 'none'
                rec.apw_approval_waiting = ''
                continue

            req = requests[0]
            state_map = {
                'draft': 'pending', 'pending': 'pending',
                'in_progress': 'in_progress', 'approved': 'approved',
                'refused': 'refused',
            }
            rec.apw_approval_state = state_map.get(req.state, 'none')
            rec.apw_approval_waiting = req.waiting_on or ''

    def action_submit_for_apw_approval(self):
        """Submit this record for APW approval."""
        self.ensure_one()
        config = self.env['apw.config'].get_config_for_model(self._name)
        if not config:
            raise UserError(_(
                'No APW workflow configured for "%s".'
            ) % self._name)

        existing = self.env['apw.request'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('state', 'in', ('draft', 'pending', 'in_progress')),
        ], limit=1)
        if existing:
            raise UserError(_('An active approval request already exists (Ref: %s).') % existing.name)

        request = self.env['apw.request'].create({
            'config_id': config.id,
            'res_model': self._name,
            'res_id': self.id,
            'requester_id': self.env.user.id,
        })
        request.action_submit()
        # Recompute state
        self._compute_apw_approval_state()
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
        config = self.env['apw.config'].get_config_for_model(self._name)
        if not config or method_name not in config.get_blocked_methods():
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
                    'Action blocked: pending approval request exists (Ref: %s, Waiting on: %s).'
                ) % (blocking.name, blocking.waiting_on or _('approver')))


class ApwEnforcer(models.TransientModel):
    _name = 'apw.enforcer'
    _description = 'APW Enforcer'

    @api.model
    def check_and_block(self, model_name, record_ids, method_name):
        config = self.env['apw.config'].get_config_for_model(model_name)
        if not config or method_name not in config.get_blocked_methods():
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
                'Action blocked: pending APW approval (Ref: %s).'
            ) % blocking.name)
