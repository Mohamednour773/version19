# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ApwStage(models.Model):
    """
    One sequential stage in an APW approval workflow.
    Namespace: apw.stage
    """
    _name = 'apw.stage'
    _description = 'APW Approval Stage'
    _order = 'config_id, sequence, id'

    name = fields.Char(string='Stage Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    config_id = fields.Many2one(
        'apw.config',
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

    approver_user_id = fields.Many2one('res.users', string='Approver User')
    approver_group_id = fields.Many2one('res.groups', string='Approver Group')
    approver_field_id = fields.Many2one(
        'ir.model.fields',
        string='Approver Field',
        domain="[('model_id', '=', parent.model_id), "
               "('ttype', '=', 'many2one'), ('relation', '=', 'res.users')]",
        help='A Many2one→res.users field on the target model (e.g. manager_id).'
    )

    # Stage behaviour
    require_all_group_members = fields.Boolean(
        string='Require ALL Group Members', default=False,
        help='If approver type is Group, require every member to approve (not just one).'
    )
    allow_self_approval = fields.Boolean(
        string='Allow Self-Approval', default=False,
        help='Allow the record creator to approve at this stage.'
    )
    auto_approve_if_missing = fields.Boolean(
        string='Auto-approve if No Approver', default=False,
        help='Skip this stage automatically if no approver can be resolved.'
    )
    condition_domain = fields.Char(
        string='Only Apply If (Domain)', default='[]',
        help='This stage is only required when the record matches this domain.'
    )
    description = fields.Text(string='Instructions for Approver')

    # Display
    approver_display = fields.Char(
        compute='_compute_approver_display', string='Approver', store=True
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
                raise ValidationError(
                    _('Stage "%s": Please select an approver user.') % rec.name)
            if rec.approver_type == 'group' and not rec.approver_group_id:
                raise ValidationError(
                    _('Stage "%s": Please select an approver group.') % rec.name)
            if rec.approver_type == 'dynamic' and not rec.approver_field_id:
                raise ValidationError(
                    _('Stage "%s": Please select a dynamic approver field.') % rec.name)

    def resolve_approvers(self, record):
        """Return res.users recordset of the approvers for this stage against the given record."""
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
                fname = self.approver_field_id.name
                val = getattr(record, fname, None)
                if val and val._name == 'res.users':
                    users = val
                elif val and val._name == 'res.partner':
                    partner_user = self.env['res.users'].search(
                        [('partner_id', '=', val.id)], limit=1
                    )
                    users = partner_user

        return users

    def is_applicable(self, record):
        """Return True if this stage should apply to the given record."""
        self.ensure_one()
        domain = (self.condition_domain or '[]').strip()
        if domain in ('[]', 'False', ''):
            return True
        try:
            import ast
            parsed = ast.literal_eval(domain)
            matching = self.env[record._name].search([('id', '=', record.id)] + parsed)
            return bool(matching)
        except Exception:
            return True
