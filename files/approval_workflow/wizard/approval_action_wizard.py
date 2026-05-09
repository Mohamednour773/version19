# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ApprovalRefuseWizard(models.TransientModel):
    """Wizard to collect a refusal reason before refusing an approval line."""
    _name = 'approval.refuse.wizard'
    _description = 'Refuse Approval Wizard'

    line_id = fields.Many2one(
        'approval.request.line',
        string='Approval Line',
        required=True,
        ondelete='cascade'
    )
    note = fields.Text(
        string='Reason for Refusal',
        required=True,
        help='Please provide a reason for refusing this approval.'
    )
    stage_name = fields.Char(related='line_id.stage_id.name', string='Stage')
    res_name = fields.Char(related='line_id.res_name', string='Document')

    def action_confirm_refuse(self):
        """Confirm the refusal."""
        self.ensure_one()
        if not self.note or not self.note.strip():
            raise UserError(_('Please provide a reason for the refusal.'))
        self.line_id.do_refuse(note=self.note)
        return {'type': 'ir.actions.act_window_close'}


class ApprovalActionWizard(models.TransientModel):
    """
    Wizard shown when a user attempts a blocked action.
    Allows them to quickly navigate to the approval request.
    """
    _name = 'approval.action.wizard'
    _description = 'Blocked Action Wizard'

    message = fields.Text(string='Message', readonly=True)
    request_id = fields.Many2one(
        'approval.request',
        string='Approval Request',
        readonly=True
    )
    waiting_on = fields.Char(
        related='request_id.waiting_on',
        string='Waiting On',
        readonly=True
    )
    stage_name = fields.Char(
        related='request_id.current_stage_id.name',
        string='Current Stage',
        readonly=True
    )

    def action_view_request(self):
        """Navigate to the approval request."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'approval.request',
            'res_id': self.request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
