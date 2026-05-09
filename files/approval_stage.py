# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ApprovalStage(models.Model):
    """
    Represents a single stage in a sequential approval workflow.
    Stages are ordered by sequence number.
    """
    _name = 'approval.stage'
    _description = 'Approval Stage'
    _order = 'workflow_config_id, sequence, id'

    name = fields.Char(
        string='Stage Name',
        required=True,
        help='Human-readable name for this approval stage (e.g. "Manager Approval", "Finance Review").'
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order in which this stage is processed. Lower numbers come first.'
    )
    workflow_config_id = fields.Many2one(
        'approval.workflow.config',
        string='Workflow',
        required=True,
        ondelete='cascade',
        index=True
    )

    # Approver definition
    approver_type = fields.Selection([
        ('user', 'Specific User'),
        ('group', 'User Group'),
        ('dynamic', 'Dynamic Field (e.g. Manager)'),
    ], string='Approver Type', required=True, default='user')

    approver_user_id = fields.Many2one(
        'res.users',
        string='Approver',
        help='The specific user who must approve at this stage.'
    )
    approver_group_id = fields.Many2one(
        'res.groups',
        string='Approver Group',
        help='Any user in this group can approve at this stage.'
    )
    approver_field_id = fields.Many2one(
        'ir.model.fields',
        string='Approver Field',
        domain="[('model_id', '=', parent.model_id), ('ttype', 'in', ['many2one']), ('relation', '=', 'res.users')]",
        help='A Many2one field on the target model pointing to the approver (e.g. the "Responsible" or "Manager" field).'
    )

    # Stage behavior
    require_all_group_members = fields.Boolean(
        string='Require ALL Group Members',
        default=False,
        help='If approver type is Group, require ALL members to approve (not just one).'
    )
    allow_self_approval = fields.Boolean(
        string='Allow Self-Approval',
        default=False,
        help='Allow the record creator/owner to approve their own record at this stage.'
    )
    auto_approve_if_approver_missing = fields.Boolean(
        string='Auto-approve if Approver Missing',
        default=False,
        help='If no approver can be resolved, automatically approve this stage.'
    )

    # Conditional stage
    condition_domain = fields.Char(
        string='Only Apply If (Domain)',
        default='[]',
        help='This stage is only required if the record matches this domain.'
    )

    # Comments / instructions
    description = fields.Text(
        string='Instructions for Approver',
        help='Additional instructions shown to the approver.'
    )

    # Computed display
    approver_display = fields.Char(
        compute='_compute_approver_display',
        string='Approver'
    )

    @api.depends('approver_type', 'approver_user_id', 'approver_group_id', 'approver_field_id')
    def _compute_approver_display(self):
        for rec in self:
            if rec.approver_type == 'user' and rec.approver_user_id:
                rec.approver_display = rec.approver_user_id.name
            elif rec.approver_type == 'group' and rec.approver_group_id:
                rec.approver_display = rec.approver_group_id.full_name
            elif rec.approver_type == 'dynamic' and rec.approver_field_id:
                rec.approver_display = _('Dynamic: %s') % rec.approver_field_id.field_description
            else:
                rec.approver_display = _('(Not configured)')

    @api.constrains('approver_type', 'approver_user_id', 'approver_group_id', 'approver_field_id')
    def _check_approver_config(self):
        for rec in self:
            if rec.approver_type == 'user' and not rec.approver_user_id:
                raise ValidationError(_('Stage "%s": Please select an approver user.') % rec.name)
            if rec.approver_type == 'group' and not rec.approver_group_id:
                raise ValidationError(_('Stage "%s": Please select an approver group.') % rec.name)
            if rec.approver_type == 'dynamic' and not rec.approver_field_id:
                raise ValidationError(_('Stage "%s": Please select a dynamic approver field.') % rec.name)

    def resolve_approvers(self, record):
        """
        Return a list of res.users that are the approvers for this stage,
        resolved against the given record.
        """
        self.ensure_one()
        users = self.env['res.users']

        if self.approver_type == 'user':
            if self.approver_user_id:
                users = self.approver_user_id
        elif self.approver_type == 'group':
            if self.approver_group_id:
                users = self.approver_group_id.users
        elif self.approver_type == 'dynamic':
            if self.approver_field_id:
                field_name = self.approver_field_id.name
                user = getattr(record, field_name, None)
                if user and user._name == 'res.users':
                    users = user
                elif user and user._name == 'res.partner':
                    partner_user = self.env['res.users'].search(
                        [('partner_id', '=', user.id)], limit=1
                    )
                    users = partner_user

        return users

    def is_applicable(self, record):
        """Check whether this stage applies to the given record (condition_domain)."""
        self.ensure_one()
        if not self.condition_domain or self.condition_domain.strip() in ('[]', 'False', ''):
            return True
        try:
            import ast
            domain = ast.literal_eval(self.condition_domain)
            matching = self.env[record._name].search(
                [('id', '=', record.id)] + domain
            )
            return bool(matching)
        except Exception:
            return True
