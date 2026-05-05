# -*- coding: utf-8 -*-
"""
Approval Log Model
Immutable record of every action taken on an approval request.
"""

from odoo import fields, models


class ApprovalLog(models.Model):
    """
    Stores an immutable log entry for each action (approve/reject/cancel)
    taken during an approval request lifecycle.
    """
    _name = 'approval.log'
    _description = 'Approval Log Entry'
    _order = 'date desc, id desc'

    request_id = fields.Many2one(
        comodel_name='approval.request',
        string='Approval Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    stage_id = fields.Many2one(
        comodel_name='approval.stage',
        string='Stage',
        ondelete='set null',
    )
    approver_id = fields.Many2one(
        comodel_name='res.users',
        string='Action By',
        required=True,
        ondelete='restrict',
    )
    action = fields.Selection(
        selection=[
            ('approve', 'Approved'),
            ('reject', 'Rejected'),
            ('cancel', 'Cancelled'),
            ('submit', 'Submitted'),
        ],
        string='Action',
        required=True,
    )
    action_label = fields.Char(
        string='Action Label',
        compute='_compute_action_label',
    )
    comment = fields.Text(
        string='Comment',
    )
    date = fields.Datetime(
        string='Date & Time',
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # Computed
    # -------------------------------------------------------------------------

    def _compute_action_label(self):
        labels = {
            'approve': '✅ Approved',
            'reject': '❌ Rejected',
            'cancel': '🚫 Cancelled',
            'submit': '📤 Submitted',
        }
        for rec in self:
            rec.action_label = labels.get(rec.action, rec.action)
