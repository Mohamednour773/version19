# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta


class ClubSession(models.Model):
    _name = 'club.session'
    _description = 'Club Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, time_start'

    name = fields.Char(string='Session', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    # ── Class link ──────────────────────────────────────────
    class_id = fields.Many2one(
        'club.class', string='Class', required=True,
        ondelete='cascade', tracking=True,
    )
    branch_id = fields.Many2one(related='class_id.branch_id', string='Branch', store=True)
    # Primary trainer (kept for backward compat & record rules)
    trainer_id = fields.Many2one(
        'club.trainer', string='Primary Trainer',
        required=True, ondelete='restrict', tracking=True,
    )
    facility_id = fields.Many2one(related='class_id.facility_id', string='Facility', store=True)
    class_type = fields.Selection(related='class_id.class_type', string='Type', store=True)
    specialization = fields.Selection(related='class_id.specialization', string='Sport', store=True)

    # ── Multi-trainer lines ─────────────────────────────────
    trainer_line_ids = fields.One2many(
        'club.session.trainer.line', 'session_id',
        string='Trainer Lines',
    )
    trainer_count = fields.Integer(
        compute='_compute_trainer_count', string='Trainers', store=True,
    )

    # ── Schedule ────────────────────────────────────────────
    date = fields.Date(string='Date', required=True, tracking=True)
    time_start = fields.Float(string='Start Time', required=True)
    time_end = fields.Float(string='End Time', required=True)
    duration = fields.Float(string='Duration (hrs)', compute='_compute_duration', store=True)
    datetime_start = fields.Datetime(
        compute='_compute_datetimes', inverse='_inverse_datetimes',
        store=True, string='Start DateTime',
    )
    datetime_end = fields.Datetime(
        compute='_compute_datetimes', inverse='_inverse_datetimes',
        store=True, string='End DateTime',
    )

    # ── Capacity ────────────────────────────────────────────
    max_capacity = fields.Integer(related='class_id.max_capacity', string='Max Capacity', store=True)
    enrolled_count = fields.Integer(
        compute='_compute_attendance_stats', string='Enrolled', store=True,
    )
    attended_count = fields.Integer(
        compute='_compute_attendance_stats', string='Attended', store=True,
    )
    available_spots = fields.Integer(
        compute='_compute_attendance_stats', string='Available Spots', store=True,
    )
    is_full = fields.Boolean(
        compute='_compute_attendance_stats', string='Full', store=True,
    )

    # ── Members ─────────────────────────────────────────────
    membership_ids = fields.Many2many(
        'club.membership',
        'club_session_membership_rel',
        'session_id', 'membership_id',
        string='Enrolled Members',
    )

    # ── Attendance ──────────────────────────────────────────
    attendance_ids = fields.One2many('club.attendance', 'session_id', string='Attendance')

    # ── Commission ──────────────────────────────────────────
    commission_ids = fields.One2many('club.trainer.commission', 'session_id', string='Commissions')

    notes = fields.Text(string='Notes')
    color = fields.Integer(compute='_compute_color', string='Color', store=True)

    # ════════════════════════════════════════════════════
    # COMPUTE METHODS
    # ════════════════════════════════════════════════════

    @api.depends('class_id', 'date', 'trainer_id')
    def _compute_name(self):
        for s in self:
            parts = []
            if s.class_id:
                parts.append(s.class_id.name)
            if s.date:
                parts.append(str(s.date))
            s.name = ' - '.join(parts) if parts else 'Session'

    @api.depends('time_start', 'time_end')
    def _compute_duration(self):
        for s in self:
            s.duration = max(0, s.time_end - s.time_start)

    @api.depends('date', 'time_start', 'time_end')
    def _compute_datetimes(self):
        for s in self:
            if s.date and s.time_start is not False:
                h = int(s.time_start)
                m = int((s.time_start - h) * 60)
                s.datetime_start = datetime.combine(
                    s.date, datetime.min.time()
                ).replace(hour=h, minute=m)
            else:
                s.datetime_start = False

            if s.date and s.time_end is not False:
                h = int(s.time_end)
                m = int((s.time_end - h) * 60)
                s.datetime_end = datetime.combine(
                    s.date, datetime.min.time()
                ).replace(hour=h, minute=m)
            else:
                s.datetime_end = False

    def _inverse_datetimes(self):
        """
        Called when calendar drag & drop writes datetime_start / datetime_end.
        Converts back to date + float time fields.
        """
        for s in self:
            if s.datetime_start:
                s.date = s.datetime_start.date()
                s.time_start = s.datetime_start.hour + s.datetime_start.minute / 60.0
            if s.datetime_end:
                s.time_end = s.datetime_end.hour + s.datetime_end.minute / 60.0

    @api.depends('attendance_ids', 'attendance_ids.state', 'membership_ids', 'max_capacity')
    def _compute_attendance_stats(self):
        for s in self:
            s.enrolled_count = len(s.membership_ids)
            s.attended_count = len(s.attendance_ids.filtered(lambda a: a.state == 'attended'))
            s.available_spots = max(0, (s.max_capacity or 0) - s.enrolled_count)
            s.is_full = s.enrolled_count >= (s.max_capacity or 0)

    @api.depends('trainer_line_ids')
    def _compute_trainer_count(self):
        for s in self:
            s.trainer_count = len(s.trainer_line_ids) or (1 if s.trainer_id else 0)

    @api.depends('state')
    def _compute_color(self):
        color_map = {
            'draft': 0, 'confirmed': 4, 'in_progress': 2,
            'done': 10, 'cancelled': 1,
        }
        for s in self:
            s.color = color_map.get(s.state, 0)

    # ════════════════════════════════════════════════════
    # CONSTRAINTS
    # ════════════════════════════════════════════════════

    @api.constrains('time_start', 'time_end')
    def _check_time(self):
        for s in self:
            if s.time_end <= s.time_start:
                raise ValidationError('End time must be after start time.')

    @api.constrains('trainer_id', 'date', 'time_start', 'time_end')
    def _check_trainer_overlap(self):
        for s in self:
            if not s.trainer_id or not s.date:
                continue
            overlapping = self.search([
                ('id', '!=', s.id),
                ('trainer_id', '=', s.trainer_id.id),
                ('date', '=', s.date),
                ('state', 'not in', ('cancelled',)),
                ('time_start', '<', s.time_end),
                ('time_end', '>', s.time_start),
            ])
            if overlapping:
                raise ValidationError(
                    f'Trainer {s.trainer_id.name} already has session '
                    f'"{overlapping[0].name}" at this time on {s.date}.'
                )

    @api.constrains('facility_id', 'date', 'time_start', 'time_end')
    def _check_facility_overlap(self):
        for s in self:
            if not s.facility_id or not s.date:
                continue
            overlapping = self.search([
                ('id', '!=', s.id),
                ('facility_id', '=', s.facility_id.id),
                ('date', '=', s.date),
                ('state', 'not in', ('cancelled',)),
                ('time_start', '<', s.time_end),
                ('time_end', '>', s.time_start),
            ])
            if overlapping:
                raise ValidationError(
                    f'Facility {s.facility_id.name} is already booked '
                    f'for "{overlapping[0].name}" on {s.date}.'
                )

    # ════════════════════════════════════════════════════
    # ENROLLMENT WITH PACKAGE ENFORCEMENT
    # ════════════════════════════════════════════════════

    def _validate_membership_enrollment(self, membership):
        """
        Called before enrolling a member in this session.
        Enforces package limits at booking stage (before attendance).
        """
        if membership.state not in ('active', 'confirmed'):
            raise ValidationError(
                f'Membership "{membership.name}" is not active '
                f'(current state: {membership.state}).'
            )

        # ── Total sessions limit ────────────────────────────
        if membership.sessions_remaining <= 0:
            raise ValidationError(
                f'Client "{membership.partner_id.name}" has used all '
                f'{membership.total_sessions} sessions in "{membership.name}".'
            )

        # ── Weekly limit ────────────────────────────────────
        from datetime import date as date_cls, timedelta
        today = self.date or date_cls.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        # Count enrolled sessions this week (already booked, not just attended)
        enrolled_this_week = self.env['club.session'].search_count([
            ('id', '!=', self.id),
            ('membership_ids', 'in', [membership.id]),
            ('date', '>=', week_start),
            ('date', '<=', week_end),
            ('state', 'not in', ('cancelled',)),
        ])
        if enrolled_this_week >= membership.sessions_per_week:
            raise ValidationError(
                f'Client "{membership.partner_id.name}" already has '
                f'{enrolled_this_week} session(s) booked this week. '
                f'Package limit is {membership.sessions_per_week}/week.'
            )

        # ── Package type vs class type ──────────────────────
        pkg = membership.package_id
        if pkg.package_type not in ('both', 'group', 'private'):
            pass  # rental-only packages cannot enroll in classes
        if pkg.package_type == 'group' and self.class_type == 'private':
            raise ValidationError(
                f'Package "{pkg.name}" only covers group classes, '
                f'not private sessions.'
            )
        if pkg.package_type == 'private' and self.class_type == 'group':
            raise ValidationError(
                f'Package "{pkg.name}" only covers private sessions, '
                f'not group classes.'
            )

    def write(self, vals):
        """
        Intercept membership_ids changes to enforce package limits
        at enrollment (not just at attendance time).
        Also handles drag-and-drop rescheduling validation.
        """
        # Detect date/time changes (from calendar drag & drop)
        reschedule_fields = {'date', 'time_start', 'time_end', 'datetime_start', 'datetime_end'}
        if reschedule_fields & set(vals.keys()):
            for session in self:
                if session.state == 'done':
                    raise UserError('Cannot reschedule a completed session.')
                if session.state == 'cancelled':
                    raise UserError('Cannot reschedule a cancelled session.')

        result = super().write(vals)

        # Validate enrollments after membership_ids are written
        if 'membership_ids' in vals:
            for session in self:
                for membership in session.membership_ids:
                    try:
                        session._validate_membership_enrollment(membership)
                    except ValidationError:
                        # Re-raise — Odoo will roll back the transaction
                        raise

        return result

    def action_enroll_membership(self, membership_id):
        """
        Safely enroll a membership. Validates package limits BEFORE writing.
        """
        self.ensure_one()
        membership = self.env['club.membership'].browse(membership_id)
        self._validate_membership_enrollment(membership)
        if self.is_full:
            raise UserError(
                f'Session "{self.name}" is fully booked '
                f'(capacity: {self.max_capacity}).'
            )
        self.membership_ids = [(4, membership_id)]

    # ════════════════════════════════════════════════════
    # STATE TRANSITIONS
    # ════════════════════════════════════════════════════

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        for session in self:
            session.state = 'done'
            session._generate_commission_multi()

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    # ════════════════════════════════════════════════════
    # COMMISSION (multi-trainer aware)
    # ════════════════════════════════════════════════════

    def _generate_commission_multi(self):
        """
        Generate commission records supporting multi-trainer sessions.
        - If trainer_line_ids exist → split revenue per line
        - Otherwise → use primary trainer (backward compat)
        """
        self.ensure_one()
        if self.commission_ids:
            return  # Already generated

        attended = self.attendance_ids.filtered(lambda a: a.state == 'attended')
        attended_count = len(attended)
        if not attended_count:
            return

        # Calculate total session revenue
        total_revenue = sum(
            (att.membership_id.price / att.membership_id.package_id.total_sessions)
            for att in attended
            if att.membership_id and att.membership_id.package_id.total_sessions
        )

        if self.trainer_line_ids:
            # ── Multi-trainer: distribute revenue by share ──
            trainer_count = len(self.trainer_line_ids)
            for line in self.trainer_line_ids:
                share = total_revenue / trainer_count
                line.write({
                    'attended_share': attended_count,
                    'revenue_share': share,
                })
                line.action_generate_commission()
        else:
            # ── Single primary trainer (backward compat) ────
            if not self.trainer_id:
                return
            self.env['club.trainer.commission'].create({
                'trainer_id': self.trainer_id.id,
                'session_id': self.id,
                'date': self.date,
                'attended_count': attended_count,
                'session_revenue': total_revenue,
                'commission_pct': self.trainer_id.commission_pct,
            })

    # ════════════════════════════════════════════════════
    # ATTENDANCE
    # ════════════════════════════════════════════════════

    def action_take_attendance(self):
        self.ensure_one()
        existing_member_ids = self.attendance_ids.mapped('membership_id').ids
        for membership in self.membership_ids:
            if membership.id not in existing_member_ids:
                self.env['club.attendance'].create({
                    'session_id': self.id,
                    'membership_id': membership.id,
                    'partner_id': membership.partner_id.id,
                    'date': self.date,
                })
        return {
            'type': 'ir.actions.act_window',
            'name': f'Attendance — {self.name}',
            'res_model': 'club.attendance',
            'view_mode': 'list,form',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id},
        }

    def action_reschedule(self):
        """Open quick-reschedule wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reschedule Session',
            'res_model': 'club.reschedule.session.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_session_id': self.id,
                'default_date': self.date,
                'default_time_start': self.time_start,
                'default_time_end': self.time_end,
            },
        }
