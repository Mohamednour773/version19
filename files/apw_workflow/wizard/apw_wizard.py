# -*- coding: utf-8 -*-
from odoo import models, fields, _, api
from odoo.exceptions import UserError


class ApwRefuseWizard(models.TransientModel):
    """Collect a refusal reason before refusing an apw.request.line."""
    _name = 'apw.refuse.wizard'
    _description = 'APW Refuse Wizard'

    line_id = fields.Many2one('apw.request.line', required=True, ondelete='cascade')
    note = fields.Text(string='Reason for Refusal', required=True)
    stage_name = fields.Char(related='line_id.stage_id.name', string='Stage')
    res_name = fields.Char(related='line_id.res_name', string='Document')

    def action_confirm_refuse(self):
        self.ensure_one()
        if not (self.note or '').strip():
            raise UserError(_('Please provide a reason for the refusal.'))
        self.line_id.do_refuse(note=self.note)
        return {'type': 'ir.actions.act_window_close'}
