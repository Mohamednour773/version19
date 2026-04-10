# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import date, timedelta


class GenerateSessionsWizard(models.TransientModel):
    _name = 'club.generate.sessions.wizard'
    _description = 'Generate Recurring Sessions Wizard'

    class_id = fields.Many2one(
        'club.class',
        string='Class',
        required=True,
        ondelete='cascade',
    )
    date_start = fields.Date(
        string='From Date',
        required=True,
        default=fields.Date.context_today,
    )
    date_end = fields.Date(
        string='To Date',
        required=True,
    )
    trainer_id = fields.Many2one(
        'club.trainer',
        string='Trainer',
        related='class_id.trainer_id',
        readonly=True,
    )
    time_start = fields.Float(
        string='Start Time',
        related='class_id.time_start',
        readonly=True,
    )
    time_end = fields.Float(
        string='End Time',
        related='class_id.time_end',
        readonly=True,
    )
    skip_existing = fields.Boolean(
        string='Skip Existing Dates',
        default=True,
        help='If checked, dates that already have a session will be skipped instead of raising an error.',
    )
    preview_count = fields.Integer(
        string='Sessions to Generate',
        compute='_compute_preview_count',
    )

    @api.onchange('class_id', 'date_start')
    def _onchange_class(self):
        if self.class_id and self.class_id.recurrence_end_date:
            self.date_end = self.class_id.recurrence_end_date
        elif self.date_start:
            self.date_end = self.date_start + timedelta(weeks=4)

    @api.depends('class_id', 'date_start', 'date_end')
    def _compute_preview_count(self):
        for wizard in self:
            wizard.preview_count = len(wizard._get_session_dates())

    def _get_session_dates(self):
        """Return list of dates on which sessions should be created."""
        if not self.class_id or not self.date_start or not self.date_end:
            return []
        if self.date_end < self.date_start:
            return []

        weekdays = self.class_id.get_weekday_list()
        if not weekdays:
            return []

        dates = []
        current = self.date_start
        while current <= self.date_end:
            if current.weekday() in weekdays:
                dates.append(current)
            current += timedelta(days=1)
        return dates

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_end < wizard.date_start:
                raise ValidationError('End date must be on or after start date.')

    def action_generate(self):
        self.ensure_one()
        cls = self.class_id

        if cls.state not in ('confirmed',):
            raise UserError(
                f'Class "{cls.name}" must be in "Confirmed" state to generate sessions.'
            )
        if not cls.package_ids:
            raise UserError(
                f'Class "{cls.name}" must be linked to at least one package before generating sessions.'
            )

        session_dates = self._get_session_dates()
        if not session_dates:
            raise UserError(
                'No matching weekdays found in the selected date range. '
                'Please check the class schedule (Mon–Sun checkboxes).'
            )

        # Fetch existing sessions to check for duplicates
        existing_dates = set(
            self.env['club.session'].search([
                ('class_id', '=', cls.id),
                ('date', 'in', session_dates),
                ('state', '!=', 'cancelled'),
            ]).mapped('date')
        )

        sessions_to_create = []
        skipped = 0
        for d in session_dates:
            if d in existing_dates:
                if self.skip_existing:
                    skipped += 1
                    continue
                else:
                    raise UserError(
                        f'A session already exists for class "{cls.name}" on {d}. '
                        f'Enable "Skip Existing Dates" to skip them automatically.'
                    )
            sessions_to_create.append({
                'class_id': cls.id,
                'trainer_id': cls.trainer_id.id,
                'date': d,
                'time_start': cls.time_start,
                'time_end': cls.time_end,
                'state': 'draft',
            })

        if not sessions_to_create:
            raise UserError(
                f'All {len(session_dates)} date(s) already have sessions. Nothing to generate.'
            )

        created = self.env['club.session'].create(sessions_to_create)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sessions Generated',
                'message': (
                    f'{len(created)} session(s) created'
                    + (f', {skipped} skipped (already existed).' if skipped else '.')
                ),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'name': 'Sessions',
                    'res_model': 'club.session',
                    'view_mode': 'list,form,calendar',
                    'domain': [('class_id', '=', cls.id)],
                },
            },
        }
