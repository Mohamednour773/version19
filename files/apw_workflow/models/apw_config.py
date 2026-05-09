# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ApwConfig(models.Model):
    _name = 'apw.config'
    _description = 'APW Workflow Configuration'
    _order = 'name'

    name = fields.Char(string='Workflow Name', required=True)
    active = fields.Boolean(default=True)

    model_id = fields.Many2one(
        'ir.model', string='Target Model', required=True,
        ondelete='cascade', domain=[('transient', '=', False)],
    )
    model_name = fields.Char(
        related='model_id.model', string='Model Technical Name',
        store=True, readonly=True
    )
    description = fields.Text(string='Description')

    # ── Action to execute after full approval ────────────────────────
    confirm_method = fields.Char(
        string='Confirm Method (on approval)',
        help='Method name to call on the document when all approvals are granted.\n'
             'e.g. action_confirm  or  action_validate\n'
             'Leave empty to do nothing after approval.'
    )
    cancel_method = fields.Char(
        string='Cancel Method (on refusal)',
        help='Method name to call on the document when an approval is refused.\n'
             'e.g. action_cancel\n'
             'Leave empty to do nothing after refusal.'
    )

    # ── Injected view tracking ───────────────────────────────────────
    injected_view_id = fields.Many2one(
        'ir.ui.view', string='Injected View',
        ondelete='set null', copy=False, readonly=True,
        help='Auto-generated view that injects the approval button into the target form.'
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

    # ── View injection ───────────────────────────────────────────────

    def _get_target_form_view(self):
        """Find the primary form view for the target model."""
        self.ensure_one()
        view = self.env['ir.ui.view'].search([
            ('model', '=', self.model_name),
            ('type', '=', 'form'),
            ('mode', '=', 'primary'),
        ], order='priority asc', limit=1)
        return view

    def _build_injection_arch(self):
        """Build the XML arch that injects the APW button + badge into the target form."""
        self.ensure_one()
        arch = """<data>
    <xpath expr="//form" position="inside">
        <header>
            <button name="action_submit_for_apw_approval"
                    string="طلب موافقة"
                    type="object"
                    class="btn-warning"
                    invisible="apw_approval_state in ('pending','in_progress','approved')"/>
        </header>
        <div class="apw_badge_bar" style="margin:4px 0 8px 0; padding: 6px 12px; background:#f8f9fa; border-radius:6px; border:1px solid #dee2e6;" invisible="apw_approval_state == 'none'">
            <field name="apw_approval_state" readonly="1"/>
            <span invisible="apw_approval_waiting == ''"> — ينتظر: <field name="apw_approval_waiting" readonly="1"/></span>
            <button name="action_view_apw_requests" string="عرض الموافقات" type="object" class="btn-link btn-sm"/>
        </div>
    </xpath>
</data>"""
        return arch

    def action_inject_view(self):
        """Inject the APW button into the target model's form view."""
        self.ensure_one()
        if not self.model_name:
            raise ValidationError(_('Please select a target model first.'))

        parent_view = self._get_target_form_view()
        if not parent_view:
            raise ValidationError(_(
                'No primary form view found for model "%s".\n'
                'The approval button cannot be injected automatically.\n'
                'Please add the button manually or ensure the model has a form view.'
            ) % self.model_name)

        arch = self._build_injection_arch()

        if self.injected_view_id:
            self.injected_view_id.write({'arch': arch})
        else:
            view = self.env['ir.ui.view'].create({
                'name': 'apw.inject.%s' % self.model_name.replace('.', '_'),
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
                'message': _('Approval button injected into %s form successfully!') % self.model_id.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_remove_injection(self):
        """Remove the injected view."""
        self.ensure_one()
        if self.injected_view_id:
            self.injected_view_id.unlink()
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
        self.ensure_one()
        methods = set()
        if self.confirm_method:
            # Block the confirm method until approved
            methods.add(self.confirm_method.strip())
        return methods

    @api.model
    def get_config_for_model(self, model_name):
        return self.search([
            ('model_name', '=', model_name),
            ('active', '=', True),
        ], limit=1)

    def unlink(self):
        for rec in self:
            if rec.injected_view_id:
                rec.injected_view_id.unlink()
        return super().unlink()
