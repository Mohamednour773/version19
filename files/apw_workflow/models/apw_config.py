# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class ApwConfig(models.Model):
    _name = 'apw.config'
    _description = 'APW Workflow Configuration'
    _order = 'name'

    name = fields.Char(string='Workflow Name', required=True)
    active = fields.Boolean(default=True)

    model_id = fields.Many2one(
        'ir.model', string='Target Model', required=True,
        ondelete='restrict', domain=[('transient', '=', False)],
    )
    model_name = fields.Char(
        related='model_id.model', string='Model Technical Name',
        store=True, readonly=True
    )
    description = fields.Text(string='Description')

    # Method to call on the document after all approvals granted
    confirm_method = fields.Char(
        string='Confirm Method (on approval)',
        placeholder='e.g. action_confirm',
        help='Method name to call on the document when all approvals are granted. Leave empty to do nothing.'
    )
    # Method to call on the document after refusal
    cancel_method = fields.Char(
        string='Cancel Method (on refusal)',
        placeholder='e.g. action_cancel',
        help='Method name to call on the document when an approval is refused. Leave empty to do nothing.'
    )

    # Track injected view
    injected_view_id = fields.Many2one(
        'ir.ui.view', string='Injected View',
        ondelete='set null', copy=False, readonly=True,
    )

    # Notifications
    notify_requester = fields.Boolean(string='Notify Requester', default=True)
    notify_next_approver = fields.Boolean(string='Notify Next Approver', default=True)

    # Stages
    stage_ids = fields.One2many('apw.stage', 'config_id', string='Approval Stages', copy=True)
    stage_count = fields.Integer(compute='_compute_counts', string='# Stages', store=True)

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

    # ── Dynamic field + view injection ──────────────────────────────

    def _ensure_fields_on_model(self):
        """
        Add computed fields directly to the target model via ir.model.fields.
        This makes them first-class fields on the original model — no new models.
        Fields added:
          - apw_state       (Selection: char stored)
          - apw_waiting     (Char stored)
        """
        self.ensure_one()
        IrField = self.env['ir.model.fields']
        target_model = self.model_id

        fields_to_create = [
            {
                'name': 'x_apw_state',
                'field_description': 'Approval Status',
                'model_id': target_model.id,
                'ttype': 'selection',
                'selection': "[('none','No Approval'),('pending','Pending'),('in_progress','In Progress'),('approved','Approved'),('refused','Refused')]",
                'store': True,
                'copied': False,
            },
            {
                'name': 'x_apw_waiting',
                'field_description': 'Waiting On',
                'model_id': target_model.id,
                'ttype': 'char',
                'store': True,
                'copied': False,
            },
        ]

        created = []
        for fdef in fields_to_create:
            existing = IrField.search([
                ('model_id', '=', target_model.id),
                ('name', '=', fdef['name']),
            ], limit=1)
            if not existing:
                try:
                    IrField.create(fdef)
                    created.append(fdef['name'])
                    _logger.info('APW: created field %s on %s', fdef['name'], self.model_name)
                except Exception as e:
                    _logger.warning('APW: could not create field %s: %s', fdef['name'], e)

        return created

    def _get_primary_form_view(self):
        """Return the primary form view for the target model."""
        self.ensure_one()
        return self.env['ir.ui.view'].search([
            ('model', '=', self.model_name),
            ('type', '=', 'form'),
            ('mode', '=', 'primary'),
        ], order='priority asc', limit=1)

    def _build_injection_arch(self):
        """
        Build the inherited view arch that injects:
          1. "Request Approval" button in the header
          2. Status badge bar below the title
        Directly onto the target model's form — no separate form.
        """
        self.ensure_one()
        arch = (
            '<data>'
            '<xpath expr="//header" position="inside">'
            '<button name="apw_submit_approval"'
            ' string="Request Approval"'
            ' type="object"'
            ' class="btn-warning"'
            ' invisible="x_apw_state in (\'pending\',\'in_progress\',\'approved\')"/>'
            '</xpath>'
            '<xpath expr="//sheet" position="before">'
            '<div style="padding:6px 16px 0 16px;" invisible="x_apw_state == \'none\'">'
            '<field name="x_apw_state" readonly="1"/>'
            '<span invisible="x_apw_waiting == \'\'">'
            ' — Waiting on: <field name="x_apw_waiting" readonly="1"/>'
            '</span>'
            '<button name="apw_view_approvals" string="View Approvals"'
            ' type="object" class="btn-link"/>'
            '</div>'
            '</xpath>'
            '</data>'
        )
        return arch

    def action_inject_view(self):
        """
        1. Create x_apw_state, x_apw_waiting fields on the target model.
        2. Inject the approval button + badge into the target model's form view.
        3. Register the server action that apw_submit_approval will call.
        """
        self.ensure_one()
        if not self.model_name:
            raise ValidationError(_('Please select a target model first.'))

        # Step 1: add fields to the model
        self._ensure_fields_on_model()

        # Step 2: inject button+badge into form view
        parent_view = self._get_primary_form_view()
        if not parent_view:
            raise ValidationError(_(
                'No primary form view found for "%s". '
                'The injection cannot be done automatically.'
            ) % self.model_name)

        arch = self._build_injection_arch()
        if self.injected_view_id:
            self.injected_view_id.write({'arch': arch})
        else:
            view = self.env['ir.ui.view'].sudo().create({
                'name': 'apw_inject_%s' % self.model_name.replace('.', '_'),
                'model': self.model_name,
                'inherit_id': parent_view.id,
                'arch': arch,
                'priority': 99,
            })
            self.injected_view_id = view

        # Step 3: ensure server actions exist for the buttons
        self._ensure_server_actions()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Approval button injected into %s successfully!') % self.model_id.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def _ensure_server_actions(self):
        """
        Create ir.actions.server bound to the target model for:
          - apw_submit_approval  (button name in the injected view)
          - apw_view_approvals
        These are model-level server actions that get called as methods.
        """
        self.ensure_one()
        # We bind via ir.actions.server with binding_model_id
        # so they appear as object buttons on the model.
        IrAction = self.env['ir.actions.server']

        for action_def in [
            {
                'name': 'APW: Submit for Approval',
                'model_id': self.model_id.id,
                'binding_model_id': self.model_id.id,
                'state': 'code',
                'code': (
                    "config = env['apw.config'].get_config_for_model(record._name)\n"
                    "if not config:\n"
                    "    raise UserError('No APW workflow configured for this model.')\n"
                    "existing = env['apw.request'].search([\n"
                    "    ('res_model','=',record._name),\n"
                    "    ('res_id','=',record.id),\n"
                    "    ('state','in',['draft','pending','in_progress']),\n"
                    "], limit=1)\n"
                    "if existing:\n"
                    "    raise UserError('Active approval request already exists: ' + existing.name)\n"
                    "req = env['apw.request'].create({\n"
                    "    'config_id': config.id,\n"
                    "    'res_model': record._name,\n"
                    "    'res_id': record.id,\n"
                    "    'requester_id': env.user.id,\n"
                    "})\n"
                    "req.action_submit()\n"
                    "record.write({'x_apw_state': req.state, 'x_apw_waiting': req.waiting_on or ''})\n"
                ),
                '_apw_key': 'apw_submit_approval_%s' % self.model_name,
            },
            {
                'name': 'APW: View Approvals',
                'model_id': self.model_id.id,
                'binding_model_id': self.model_id.id,
                'state': 'code',
                'code': (
                    "action = {\n"
                    "    'type': 'ir.actions.act_window',\n"
                    "    'name': 'Approval Requests',\n"
                    "    'res_model': 'apw.request',\n"
                    "    'view_mode': 'list,form',\n"
                    "    'domain': [('res_model','=',record._name),('res_id','=',record.id)],\n"
                    "}\n"
                ),
                '_apw_key': 'apw_view_approvals_%s' % self.model_name,
            },
        ]:
            key = action_def.pop('_apw_key')
            # Check by name+model to avoid duplicates
            existing = IrAction.search([
                ('name', '=', action_def['name']),
                ('model_id', '=', self.model_id.id),
            ], limit=1)
            if not existing:
                IrAction.sudo().create(action_def)

    def action_remove_injection(self):
        """Remove the injected view (fields stay — safe to keep)."""
        self.ensure_one()
        if self.injected_view_id:
            self.injected_view_id.sudo().unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Approval button removed from form view.'),
                'type': 'warning',
                'sticky': False,
            }
        }

    def action_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Requests — %s') % self.name,
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

    @api.model
    def get_config_for_model(self, model_name):
        return self.search([
            ('model_name', '=', model_name),
            ('active', '=', True),
        ], limit=1)

    def unlink(self):
        for rec in self:
            if rec.injected_view_id:
                try:
                    rec.injected_view_id.sudo().unlink()
                except Exception:
                    pass
        return super().unlink()
