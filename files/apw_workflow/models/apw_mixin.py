# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ApwEnforcer(models.TransientModel):
    """
    Stateless helper called by server actions on target models.
    No inheritance needed on the target model.
    """
    _name = 'apw.enforcer'
    _description = 'APW Enforcer'

    @api.model
    def check_and_block(self, model_name, record_ids, method_name):
        """Raise UserError if method_name is blocked by a pending approval."""
        config = self.env['apw.config'].get_config_for_model(model_name)
        if not config:
            return
        blocked = set()
        if config.confirm_method:
            blocked.add(config.confirm_method.strip())
        if method_name not in blocked:
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
                'Action blocked: pending APW approval (Ref: %s, Waiting on: %s).'
            ) % (blocking.name, blocking.waiting_on or _('approver')))
