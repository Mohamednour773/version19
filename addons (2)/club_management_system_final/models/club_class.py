# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


DAYS_OF_WEEK = [
    ('0', 'Monday'),
    ('1', 'Tuesday'),
    ('2', 'Wednesday'),
    ('3', 'Thursday'),
    ('4', 'Friday'),
    ('5', 'Saturday'),
    ('6', 'Sunday'),
]


class ClubClass(models.Model):
    _name = 'club.class'
    _description = 'Club Class'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'branch_id, name'

    name = fields.Char(string='Class Name', required=True, tracking=True)
    code = fields.Char(string='Code', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True, tracking=True)
    color = fields.Integer(default=0)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    # Branch & Trainer
    branch_id = fields.Many2one(
        'club.branch',
        string='Branch',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    trainer_id = fields.Many2one(
        'club.trainer',
        string='Trainer',
        required=True,
        ondelete='restrict',
        tracking=True,
        domain="[('branch_id', '=', branch_id)]",
    )

    # Class type
    class_type = fields.Selection([
        ('group', 'Group Class'),
        ('private', 'Private Session'),
    ], string='Class Type', required=True, default='group', tracking=True)

    # Schedule type
    schedule_type = fields.Selection([
        ('mandatory', 'Mandatory (Fixed)'),
        ('open', 'Open (Flexible)'),
    ], string='Schedule Type', required=True, default='mandatory', tracking=True,
        help=(
            'Mandatory: All sessions follow the fixed days/times defined here. '
            'Times cannot be changed per session.\n'
            'Open: Sessions can have different times. '
            'Days/times here are used only as defaults.'
        )
    )

    specialization = fields.Selection([
        ('swimming', 'Swimming'),
        ('fitness', 'Fitness'),
        ('football', 'Football'),
        ('tennis', 'Tennis'),
        ('martial_arts', 'Martial Arts'),
        ('yoga', 'Yoga'),
        ('other', 'Other'),
    ], string='Sport', required=True, default='swimming')

    # Facility
    facility_id = fields.Many2one(
        'club.facility',
        string='Facility',
        ondelete='set null',
        domain="[('branch_id', '=', branch_id)]",
    )

    # Capacity
    max_capacity = fields.Integer(string='Max Capacity', default=20)
    enrolled_count = fields.Integer(
        compute='_compute_enrolled_count',
        string='Enrolled',
        store=True,
    )
    available_spots = fields.Integer(
        compute='_compute_enrolled_count',
        string='Available Spots',
        store=True,
    )

    # Schedule
    time_start = fields.Float(string='Start Time', required=True, default=9.0)
    time_end = fields.Float(string='End Time', required=True, default=10.0)
    duration = fields.Float(
        string='Duration (hrs)',
        compute='_compute_duration',
        store=True,
    )

    # Recurring schedule
    is_recurring = fields.Boolean(string='Recurring', default=True)
    day_mon = fields.Boolean(string='Monday')
    day_tue = fields.Boolean(string='Tuesday')
    day_wed = fields.Boolean(string='Wednesday')
    day_thu = fields.Boolean(string='Thursday')
    day_fri = fields.Boolean(string='Friday')
    day_sat = fields.Boolean(string='Saturday')
    day_sun = fields.Boolean(string='Sunday')
    recurrence_end_date = fields.Date(string='Recurrence End Date')

    # Package link — class must be linked to a valid package
    package_ids = fields.Many2many(
        'club.package',
        'club_class_package_rel',
        'class_id',
        'package_id',
        string='Linked Packages',
    )
    has_valid_package = fields.Boolean(
        compute='_compute_has_valid_package',
        string='Has Valid Package',
        store=True,
    )

    # Sessions
    session_ids = fields.One2many('club.session', 'class_id', string='Sessions')
    session_count = fields.Integer(compute='_compute_session_count', string='Sessions')

    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Class code must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('club.class') or 'New'
        return super().create(vals_list)

    @api.depends('time_start', 'time_end')
    def _compute_duration(self):
        for cls in self:
            cls.duration = max(0, cls.time_end - cls.time_start)

    @api.depends('package_ids')
    def _compute_has_valid_package(self):
        for cls in self:
            cls.has_valid_package = bool(cls.package_ids)

    @api.depends('session_ids.membership_ids')
    def _compute_enrolled_count(self):
        for cls in self:
            # Count unique members across all sessions
            member_ids = cls.session_ids.mapped('membership_ids').ids
            unique_members = len(set(member_ids))
            cls.enrolled_count = unique_members
            cls.available_spots = max(0, cls.max_capacity - unique_members)

    @api.depends('session_ids')
    def _compute_session_count(self):
        for cls in self:
            cls.session_count = len(cls.session_ids)

    @api.constrains('time_start', 'time_end')
    def _check_time(self):
        for cls in self:
            if cls.time_end <= cls.time_start:
                raise ValidationError('End time must be after start time.')

    @api.constrains('max_capacity')
    def _check_capacity(self):
        for cls in self:
            if cls.max_capacity < 1:
                raise ValidationError('Max capacity must be at least 1.')

    def action_confirm(self):
        for cls in self:
            if not cls.package_ids:
                raise UserError(
                    f'Class "{cls.name}" must be linked to at least one package before confirming.'
                )
            cls.state = 'confirmed'

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        for cls in self:
            if cls.state == 'done':
                raise UserError(
                    f'Class "{cls.name}" is already done and cannot be reset to draft.'
                )
        self.write({'state': 'draft'})

    def action_generate_sessions(self):
        """Open wizard to generate recurring sessions."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generate Sessions',
            'res_model': 'club.generate.sessions.wizard',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_class_id': self.id,
                'default_date_start': fields.Date.today(),
                'default_date_end': self.recurrence_end_date,
            },
        }

    def action_view_sessions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sessions',
            'res_model': 'club.session',
            'view_mode': 'list,form,calendar',
            'views': [[False, 'list'], [False, 'form'], [False, 'calendar']],
            'domain': [('class_id', '=', self.id)],
            'context': {'default_class_id': self.id},
        }

    def get_weekday_list(self):
        """Return list of weekday integers (0=Monday) for this class."""
        self.ensure_one()
        days = []
        if self.day_mon: days.append(0)
        if self.day_tue: days.append(1)
        if self.day_wed: days.append(2)
        if self.day_thu: days.append(3)
        if self.day_fri: days.append(4)
        if self.day_sat: days.append(5)
        if self.day_sun: days.append(6)
        return days
