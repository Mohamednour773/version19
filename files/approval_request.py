# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ApprovalRequest(models.Model):
    """
    An instance of an approval workflow run for a specific record.
    Tracks the overall state and links to individual stage approvals.
    """
    _name = 'approval.request'
    _description = 'Approval Request'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    workflow_config_id = fields.Many2one(
        'approval.workflow.config',
        string='Workflow',
        required=True,
        ondelete='cascade',
        index=True
    )
    # Polymorphic link to the source record
    res_model = fields.Char(
        string='Document Model',
        required=True,
        index=True
    )
    res_id = fields.Integer(
        string='Document ID',
        required=True,
        index=True
    )
    res_name = fields.Char(
        string='Document',
        compute='_compute_res_name',
        store=True
    )

    requester_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        index=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('approved', 'Fully Approved'),
        ('refused', 'Refused'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, index=True)

    current_stage_id = fields.Many2one(
        'approval.stage',
        string='Current Stage',
        index=True
    )
    current_stage_sequence = fields.Integer(
        related='current_stage_id.sequence',
        string='Current Sequence'
    )

    # Stage approval lines
    line_ids = fields.One2many(
        'approval.request.line',
        'request_id',
        string='Approval Lines',
        copy=False
    )

    date_submitted = fields.Datetime(string='Submitted On')
    date_approved = fields.Datetime(string='Fully Approved On')
    date_refused = fields.Datetime(string='Refused On')

    # Who is blocking right now
    waiting_on = fields.Char(
        compute='_compute_waiting_on',
        string='Waiting On',
        store=False
    )
    progress_percent = fields.Float(
        compute='_compute_progress',
        string='Progress (%)'
    )

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

    @api.depends('line_ids', 'line_ids.state', 'state', 'current_stage_id')
    def _compute_waiting_on(self):
        for rec in self:
            if rec.state not in ('pending', 'in_progress'):
                rec.waiting_on = ''
                continue
            pending_lines = rec.line_ids.filtered(
                lambda l: l.stage_id == rec.current_stage_id and l.state == 'pending'
            )
            names = pending_lines.mapped('approver_id.name')
            rec.waiting_on = ', '.join(names) if names else _('Unknown')

    @api.depends('line_ids', 'line_ids.state')
    def _compute_progress(self):
        for rec in self:
            total = len(rec.line_ids)
            if not total:
                rec.progress_percent = 0.0
                continue
            approved = len(rec.line_ids.filtered(lambda l: l.state == 'approved'))
            rec.progress_percent = (approved / total) * 100.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('approval.request') or _('New')
        return super().create(vals_list)

    def action_submit(self):
        """Submit the request and start the first approval stage."""
        for rec in self:
            if rec.state not in ('draft',):
                raise UserError(_('Only draft requests can be submitted.'))
            rec._initialize_stages()
            rec.state = 'pending'
            rec.date_submitted = fields.Datetime.now()
            rec._advance_to_next_stage()
            rec.message_post(
                body=_('Approval request submitted by %s.') % rec.requester_id.name,
                subtype_xmlid='mail.mt_note'
            )

    def action_cancel(self):
        """Cancel the approval request."""
        for rec in self:
            if rec.state in ('approved', 'refused'):
                raise UserError(_('Cannot cancel a completed request.'))
            rec.line_ids.filtered(lambda l: l.state == 'pending').write({'state': 'cancelled'})
            rec.state = 'cancelled'
            rec.message_post(
                body=_('Approval request cancelled by %s.') % self.env.user.name,
                subtype_xmlid='mail.mt_note'
            )

    def action_reset_to_draft(self):
        """Reset a cancelled request to draft for resubmission."""
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only cancelled requests can be reset to draft.'))
            rec.line_ids.unlink()
            rec.current_stage_id = False
            rec.state = 'draft'

    def _initialize_stages(self):
        """Create approval.request.line records for each applicable stage."""
        self.ensure_one()
        # Remove any existing lines
        self.line_ids.unlink()

        config = self.workflow_config_id
        try:
            target_record = self.env[self.res_model].browse(self.res_id)
        except Exception:
            raise UserError(_('Cannot find the linked document.'))

        lines = []
        for stage in config.stage_ids.sorted('sequence'):
            if not stage.is_applicable(target_record):
                continue
            approvers = stage.resolve_approvers(target_record)
            if not approvers:
                if stage.auto_approve_if_approver_missing:
                    # Create auto-approved line
                    lines.append({
                        'request_id': self.id,
                        'stage_id': stage.id,
                        'approver_id': self.env.ref('base.user_root').id,
                        'state': 'approved',
                        'note': _('Auto-approved: no approver resolved.'),
                        'date_approved': fields.Datetime.now(),
                    })
                continue

            if stage.approver_type == 'group' and stage.require_all_group_members:
                for user in approvers:
                    lines.append({
                        'request_id': self.id,
                        'stage_id': stage.id,
                        'approver_id': user.id,
                        'state': 'pending',
                    })
            else:
                # One approval line per stage; any matching user can approve
                for user in approvers:
                    lines.append({
                        'request_id': self.id,
                        'stage_id': stage.id,
                        'approver_id': user.id,
                        'state': 'pending',
                    })

        if lines:
            self.env['approval.request.line'].create(lines)

    def _advance_to_next_stage(self):
        """
        Move the request to the next pending stage.
        If all stages are done, mark as fully approved.
        """
        self.ensure_one()
        config = self.workflow_config_id

        # Find all stages that have pending lines
        all_stage_ids = self.line_ids.mapped('stage_id').sorted('sequence')

        for stage in all_stage_ids:
            stage_lines = self.line_ids.filtered(lambda l: l.stage_id == stage)
            pending = stage_lines.filtered(lambda l: l.state == 'pending')
            if pending:
                # This is the current blocking stage
                self.current_stage_id = stage
                self.state = 'in_progress'
                # Notify approvers
                if config.notify_next_approver:
                    self._notify_approvers(pending)
                return

        # All stages done → approved
        self._mark_approved()

    def _mark_approved(self):
        """Mark the request as fully approved."""
        self.ensure_one()
        self.state = 'approved'
        self.date_approved = fields.Datetime.now()
        self.current_stage_id = False
        self.message_post(
            body=_('✅ All approvals granted. This document is now fully approved.'),
            subtype_xmlid='mail.mt_note'
        )
        if self.workflow_config_id.notify_requester:
            self._notify_requester_approved()

    def _notify_approvers(self, lines):
        """Send notification to pending approvers."""
        self.ensure_one()
        for line in lines:
            try:
                self.message_notify(
                    partner_ids=line.approver_id.partner_id.ids,
                    subject=_('Approval Required: %s') % self.res_name,
                    body=_(
                        'Hello %s,<br/><br/>'
                        'Your approval is required for <b>%s</b> (Stage: %s).<br/>'
                        'Please review and approve or refuse.'
                    ) % (
                        line.approver_id.name,
                        self.res_name,
                        line.stage_id.name
                    ),
                    email_layout_xmlid='mail.mail_notification_light',
                )
            except Exception as e:
                _logger.warning('Could not notify approver %s: %s', line.approver_id.name, e)

    def _notify_requester_approved(self):
        """Notify the requester that all approvals are complete."""
        self.ensure_one()
        try:
            self.message_notify(
                partner_ids=self.requester_id.partner_id.ids,
                subject=_('Approved: %s') % self.res_name,
                body=_(
                    'Hello %s,<br/><br/>'
                    'Your request for <b>%s</b> has been fully approved.'
                ) % (self.requester_id.name, self.res_name),
                email_layout_xmlid='mail.mail_notification_light',
            )
        except Exception as e:
            _logger.warning('Could not notify requester: %s', e)

    def action_open_document(self):
        """Open the linked document."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def is_approved(self):
        """Return True if this request is fully approved."""
        self.ensure_one()
        return self.state == 'approved'

    @api.model
    def get_pending_for_user(self, user=None):
        """Return approval request lines pending for the given user (default: current user)."""
        if user is None:
            user = self.env.user
        return self.env['approval.request.line'].search([
            ('approver_id', '=', user.id),
            ('state', '=', 'pending'),
            ('request_id.state', 'in', ('pending', 'in_progress')),
        ])


class ApprovalRequestLine(models.Model):
    """
    One approval decision within an approval request.
    Tracks a single approver's response for a single stage.
    """
    _name = 'approval.request.line'
    _description = 'Approval Request Line'
    _order = 'stage_id, id'

    request_id = fields.Many2one(
        'approval.request',
        string='Approval Request',
        required=True,
        ondelete='cascade',
        index=True
    )
    stage_id = fields.Many2one(
        'approval.stage',
        string='Stage',
        required=True,
        ondelete='cascade'
    )
    stage_sequence = fields.Integer(
        related='stage_id.sequence',
        string='Stage Sequence',
        store=True
    )
    stage_name = fields.Char(
        related='stage_id.name',
        string='Stage Name',
        store=True
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Approver',
        required=True,
        index=True
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
        ('cancelled', 'Cancelled'),
    ], string='Decision', default='pending', index=True)

    note = fields.Text(string='Comment / Reason')
    date_approved = fields.Datetime(string='Decision Date')

    # Convenience fields
    workflow_config_id = fields.Many2one(
        related='request_id.workflow_config_id',
        string='Workflow',
        store=True
    )
    res_model = fields.Char(related='request_id.res_model', store=True, string='Model')
    res_id = fields.Integer(related='request_id.res_id', store=True, string='Record ID')
    res_name = fields.Char(related='request_id.res_name', store=True, string='Document')

    def _check_can_decide(self):
        """Ensure the current user is the designated approver for this line."""
        self.ensure_one()
        stage = self.stage_id
        request = self.request_id

        if self.state != 'pending':
            raise UserError(_('This approval has already been decided.'))
        if request.state not in ('pending', 'in_progress'):
            raise UserError(_('The request is not in an approvable state.'))
        if request.current_stage_id != stage:
            raise UserError(_(
                'This stage is not yet active. Please wait for stage "%s" to complete first.'
            ) % request.current_stage_id.name)

        # Check self-approval restriction
        if not stage.allow_self_approval and self.env.user == request.requester_id:
            raise UserError(_(
                'Self-approval is not allowed for stage "%s".'
            ) % stage.name)

        # Check that current user is authorized
        if self.approver_id != self.env.user:
            # For group approvals, check if the user belongs to the approver group
            if stage.approver_type == 'group' and stage.approver_group_id:
                if self.env.user not in stage.approver_group_id.users:
                    raise UserError(_('You are not authorized to approve at this stage.'))
            else:
                raise UserError(_('You are not the designated approver for this stage.'))

    def action_approve(self):
        """Approve this line."""
        for rec in self:
            rec._check_can_decide()
            rec.write({
                'state': 'approved',
                'date_approved': fields.Datetime.now(),
            })
            rec.request_id.message_post(
                body=_('✅ Stage <b>%s</b> approved by %s.') % (
                    rec.stage_id.name, self.env.user.name
                ),
                subtype_xmlid='mail.mt_note'
            )
            # Check if stage is now complete
            rec.request_id._check_stage_completion()

    def action_refuse(self):
        """Open wizard to refuse with a comment."""
        self.ensure_one()
        self._check_can_decide()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Refuse Approval'),
            'res_model': 'approval.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

    def do_refuse(self, note=''):
        """Perform the refusal."""
        self.ensure_one()
        self.write({
            'state': 'refused',
            'note': note,
            'date_approved': fields.Datetime.now(),
        })
        request = self.request_id
        request.state = 'refused'
        request.date_refused = fields.Datetime.now()
        request.message_post(
            body=_('❌ Stage <b>%s</b> refused by %s. Reason: %s') % (
                self.stage_id.name, self.env.user.name, note or _('No reason given')
            ),
            subtype_xmlid='mail.mt_note'
        )
        # Cancel remaining pending lines
        request.line_ids.filtered(lambda l: l.state == 'pending').write({
            'state': 'cancelled'
        })
        if request.workflow_config_id.notify_requester:
            try:
                request.message_notify(
                    partner_ids=request.requester_id.partner_id.ids,
                    subject=_('Approval Refused: %s') % request.res_name,
                    body=_(
                        'Hello %s,<br/><br/>'
                        'Your request for <b>%s</b> has been refused at stage <b>%s</b>.<br/>'
                        'Reason: %s'
                    ) % (
                        request.requester_id.name,
                        request.res_name,
                        self.stage_id.name,
                        note or _('No reason given')
                    ),
                    email_layout_xmlid='mail.mail_notification_light',
                )
            except Exception as e:
                _logger.warning('Could not notify requester of refusal: %s', e)


# Extend ApprovalRequest with stage completion logic
def _check_stage_completion(self):
    """
    Called after an approval line is approved.
    Checks if the current stage is complete and advances to the next.
    """
    self.ensure_one()
    stage = self.current_stage_id
    if not stage:
        return

    stage_lines = self.line_ids.filtered(lambda l: l.stage_id == stage)

    if stage.approver_type == 'group' and not stage.require_all_group_members:
        # Any one approval is enough
        approved = stage_lines.filtered(lambda l: l.state == 'approved')
        if approved:
            # Cancel the remaining pending lines for this stage
            stage_lines.filtered(lambda l: l.state == 'pending').write({'state': 'cancelled'})
            self._advance_to_next_stage()
    else:
        # All pending must approve
        pending = stage_lines.filtered(lambda l: l.state == 'pending')
        if not pending:
            self._advance_to_next_stage()


ApprovalRequest._check_stage_completion = _check_stage_completion
