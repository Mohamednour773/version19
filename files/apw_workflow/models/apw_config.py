# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ApwConfig(models.Model):
    """
    Master configuration for an APW approval workflow attached to a specific model.
    Namespace: apw.config  (avoids conflict with Odoo 19 built-in approval.* models)
    """
    _name = 'apw.config'
    _description = 'APW Workflow Configuration'
    _order = 'name'

    name = fields.Char(string='Workflow Name', required=True)
    active = fields.Boolean(default=True)

    model_id = fields.Many2one(
        'ir.model',
        string='Target Model',
        required=True,
        ondelete='cascade',
        domain=[('transient', '=', False)],
        help='The Odoo model this workflow applies to.'
    )
    model_name = fields.Char(
        related='model_id.model',
        string='Model Technical Name',
        store=True,
        readonly=True
    )
    description = fields.Text(string='Description')

    # Blocked actions
    block_write = fields.Boolean(string='Block Edit', default=True,
        help='Prevent editing the record while approval is pending.')
    block_unlink = fields.Boolean(string='Block Delete', default=True,
        help='Prevent deleting the record while approval is pending.')
    block_create = fields.Boolean(string='Block Create', default=False,
        help='Prevent creating new records (rarely needed).')
    block_custom_actions = fields.Char(
        string='Block Custom Methods',
        help='Comma-separated method names to block, e.g. action_confirm,action_validate'
    )

    # Trigger settings
    trigger_on_create = fields.Boolean(
        string='Auto-trigger on Create', default=False,
        help='Automatically start approval workflow when a record is created.'
    )
    trigger_domain = fields.Char(
        string='Trigger Condition (Domain)', default='[]',
        help='Only trigger the workflow when the record matches this Odoo domain.'
    )

    # Notifications
    notify_requester = fields.Boolean(string='Notify Requester', default=True)
    notify_next_approver = fields.Boolean(string='Notify Next Approver', default=True)

    # Stages
    stage_ids = fields.One2many('apw.stage', 'config_id', string='Approval Stages', copy=True)
    stage_count = fields.Integer(compute='_compute_counts', string='# Stages', store=True)

    # Statistics
    request_ids = fields.One2many('apw.request', 'config_id', string='Requests')
    request_count = fields.Integer(compute='_compute_counts', string='# Requests', store=True)
    pending_count = fields.Integer(compute='_compute_counts', string='# Pending', store=True)

    _sql_constraints = [
        ('unique_model', 'UNIQUE(model_id)',
         'A workflow configuration already exists for this model.')
    ]

    @api.depends('stage_ids', 'request_ids', 'request_ids.state')
    def _compute_counts(self):
        for rec in self:
            rec.stage_count = len(rec.stage_ids)
            rec.request_count = len(rec.request_ids)
            rec.pending_count = len(rec.request_ids.filtered(
                lambda r: r.state in ('pending', 'in_progress')
            ))

    @api.constrains('trigger_domain')
    def _check_trigger_domain(self):
        for rec in self:
            try:
                import ast
                domain = ast.literal_eval(rec.trigger_domain or '[]')
                if not isinstance(domain, list):
                    raise ValidationError(_('Trigger Condition must be a valid Odoo domain list.'))
            except (ValueError, SyntaxError):
                raise ValidationError(_('Trigger Condition must be a valid Python list.'))

    def action_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Requests — %s') % self.name,
            'res_model': 'apw.request',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def action_view_stages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stages — %s') % self.name,
            'res_model': 'apw.stage',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def get_blocked_methods(self):
        """Return a set of method names that are blocked while approval is pending."""
        self.ensure_one()
        methods = set()
        if self.block_write:
            methods.add('write')
        if self.block_unlink:
            methods.add('unlink')
        if self.block_create:
            methods.add('create')
        if self.block_custom_actions:
            for m in self.block_custom_actions.split(','):
                m = m.strip()
                if m:
                    methods.add(m)
        return methods

    @api.model
    def get_config_for_model(self, model_name):
        """Retrieve the active workflow config for a given model technical name."""
        return self.search([
            ('model_name', '=', model_name),
            ('active', '=', True),
        ], limit=1)
