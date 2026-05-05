# -*- coding: utf-8 -*-
"""
Approval Request Model
Each approval request tracks the approval process for one specific record
through all stages of a cycle.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class UnivApprovalRequest(models.Model):
    """
    Tracks the state of an approval cycle for a specific record.
    Links the source record (any model) to the cycle and current stage.
    """
    _name = 'univ.approval.request'
    _description = 'Approval Request'
    _inherit = ['mail.thread']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # -------------------------------------------------------------------------
    # Odoo 19 compatibility: mail.activity._compute_approver_id looks for
    # 'approver_ids' in any model inheriting mail.thread. This computed
    # Many2many satisfies that dependency without affecting business logic.
    # -------------------------------------------------------------------------
    approver_ids = fields.Many2many(
        comodel_name='res.users',
        relation='approval_request_dummy_approver_rel',
        column1='request_id',
        column2='user_id',
        string='Activity Approvers',
        compute='_compute_dummy_approver_ids',
    )

    def _compute_dummy_approver_ids(self):
        for rec in self:
            rec.approver_ids = self.env['res.users']

    # -------------------------------------------------------------------------
    # Identity & Linking
    # -------------------------------------------------------------------------

    cycle_id = fields.Many2one(
        comodel_name='univ.approval.cycle',
        string='Approval Cycle',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    model_name = fields.Char(
        related='cycle_id.model_name',
        string='Model',
        store=True,
        readonly=True,
    )
    res_id = fields.Integer(
        string='Record ID',
        required=True,
        index=True,
        help='ID of the record in the target model that this request covers',
    )
    res_name = fields.Char(
        string='Record Name',
        compute='_compute_res_name',
        store=True,
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name_field',
        store=True,
    )

    # -------------------------------------------------------------------------
    # State & Progress
    # -------------------------------------------------------------------------

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('pending', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        index=True,
    )
    current_stage_id = fields.Many2one(
        comodel_name='univ.approval.stage',
        string='Current Stage',
        tracking=True,
    )
    current_stage_sequence = fields.Integer(
        related='current_stage_id.sequence',
        string='Stage Sequence',
        store=True,
    )
    progress = fields.Float(
        string='Progress (%)',
        compute='_compute_progress',
        store=True,
    )

    # -------------------------------------------------------------------------
    # Participants
    # -------------------------------------------------------------------------

    requester_id = fields.Many2one(
        comodel_name='res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    log_ids = fields.One2many(
        comodel_name='univ.approval.log',
        inverse_name='request_id',
        string='Approval History',
    )
    log_count = fields.Integer(
        string='Log Entries',
        compute='_compute_log_count',
    )

    # -------------------------------------------------------------------------
    # Metadata
    # -------------------------------------------------------------------------

    date_start = fields.Datetime(
        string='Start Date',
        readonly=True,
    )
    date_end = fields.Datetime(
        string='End Date',
        readonly=True,
    )
    notes = fields.Text(
        string='Notes / Justification',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    # -------------------------------------------------------------------------
    # Computed
    # -------------------------------------------------------------------------

    @api.depends('res_id', 'model_name')
    def _compute_res_name(self):
        for rec in self:
            if rec.model_name and rec.res_id:
                try:
                    source = self.env[rec.model_name].browse(rec.res_id)
                    rec.res_name = source.display_name if source.exists() else str(rec.res_id)
                except Exception:
                    rec.res_name = str(rec.res_id)
            else:
                rec.res_name = ''

    @api.depends('cycle_id', 'res_name')
    def _compute_display_name_field(self):
        for rec in self:
            cycle_name = rec.cycle_id.name or ''
            res_name = rec.res_name or ''
            rec.display_name = f'{cycle_name} / {res_name}' if res_name else cycle_name

    @api.depends('log_ids', 'cycle_id.stage_ids')
    def _compute_progress(self):
        for rec in self:
            total = len(rec.cycle_id.stage_ids)
            if not total:
                rec.progress = 0.0
                continue
            if rec.state == 'approved':
                rec.progress = 100.0
            elif rec.state in ('draft', 'cancelled', 'rejected'):
                rec.progress = 0.0
            else:
                approved_stages = rec.log_ids.filtered(
                    lambda l: l.action == 'approve'
                ).mapped('stage_id')
                rec.progress = (len(approved_stages) / total) * 100.0

    @api.depends('log_ids')
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    # -------------------------------------------------------------------------
    # Workflow Actions
    # -------------------------------------------------------------------------

    def action_submit(self):
        """Submit the request and move to the first stage."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft requests can be submitted.'))
        stages = self.cycle_id.get_ordered_stages()
        if not stages:
            raise UserError(_('The approval cycle "%s" has no stages defined.') % self.cycle_id.name)
        first_stage = stages[0]
        self.write({
            'state': 'pending',
            'current_stage_id': first_stage.id,
            'date_start': fields.Datetime.now(),
        })
        self._notify_approvers(first_stage)
        self.message_post(
            body=_('Approval request submitted. Awaiting approval at stage: %s') % first_stage.name,
            message_type='notification',
        )

    def action_approve(self, comment=False):
        """
        Approve the current stage.
        Moves to next stage or marks as fully approved.
        """
        self.ensure_one()
        self._check_approver_access()
        self._create_log(action='approve', comment=comment)

        if self._is_stage_complete():
            self._advance_or_complete()

    def action_reject(self, comment=False):
        """Reject the request at the current stage."""
        self.ensure_one()
        self._check_approver_access()
        self._create_log(action='reject', comment=comment)
        self.write({
            'state': 'rejected',
            'date_end': fields.Datetime.now(),
        })
        self._apply_field_update('rejected')
        self.message_post(
            body=_('Request rejected at stage "%s". Reason: %s') % (
                self.current_stage_id.name, comment or _('No reason provided')
            ),
            message_type='notification',
        )

    def action_cancel(self):
        """Cancel the approval request."""
        self.ensure_one()
        if self.state not in ('draft', 'pending'):
            raise UserError(_('Only draft or pending requests can be cancelled.'))
        self.write({
            'state': 'cancelled',
            'date_end': fields.Datetime.now(),
        })
        self._create_log(action='cancel')
        self.message_post(
            body=_('Approval request cancelled.'),
            message_type='notification',
        )

    def action_reset_to_draft(self):
        """Reset to draft so the request can be resubmitted."""
        self.ensure_one()
        if self.state not in ('rejected', 'cancelled'):
            raise UserError(_('Only rejected or cancelled requests can be reset to draft.'))
        self.write({
            'state': 'draft',
            'current_stage_id': False,
            'date_start': False,
            'date_end': False,
        })
        self.message_post(
            body=_('Request reset to draft.'),
            message_type='notification',
        )

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _check_approver_access(self):
        """Verify the current user is an eligible approver for the current stage."""
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_('This request is not in a pending state.'))
        stage = self.current_stage_id
        if not stage:
            raise UserError(_('No current stage found for this request.'))

        # Super user / admin bypass
        if self.env.user._is_admin():
            return

        approvers = stage.get_approvers_for_record(self._get_source_record())
        if self.env.user not in approvers:
            raise UserError(
                _('You are not authorized to approve at stage "%s".') % stage.name
            )
        # Check self-approval restriction
        if not stage.allow_self_approval and self.env.user == self.requester_id:
            raise UserError(
                _('Self-approval is not allowed at stage "%s".') % stage.name
            )

    def _is_stage_complete(self):
        """
        Determine if the current stage has received enough approvals.
        If require_all: all approvers must have logged an approve.
        Else: one approve is enough.
        """
        self.ensure_one()
        stage = self.current_stage_id
        source_record = self._get_source_record()
        approvers = stage.get_approvers_for_record(source_record)

        if not stage.require_all:
            return True  # One approval is enough

        # All must approve: check how many distinct approvers already approved
        approved_users = self.log_ids.filtered(
            lambda l: l.stage_id == stage and l.action == 'approve'
        ).mapped('approver_id')
        return set(approvers.ids).issubset(set(approved_users.ids))

    def _advance_or_complete(self):
        """Move to the next stage or mark the request as fully approved."""
        self.ensure_one()
        stages = self.cycle_id.get_ordered_stages()
        current_seq = self.current_stage_id.sequence
        next_stages = stages.filtered(lambda s: s.sequence > current_seq)

        if next_stages:
            next_stage = next_stages[0]
            self.write({'current_stage_id': next_stage.id})
            self._notify_approvers(next_stage)
            self.message_post(
                body=_('Stage "%s" approved. Moved to stage "%s".') % (
                    self.current_stage_id.name, next_stage.name
                ),
                message_type='notification',
            )
        else:
            # All stages done → fully approved
            self.write({
                'state': 'approved',
                'date_end': fields.Datetime.now(),
            })
            self._apply_field_update('approved')
            self.message_post(
                body=_('All approval stages completed. Request is APPROVED.'),
                message_type='notification',
            )

    def _create_log(self, action, comment=False):
        """Create an approval log entry."""
        self.ensure_one()
        self.env['univ.approval.log'].create({
            'request_id': self.id,
            'stage_id': self.current_stage_id.id,
            'approver_id': self.env.user.id,
            'action': action,
            'comment': comment or '',
            'date': fields.Datetime.now(),
        })

    def _notify_approvers(self, stage):
        """Send email notification to approvers of the given stage."""
        if not stage.notify_approvers:
            return
        source_record = self._get_source_record()
        approvers = stage.get_approvers_for_record(source_record)
        if not approvers:
            return
        template = stage.email_template_id or self.env.ref(
            'universal_approval_cycle.mail_template_approval_notification',
            raise_if_not_found=False,
        )
        if template:
            try:
                for approver in approvers:
                    template.with_context(
                        approver=approver,
                        stage=stage,
                    ).send_mail(self.id, force_send=False)
            except Exception as e:
                _logger.warning('Failed to send approval notification: %s', e)

    def _get_source_record(self):
        """Return the source record that this request is for."""
        self.ensure_one()
        if self.model_name and self.res_id:
            return self.env[self.model_name].browse(self.res_id)
        return self.env['base']

    def _apply_field_update(self, result):
        """
        Update a field on the source record after cycle completion/rejection.
        Configured on the cycle.
        """
        self.ensure_one()
        cycle = self.cycle_id
        if not cycle.approve_field_id:
            return
        field_name = cycle.approve_field_id.name
        value = cycle.approve_field_value if result == 'approved' else cycle.reject_field_value
        if value is not None:
            source = self._get_source_record()
            if source.exists():
                try:
                    source.write({field_name: value})
                except Exception as e:
                    _logger.warning('Could not update field %s on record: %s', field_name, e)

    # -------------------------------------------------------------------------
    # Smart Button / Action
    # -------------------------------------------------------------------------

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval History'),
            'res_model': 'univ.approval.log',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
        }

    def action_open_record(self):
        """Open the source record."""
        self.ensure_one()
        model = self.env[self.model_name]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Source Record'),
            'res_model': self.model_name,
            'view_mode': 'form',
            'res_id': self.res_id,
        }
