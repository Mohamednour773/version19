# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import date, timedelta


class ClubAttendance(models.Model):
    _name = 'club.attendance'
    _description = 'Session Attendance'
    _order = 'date desc, session_id'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=True)

    session_id = fields.Many2one(
        'club.session',
        string='Session',
        required=True,
        ondelete='cascade',
    )
    membership_id = fields.Many2one(
        'club.membership',
        string='Membership',
        required=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Client',
        required=True,
        ondelete='restrict',
    )

    # From session
    branch_id = fields.Many2one(
        related='session_id.branch_id',
        string='Branch',
        store=True,
    )
    trainer_id = fields.Many2one(
        related='session_id.trainer_id',
        string='Trainer',
        store=True,
    )
    class_id = fields.Many2one(
        related='session_id.class_id',
        string='Class',
        store=True,
    )

    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
    )
    check_in = fields.Datetime(string='Check In')
    check_out = fields.Datetime(string='Check Out')

    state = fields.Selection([
        ('present', 'Present'),
        ('attended', 'Attended'),
        ('absent', 'Absent'),
        ('excused', 'Excused'),
    ], string='Status', default='present')

    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('session_membership_unique', 'UNIQUE(session_id, membership_id)',
         'A member can only have one attendance record per session.'),
    ]

    @api.depends('partner_id', 'session_id')
    def _compute_display_name(self):
        for att in self:
            parts = []
            if att.partner_id:
                parts.append(att.partner_id.name)
            if att.session_id:
                parts.append(att.session_id.name)
            att.display_name = ' / '.join(parts) if parts else 'Attendance'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            # Validate weekly limit before marking as attended
            if rec.membership_id and rec.state == 'attended':
                rec._validate_session_limits()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'state' in vals and vals['state'] == 'attended':
            for rec in self:
                rec._validate_session_limits()
        return result

    def _validate_session_limits(self):
        """Check membership session limits."""
        mem = self.membership_id
        if not mem:
            return

        # Check total sessions
        attended = self.env['club.attendance'].search_count([
            ('membership_id', '=', mem.id),
            ('state', '=', 'attended'),
            ('id', '!=', self.id),
        ])
        if attended >= mem.total_sessions:
            raise ValidationError(
                f'Client {mem.partner_id.name} has used all {mem.total_sessions} sessions '
                f'in membership {mem.name}.'
            )

        # Check weekly limit
        if self.date and mem.sessions_per_week:
            att_date = self.date
            week_start = att_date - timedelta(days=att_date.weekday())
            week_end = week_start + timedelta(days=6)
            weekly = self.env['club.attendance'].search_count([
                ('membership_id', '=', mem.id),
                ('state', '=', 'attended'),
                ('date', '>=', week_start),
                ('date', '<=', week_end),
                ('id', '!=', self.id),
            ])
            if weekly >= mem.sessions_per_week:
                raise ValidationError(
                    f'Client {mem.partner_id.name} has already attended {mem.sessions_per_week} '
                    f'session(s) this week (limit for membership {mem.name}).'
                )

    def action_mark_attended(self):
        for att in self:
            if att.session_id.state not in ('confirmed', 'in_progress', 'done'):
                raise UserError('Session must be confirmed or in progress to mark attendance.')
            att.state = 'attended'
            if not att.check_in:
                att.check_in = fields.Datetime.now()

    def action_mark_absent(self):
        self.write({'state': 'absent'})

    def action_mark_excused(self):
        self.write({'state': 'excused'})

    @api.constrains('membership_id', 'session_id')
    def _check_membership_active(self):
        for att in self:
            if att.membership_id.state not in ('active', 'confirmed'):
                raise ValidationError(
                    f'Membership {att.membership_id.name} is not active. '
                    f'Current state: {att.membership_id.state}'
                )
