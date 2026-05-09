# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
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

    confirm_method = fields.Char(
        string='Confirm Method (on approval)',
        placeholder='e.g. action_confirm',
    )
    cancel_method = fields.Char(
        string='Cancel Method (on refusal)',
        placeholder='e.g. action_cancel',
    )

    injected_view_id = fields.Many2one(
        'ir.ui.view', string='Injected View',
        ondelete='set null', copy=False, readonly=True,
    )

    notify_requester = fields.Boolean(string='Notify Requester', default=True)
    notify_next_approver = fields.Boolean(string='Notify Next Approver', default=True)

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

    # ── Field injection ──────────────────────────────────────────────

    def _ensure_custom_fields(self):
        """
        Add x_apw_state (Char) and x_apw_waiting (Char) directly onto
        the target model via ir.model.fields — same as Studio custom fields.
        We use Char for state to avoid selection_ids complexity.
        """
        self.ensure_one()
        IrField = self.env['ir.model.fields'].sudo()
        target = self.model_id

        to_create = [
            {
                'name': 'x_apw_state',
                'field_description': 'Approval Status',
                'model_id': target.id,
                'ttype': 'char',
                'store': True,
                'copied': False,
                'readonly': True,
            },
            {
                'name': 'x_apw_waiting',
                'field_description': 'Waiting On (Approval)',
                'model_id': target.id,
                'ttype': 'char',
                'store': True,
                'copied': False,
                'readonly': True,
            },
        ]

        for fdef in to_create:
            existing = IrField.search([
                ('model_id', '=', target.id),
                ('name', '=', fdef['name']),
            ], limit=1)
            if not existing:
                try:
                    IrField.create(fdef)
                    _logger.info('APW: added field %s to %s', fdef['name'], self.model_name)
                except Exception as e:
                    _logger.warning('APW: could not add field %s: %s', fdef['name'], e)

    # ── View injection ───────────────────────────────────────────────

    def _get_primary_form_view(self):
        self.ensure_one()
        return self.env['ir.ui.view'].search([
            ('model', '=', self.model_name),
            ('type', '=', 'form'),
            ('mode', '=', 'primary'),
        ], order='priority asc', limit=1)

    def _get_or_create_submit_action(self):
        """Server action on the target model: submit for APW approval."""
        self.ensure_one()
        action_name = 'APW Submit: %s' % self.model_name
        IrAction = self.env['ir.actions.server'].sudo()
        action = IrAction.search([
            ('model_id', '=', self.model_id.id),
            ('name', '=', action_name),
        ], limit=1)

        code = "\n".join([
            "config = env['apw.config'].get_config_for_model(record._name)",
            "if not config:",
            "    raise UserError('No APW workflow configured for this model.')",
            "existing = env['apw.request'].search([",
            "    ('res_model', '=', record._name),",
            "    ('res_id', '=', record.id),",
            "    ('state', 'in', ['draft', 'pending', 'in_progress']),",
            "], limit=1)",
            "if existing:",
            "    raise UserError('Active approval request already exists: ' + existing.name)",
            "req = env['apw.request'].create({",
            "    'config_id': config.id,",
            "    'res_model': record._name,",
            "    'res_id': record.id,",
            "    'requester_id': env.user.id,",
            "})",
            "req.action_submit()",
        ])

        if not action:
            action = IrAction.create({
                'name': action_name,
                'model_id': self.model_id.id,
                'state': 'code',
                'code': code,
            })
        else:
            action.write({'code': code})
        return action.id

    def _get_or_create_view_action(self):
        """Server action on the target model: view approval requests."""
        self.ensure_one()
        action_name = 'APW View: %s' % self.model_name
        IrAction = self.env['ir.actions.server'].sudo()
        action = IrAction.search([
            ('model_id', '=', self.model_id.id),
            ('name', '=', action_name),
        ], limit=1)

        code = "\n".join([
            "action = {",
            "    'type': 'ir.actions.act_window',",
            "    'name': 'Approval Requests',",
            "    'res_model': 'apw.request',",
            "    'view_mode': 'list,form',",
            "    'domain': [('res_model', '=', record._name), ('res_id', '=', record.id)],",
            "}",
        ])

        if not action:
            action = IrAction.create({
                'name': action_name,
                'model_id': self.model_id.id,
                'state': 'code',
                'code': code,
            })
        else:
            action.write({'code': code})
        return action.id

    def _build_injection_arch(self, submit_id, view_id):
        return (
            '<data>'
            '<xpath expr="//header" position="inside">'
            '<button name="%d" string="Request Approval" type="action" class="btn-warning"'
            ' invisible="x_apw_state in (\'pending\',\'in_progress\',\'approved\')"/>'
            '</xpath>'
            '<xpath expr="//sheet" position="before">'
            '<div style="background:#fff3cd;border-bottom:1px solid #ffc107;'
            'padding:6px 16px;display:flex;align-items:center;gap:12px;"'
            ' invisible="x_apw_state == \'\' or x_apw_state == \'none\'">'
            '<strong>Approval Status:</strong>'
            '<field name="x_apw_state" readonly="1"/>'
            '<span invisible="x_apw_waiting == \'\'">'
            ' — Waiting on: <field name="x_apw_waiting" readonly="1"/>'
            '</span>'
            '<button name="%d" string="View Approvals" type="action" class="btn-link btn-sm"/>'
            '</div>'
            '</xpath>'
            '</data>'
        ) % (submit_id, view_id)

    def action_inject_view(self):
        self.ensure_one()
        if not self.model_name:
            raise ValidationError(_('Please select a target model first.'))

        parent_view = self._get_primary_form_view()
        if not parent_view:
            raise ValidationError(_(
                'No primary form view found for model "%s".'
            ) % self.model_name)

        # 1. Add custom fields to the target model
        self._ensure_custom_fields()

        # 2. Create server actions
        submit_id = self._get_or_create_submit_action()
        view_id   = self._get_or_create_view_action()

        # 3. Build and apply inherited view
        arch = self._build_injection_arch(submit_id, view_id)
        if self.injected_view_id:
            self.injected_view_id.sudo().write({'arch': arch})
        else:
            view = self.env['ir.ui.view'].sudo().create({
                'name': 'apw_inject_%s' % self.model_name.replace('.', '_'),
                'model': self.model_name,
                'inherit_id': parent_view.id,
                'arch': arch,
                'priority': 99,
            })
            self.injected_view_id = view

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Approval button injected into %s successfully!') % self.model_id.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_remove_injection(self):
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
