# -*- coding: utf-8 -*-
"""
Approval Stage Model
Each stage belongs to one Approval Cycle and defines who approves and how.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class UnivApprovalStage(models.Model):
    """
    Represents a single stage within an approval cycle.
    Defines approvers, approval type, and notification settings.
    """
    _name = 'univ.approval.stage'
    _description = 'Approval Stage'
    _order = 'cycle_id, sequence, id'

    name = fields.Char(
        string='Stage Name',
        required=True,
        translate=True,
    )
    cycle_id = fields.Many2one(
        comodel_name='univ.approval.cycle',
        string='Approval Cycle',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order in which this stage is processed (lower = earlier)',
    )
    description = fields.Text(
        string='Stage Description',
        translate=True,
        help='Instructions or notes for approvers at this stage',
    )

    # Approver configuration
    approval_type = fields.Selection(
        selection=[
            ('user', 'Specific Users'),
            ('group', 'User Group'),
            ('dynamic', 'Dynamic Field (from Record)'),
        ],
        string='Approver Type',
        required=True,
        default='user',
        help='How to determine who must approve at this stage',
    )
    approver_ids = fields.Many2many(
        comodel_name='res.users',
        relation='approval_stage_user_rel',
        column1='stage_id',
        column2='user_id',
        string='Approvers',
        help='Users who must approve at this stage (for type = Specific Users)',
    )
    approver_group_id = fields.Many2one(
        comodel_name='res.groups',
        string='Approver Group',
        help='Any member of this group can approve (for type = User Group)',
    )
    dynamic_approver_field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Dynamic Approver Field',
        domain="[('model_id', '=', parent.model_id), ('ttype', 'in', ['many2one']), "
               "('relation', '=', 'res.users')]",
        help='Field on the record that points to the approver (for type = Dynamic Field)',
    )

    # Approval logic
    require_all = fields.Boolean(
        string='Require All Approvers',
        default=False,
        help='If enabled, ALL specified approvers must approve. '
             'If disabled, only ONE approver needs to approve.',
    )
    allow_self_approval = fields.Boolean(
        string='Allow Self-Approval',
        default=False,
        help='Allow the record creator to approve their own request at this stage',
    )

    # Notification
    notify_approvers = fields.Boolean(
        string='Notify Approvers',
        default=True,
        help='Send email notification to approvers when this stage is reached',
    )
    email_template_id = fields.Many2one(
        comodel_name='mail.template',
        string='Custom Email Template',
        help='Override the default notification email with a custom template',
    )

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains('approval_type', 'approver_ids', 'approver_group_id', 'dynamic_approver_field_id')
    def _check_approver_config(self):
        for rec in self:
            if rec.approval_type == 'user' and not rec.approver_ids:
                raise ValidationError(
                    _('Stage "%s": At least one approver must be set when type is "Specific Users".') % rec.name
                )
            if rec.approval_type == 'group' and not rec.approver_group_id:
                raise ValidationError(
                    _('Stage "%s": An approver group must be set when type is "User Group".') % rec.name
                )
            if rec.approval_type == 'dynamic' and not rec.dynamic_approver_field_id:
                raise ValidationError(
                    _('Stage "%s": A dynamic approver field must be set when type is "Dynamic Field".') % rec.name
                )

    # -------------------------------------------------------------------------
    # Business Methods
    # -------------------------------------------------------------------------

    def get_approvers_for_record(self, record):
        """
        Returns a res.users recordset of eligible approvers for a given record.
        Resolves dynamic fields at runtime.
        """
        self.ensure_one()
        if self.approval_type == 'user':
            return self.approver_ids
        elif self.approval_type == 'group':
            return self.env['res.users'].search([
                ('groups_id', 'in', self.approver_group_id.id),
                ('active', '=', True),
            ])
        elif self.approval_type == 'dynamic':
            field_name = self.dynamic_approver_field_id.name
            approver = getattr(record, field_name, False)
            return approver if approver else self.env['res.users']
        return self.env['res.users']
