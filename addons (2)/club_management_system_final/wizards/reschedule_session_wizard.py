# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class RescheduleSessionWizard(models.TransientModel):
    _name = 'club.reschedule.session.wizard'
    _description = 'Reschedule Session Wizard'

    session_id = fields.Many2one(
        'club.session', string='Session',
        required=True, ondelete='cascade',
    )
    # Current values (read-only display)
    current_date = fields.Date(related='session_id.date', string='Current Date', readonly=True)
    current_start = fields.Float(related='session_id.time_start', string='Current Start', readonly=True)
    current_end = fields.Float(related='session_id.time_end', string='Current End', readonly=True)
    trainer_id = fields.Many2one(related='session_id.trainer_id', string='Trainer', readonly=True)
    facility_id = fields.Many2one(related='session_id.facility_id', string='Facility', readonly=True)

    # New values
    date = fields.Date(string='New Date', required=True)
    time_start = fields.Float(string='New Start Time', required=True)
    time_end = fields.Float(string='New End Time', required=True)
    reason = fields.Char(string='Reason', help='Reason for rescheduling (logged in chatter)')

    # Conflict detection (computed)
    has_trainer_conflict = fields.Boolean(compute='_compute_conflicts', string='Trainer Conflict')
    has_facility_conflict = fields.Boolean(compute='_compute_conflicts', string='Facility Conflict')
    conflict_message = fields.Char(compute='_compute_conflicts', string='Conflict Details')

    @api.depends('date', 'time_start', 'time_end', 'session_id')
    def _compute_conflicts(self):
        for wiz in self:
            wiz.has_trainer_conflict = False
            wiz.has_facility_conflict = False
            wiz.conflict_message = ''

            if not (wiz.date and wiz.session_id):
                continue

            messages = []

            # Check trainer conflict
            trainer = wiz.session_id.trainer_id
            if trainer:
                conflict = self.env['club.session'].search([
                    ('id', '!=', wiz.session_id.id),
                    ('trainer_id', '=', trainer.id),
                    ('date', '=', wiz.date),
                    ('state', 'not in', ('cancelled',)),
                    ('time_start', '<', wiz.time_end),
                    ('time_end', '>', wiz.time_start),
                ], limit=1)
                if conflict:
                    wiz.has_trainer_conflict = True
                    messages.append(
                        f'Trainer "{trainer.name}" is busy: "{conflict.name}"'
                    )

            # Check facility conflict
            facility = wiz.session_id.facility_id
            if facility:
                conflict = self.env['club.session'].search([
                    ('id', '!=', wiz.session_id.id),
                    ('facility_id', '=', facility.id),
                    ('date', '=', wiz.date),
                    ('state', 'not in', ('cancelled',)),
                    ('time_start', '<', wiz.time_end),
                    ('time_end', '>', wiz.time_start),
                ], limit=1)
                if not conflict:
                    # Also check rentals
                    start_h = wiz.time_start
                    end_h = wiz.time_end
                    rental_conflict = self.env['club.rental'].search([
                        ('facility_id', '=', facility.id),
                        ('state', 'not in', ('cancelled',)),
                        ('date_start', '<', '%s %02d:%02d:00' % (
                            wiz.date,
                            int(end_h),
                            int((end_h - int(end_h)) * 60),
                        )),
                        ('date_end', '>', '%s %02d:%02d:00' % (
                            wiz.date,
                            int(start_h),
                            int((start_h - int(start_h)) * 60),
                        )),
                    ], limit=1)
                    if rental_conflict:
                        wiz.has_facility_conflict = True
                        messages.append(
                            f'Facility "{facility.name}" has a rental booking: "{rental_conflict.name}"'
                        )
                else:
                    wiz.has_facility_conflict = True
                    messages.append(
                        f'Facility "{facility.name}" is booked: "{conflict.name}"'
                    )

            wiz.conflict_message = ' | '.join(messages) if messages else ''

    @api.constrains('time_start', 'time_end')
    def _check_times(self):
        for wiz in self:
            if wiz.time_end <= wiz.time_start:
                raise ValidationError('End time must be after start time.')

    def action_reschedule(self):
        self.ensure_one()
        if self.has_trainer_conflict or self.has_facility_conflict:
            raise UserError(
                f'Cannot reschedule due to conflicts:\n{self.conflict_message}'
            )
        if self.session_id.state == 'done':
            raise UserError('Cannot reschedule a completed session.')

        old_date = self.session_id.date
        old_start = self.session_id.time_start
        old_end = self.session_id.time_end

        self.session_id.write({
            'date': self.date,
            'time_start': self.time_start,
            'time_end': self.time_end,
        })

        # Log in chatter
        def fmt_time(t):
            h = int(t)
            m = int((t - h) * 60)
            return f'{h:02d}:{m:02d}'

        reason_text = f' — Reason: {self.reason}' if self.reason else ''
        self.session_id.message_post(
            body=(
                f'<b>Session Rescheduled</b>{reason_text}<br/>'
                f'From: {old_date} {fmt_time(old_start)}–{fmt_time(old_end)}<br/>'
                f'To: {self.date} {fmt_time(self.time_start)}–{fmt_time(self.time_end)}'
            )
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Session Rescheduled',
                'message': (
                    f'"{self.session_id.name}" moved to '
                    f'{self.date} {fmt_time(self.time_start)}–{fmt_time(self.time_end)}'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_reschedule_force(self):
        """Reschedule even if conflicts exist (admin override)."""
        self.ensure_one()
        if self.session_id.state == 'done':
            raise UserError('Cannot reschedule a completed session.')
        self.session_id.write({
            'date': self.date,
            'time_start': self.time_start,
            'time_end': self.time_end,
        })
        msg = '⚠️ <b>Force-rescheduled</b> despite conflicts.'
        if self.reason:
            msg += f' Reason: {self.reason}'
        self.session_id.message_post(body=msg)
        return {'type': 'ir.actions.act_window_close'}
