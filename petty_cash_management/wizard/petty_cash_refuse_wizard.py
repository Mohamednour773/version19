# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class PettyCashRefuseWizard(models.TransientModel):
    _name = 'petty.cash.refuse.wizard'
    _description = 'Refuse Custody Wizard'

    custody_id = fields.Many2one('hr.petty.cash', string='Custody', required=True)
    reason = fields.Text(string='Reason / سبب الرفض', required=True)

    def action_confirm_refuse(self):
        self.ensure_one()
        if not self.reason:
            raise UserError(_('Please provide a reason for refusal.'))
        self.custody_id.write({
            'state': 'refused',
            'refuse_reason': self.reason,
        })
        self.custody_id.message_post(
            body=_('❌ Custody refused. Reason: %s') % self.reason,
            subtype_xmlid='mail.mt_comment',
        )
        return {'type': 'ir.actions.act_window_close'}
