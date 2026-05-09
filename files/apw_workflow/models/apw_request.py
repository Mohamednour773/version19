# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ApwRequest(models.Model):
    """
    A running instance of an APW approval workflow for a specific record.
    Namespace: apw.request
    """
    _name = 'apw.request'
    _description = 'APW Approval Request'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Reference', required=True, copy=False,
        readonly=True, default=lambda self: _('New')
    )
    config_id = fields.Many2one(
        'apw.config', string='Workflow', required=True,
        ondelete='cascade', index=True
    )

    # Polymorphic link to the source document
    res_model = fields.Char(string='Document Model', required=True, index=True)
    res_id = fields.Integer(string='Document ID', required=True, index=True)
    res_name = fields.Char(
        string='Document',
        compute='_compute_res_name',
        store=True
    )

    requester_id = fields.Many2one(
        'res.users', string='Requested By',
        default=lambda self: self.env.user,
        required=True, index=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, index=True)

    current_stage_id = fields.Many2one('apw.stage', string='Current Stage', index=True)

    line_ids = fields.One2many('apw.request.line', 'request_id', string='Approval Lines', copy=False)

    date_submitted = fields.Datetime(string='Submitted On')
    date_approved = fields.Datetime(string='Approved On')
    date_refused = fields.Datetime(string='Refused On')

    waiting_on = fields.Char(compute='_compute_waiting_on', string='Waiting On', store=True)
    progress_percent = fields.Float(compute='_compute_progress', string='Progress (%)', store=True)

    @api.depends('res_model', 'res_id')
    def _compute_res_name(self):
        for rec in self:
            if rec.res_model and rec.res_id:
                try:
                    target = self.env[rec.res_model].browse(rec.res_id)
                    rec.res_name = target.display_name or str(rec.res_id)
                except Exception:
                    rec.res_name = str(rec.res_id)
            else:
                rec.res_name = ''

    @api.depends('line_ids.state', 'state', 'current_stage_id')
    def _compute_waiting_on(self):
        for rec in self:
            if rec.state not in ('pending', 'in_progress'):
                rec.waiting_on = ''
                continue
            pending = rec.line_ids.filtered(
                lambda l: l.stage_id == rec.current_stage_id and l.state == 'pending'
            )
            names = pending.mapped('approver_id.name')
            rec.waiting_on = ', '.join(names) if names else _('Unknown')

    @api.depends('line_ids.state')
    def _compute_progress(self):
        for rec in self:
            total = len(rec.line_ids)
            if not total:
                rec.progress_percent = 0.0
            else:
                done = len(rec.line_ids.filtered(lambda l: l.state in ('approved', 'cancelled')))
                rec.progress_percent = (done / total) * 100.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('apw.request') or _('New')
        return super().create(vals_list)

    # ── State machine ────────────────────────────────────────────────

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft requests can be submitted.'))
            rec._initialize_lines()
            rec.state = 'pending'
            rec.date_submitted = fields.Datetime.now()
            rec._advance_to_next_stage()
            rec.message_post(
                body=_('Approval request submitted by %s.') % rec.requester_id.name,
                subtype_xmlid='mail.mt_note'
            )

    def action_cancel(self):
        for rec in self:
            if rec.state in ('approved', 'refused'):
                raise UserError(_('Cannot cancel a completed request.'))
            rec.line_ids.filtered(lambda l: l.state == 'pending').write({'state': 'cancelled'})
            rec.state = 'cancelled'
            rec.message_post(
                body=_('Request cancelled by %s.') % self.env.user.name,
                subtype_xmlid='mail.mt_note'
            )

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only cancelled requests can be reset.'))
            rec.line_ids.unlink()
            rec.current_stage_id = False
            rec.state = 'draft'

    def action_open_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Internal helpers ─────────────────────────────────────────────

    def _initialize_lines(self):
        """Create apw.request.line records for each applicable stage."""
        self.ensure_one()
        self.line_ids.unlink()

        try:
            target = self.env[self.res_model].browse(self.res_id)
        except Exception:
            raise UserError(_('Cannot find the linked document.'))

        lines_vals = []
        for stage in self.config_id.stage_ids.sorted('sequence'):
            if not stage.is_applicable(target):
                continue

            approvers = stage.resolve_approvers(target)

            if not approvers:
                if stage.auto_approve_if_missing:
                    lines_vals.append({
                        'request_id': self.id,
                        'stage_id': stage.id,
                        'approver_id': self.env.ref('base.user_root').id,
                        'state': 'approved',
                        'note': _('Auto-approved: no approver resolved.'),
                        'date_decided': fields.Datetime.now(),
                    })
                continue

            # For group OR logic — create one line per user; first to approve wins
            # For group AND logic — create one line per user; all must approve
            for user in approvers:
                lines_vals.append({
                    'request_id': self.id,
                    'stage_id': stage.id,
                    'approver_id': user.id,
                    'state': 'pending',
                })

        if lines_vals:
            self.env['apw.request.line'].create(lines_vals)

    def _advance_to_next_stage(self):
        """Move to the next blocking stage, or mark as fully approved."""
        self.ensure_one()
        stages_with_pending = (
            self.line_ids
            .filtered(lambda l: l.state == 'pending')
            .mapped('stage_id')
            .sorted('sequence')
        )

        if not stages_with_pending:
            self._mark_approved()
            return

        next_stage = stages_with_pending[0]
        self.current_stage_id = next_stage
        self.state = 'in_progress'

        if self.config_id.notify_next_approver:
            pending_lines = self.line_ids.filtered(
                lambda l: l.stage_id == next_stage and l.state == 'pending'
            )
            self._notify_approvers(pending_lines)

    def _check_stage_completion(self):
        """Called after a line is approved. Advance if the current stage is done."""
        self.ensure_one()
        stage = self.current_stage_id
        if not stage:
            return

        stage_lines = self.line_ids.filtered(lambda l: l.stage_id == stage)
        pending = stage_lines.filtered(lambda l: l.state == 'pending')

        if stage.approver_type == 'group' and not stage.require_all_group_members:
            # OR logic: one approval is enough → cancel remaining lines
            if stage_lines.filtered(lambda l: l.state == 'approved'):
                pending.write({'state': 'cancelled'})
                self._advance_to_next_stage()
        else:
            # AND logic: all must approve
            if not pending:
                self._advance_to_next_stage()

    def _mark_approved(self):
        self.ensure_one()
        self.write({
            'state': 'approved',
            'date_approved': fields.Datetime.now(),
            'current_stage_id': False,
        })
        self.message_post(
            body=_('✅ All approvals granted. Document is fully approved.'),
            subtype_xmlid='mail.mt_note'
        )
        if self.config_id.notify_requester:
            self._notify_requester(_('Approved'), _(
                'Your request for <b>%s</b> has been fully approved.'
            ) % self.res_name)

    def _notify_approvers(self, lines):
        for line in lines:
            try:
                self.message_notify(
                    partner_ids=line.approver_id.partner_id.ids,
                    subject=_('Approval Required: %s') % self.res_name,
                    body=_(
                        'Hello %s,<br/><br/>'
                        'Your approval is required for <b>%s</b> (Stage: <b>%s</b>).<br/>'
                        'Please review and approve or refuse the request.'
                    ) % (line.approver_id.name, self.res_name, line.stage_id.name),
                    email_layout_xmlid='mail.mail_notification_light',
                )
            except Exception as e:
                _logger.warning('APW: could not notify approver %s: %s', line.approver_id.name, e)

    def _notify_requester(self, subject_suffix, body):
        try:
            self.message_notify(
                partner_ids=self.requester_id.partner_id.ids,
                subject=_('%s: %s') % (subject_suffix, self.res_name),
                body=_('Hello %s,<br/><br/>%s') % (self.requester_id.name, body),
                email_layout_xmlid='mail.mail_notification_light',
            )
        except Exception as e:
            _logger.warning('APW: could not notify requester: %s', e)

    def is_approved(self):
        self.ensure_one()
        return self.state == 'approved'


class ApwRequestLine(models.Model):
    """
    One approver decision within an apw.request.
    Namespace: apw.request.line
    """
    _name = 'apw.request.line'
    _description = 'APW Approval Request Line'
    _order = 'stage_id, id'

    request_id = fields.Many2one(
        'apw.request', string='Request', required=True,
        ondelete='cascade', index=True
    )
    stage_id = fields.Many2one('apw.stage', string='Stage', required=True, ondelete='cascade')
    stage_sequence = fields.Integer(related='stage_id.sequence', string='Seq', store=True)
    stage_name = fields.Char(related='stage_id.name', string='Stage Name', store=True)

    approver_id = fields.Many2one('res.users', string='Approver', required=True, index=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
        ('cancelled', 'Cancelled'),
    ], string='Decision', default='pending', index=True)

    note = fields.Text(string='Comment')
    date_decided = fields.Datetime(string='Decision Date')

    # Denormalized for dashboard queries
    config_id = fields.Many2one(related='request_id.config_id', store=True, string='Workflow')
    res_model = fields.Char(related='request_id.res_model', store=True, string='Model')
    res_id = fields.Integer(related='request_id.res_id', store=True, string='Record ID')
    res_name = fields.Char(related='request_id.res_name', store=True, string='Document')

    def _check_can_decide(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_('This approval has already been decided.'))
        if self.request_id.state not in ('pending', 'in_progress'):
            raise UserError(_('The request is not in an approvable state.'))
        if self.request_id.current_stage_id != self.stage_id:
            raise UserError(_(
                'Stage "%s" is not yet active. Please wait for earlier stages to complete.'
            ) % self.stage_id.name)
        stage = self.stage_id
        if not stage.allow_self_approval and self.env.user == self.request_id.requester_id:
            raise UserError(_('Self-approval is not allowed at stage "%s".') % stage.name)
        # Authorization check
        if self.approver_id != self.env.user:
            if stage.approver_type == 'group' and stage.approver_group_id:
                if self.env.user not in stage.approver_group_id.users:
                    raise UserError(_('You are not authorized to approve at stage "%s".') % stage.name)
            else:
                raise UserError(_('You are not the designated approver for this stage.'))

    def action_approve(self):
        for rec in self:
            rec._check_can_decide()
            rec.write({'state': 'approved', 'date_decided': fields.Datetime.now()})
            rec.request_id.message_post(
                body=_('✅ Stage <b>%s</b> approved by %s.') % (
                    rec.stage_id.name, self.env.user.name),
                subtype_xmlid='mail.mt_note'
            )
            rec.request_id._check_stage_completion()

    def action_refuse(self):
        self.ensure_one()
        self._check_can_decide()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Refuse Approval'),
            'res_model': 'apw.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

    def do_refuse(self, note=''):
        self.ensure_one()
        self.write({'state': 'refused', 'note': note, 'date_decided': fields.Datetime.now()})
        req = self.request_id
        req.write({'state': 'refused', 'date_refused': fields.Datetime.now()})
        req.line_ids.filtered(lambda l: l.state == 'pending').write({'state': 'cancelled'})
        req.message_post(
            body=_('❌ Stage <b>%s</b> refused by %s. Reason: %s') % (
                self.stage_id.name, self.env.user.name, note or _('No reason given')),
            subtype_xmlid='mail.mt_note'
        )
        if req.config_id.notify_requester:
            req._notify_requester(
                _('Refused'),
                _('Your request for <b>%s</b> was refused at stage <b>%s</b>.<br/>Reason: %s') % (
                    req.res_name, self.stage_id.name, note or _('No reason given'))
            )
