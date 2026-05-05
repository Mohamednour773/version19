# -*- coding: utf-8 -*-
"""
Approval Action Wizard
A transient model (wizard) used to:
 1. Start a new approval request for any record.
 2. Process approve/reject actions with a comment.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class UnivApprovalWizard(models.TransientModel):
    """
    Wizard to create and submit an approval request for a given record,
    or to approve/reject an existing pending request.
    """
    _name = 'univ.approval.wizard'
    _description = 'Approval Action Wizard'

    # -------------------------------------------------------------------------
    # Mode: 'start' or 'process'
    # -------------------------------------------------------------------------
    wizard_mode = fields.Selection(
        selection=[
            ('start', 'Start New Approval'),
            ('process', 'Approve / Reject'),
        ],
        string='Mode',
        default='start',
        required=True,
    )

    # -------------------------------------------------------------------------
    # Start mode fields
    # -------------------------------------------------------------------------
    res_model = fields.Char(
        string='Model',
        help='Technical name of the source model',
    )
    res_id = fields.Integer(
        string='Record ID',
    )
    cycle_id = fields.Many2one(
        comodel_name='univ.approval.cycle',
        string='Approval Cycle',
        domain="[('model_name', '=', res_model), ('active', '=', True)]",
    )
    available_cycle_ids = fields.Many2many(
        comodel_name='univ.approval.cycle',
        string='Available Cycles',
        compute='_compute_available_cycles',
    )
    notes = fields.Text(
        string='Justification / Notes',
    )

    # -------------------------------------------------------------------------
    # Process mode fields
    # -------------------------------------------------------------------------
    request_id = fields.Many2one(
        comodel_name='univ.approval.request',
        string='Approval Request',
    )
    action = fields.Selection(
        selection=[
            ('approve', 'Approve'),
            ('reject', 'Reject'),
        ],
        string='Decision',
        default='approve',
    )
    comment = fields.Text(
        string='Comment',
        help='Optional comment or reason for your decision',
    )

    # -------------------------------------------------------------------------
    # Computed
    # -------------------------------------------------------------------------

    @api.depends('res_model')
    def _compute_available_cycles(self):
        for rec in self:
            if rec.res_model:
                rec.available_cycle_ids = self.env['univ.approval.cycle'].search([
                    ('model_name', '=', rec.res_model),
                    ('active', '=', True),
                ])
            else:
                rec.available_cycle_ids = self.env['univ.approval.cycle']

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_confirm(self):
        """Execute the wizard action based on the selected mode."""
        self.ensure_one()
        if self.wizard_mode == 'start':
            return self._do_start_approval()
        elif self.wizard_mode == 'process':
            return self._do_process_approval()

    def _do_start_approval(self):
        """Create and submit a new approval request."""
        if not self.cycle_id:
            raise UserError(_('Please select an approval cycle.'))
        if not self.res_model or not self.res_id:
            raise UserError(_('Source record information is missing.'))

        # Check no active pending request already exists
        existing = self.env['univ.approval.request'].search([
            ('cycle_id', '=', self.cycle_id.id),
            ('res_id', '=', self.res_id),
            ('model_name', '=', self.res_model),
            ('state', '=', 'pending'),
        ], limit=1)
        if existing:
            raise UserError(
                _('An active approval request for this cycle already exists (ID: %s).') % existing.id
            )

        request = self.env['univ.approval.request'].create({
            'cycle_id': self.cycle_id.id,
            'res_id': self.res_id,
            'notes': self.notes,
            'requester_id': self.env.user.id,
        })
        request.action_submit()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Request'),
            'res_model': 'univ.approval.request',
            'view_mode': 'form',
            'res_id': request.id,
        }

    def _do_process_approval(self):
        """Approve or reject the linked request."""
        if not self.request_id:
            raise UserError(_('No approval request selected.'))
        if self.action == 'approve':
            self.request_id.action_approve(comment=self.comment)
        elif self.action == 'reject':
            if not self.comment:
                raise UserError(_('Please provide a reason for rejection.'))
            self.request_id.action_reject(comment=self.comment)
        return {'type': 'ir.actions.act_window_close'}
