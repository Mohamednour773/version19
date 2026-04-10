# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ClubPackage(models.Model):
    _name = 'club.package'
    _description = 'Club Membership Package'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'branch_id, name'

    name = fields.Char(string='Package Name', required=True, tracking=True)
    code = fields.Char(string='Code', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True, tracking=True)
    color = fields.Integer(string='Color', default=0)

    branch_id = fields.Many2one(
        'club.branch',
        string='Branch',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Price List',
        related='branch_id.pricelist_id',
        store=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('type', '=', 'service')],
    )

    # Package type
    package_type = fields.Selection([
        ('group', 'Group Classes'),
        ('private', 'Private Sessions'),
        ('both', 'Group & Private'),
        ('rental', 'Facility Rental'),
    ], string='Package Type', required=True, default='group', tracking=True)

    # Session details
    total_sessions = fields.Integer(string='Total Sessions', required=True, default=12)
    sessions_per_week = fields.Integer(string='Sessions/Week', required=True, default=3)
    duration_weeks = fields.Integer(
        string='Duration (Weeks)',
        compute='_compute_duration_weeks',
        store=True,
    )

    # Price
    price = fields.Float(
        string='Package Price',
        required=True,
        digits=(16, 2),
        tracking=True,
    )
    price_per_session = fields.Float(
        string='Price/Session',
        compute='_compute_price_per_session',
        digits=(16, 2),
    )

    # Allowed facilities / class types
    facility_type = fields.Selection([
        ('pool', 'Swimming Pool'),
        ('lane', 'Swimming Lane'),
        ('court', 'Court'),
        ('gym', 'Gym'),
        ('room', 'Multi-Purpose Room'),
        ('any', 'Any'),
    ], string='Facility Type', default='any')

    specialization = fields.Selection([
        ('swimming', 'Swimming'),
        ('fitness', 'Fitness'),
        ('football', 'Football'),
        ('tennis', 'Tennis'),
        ('martial_arts', 'Martial Arts'),
        ('yoga', 'Yoga'),
        ('any', 'Any'),
    ], string='Sport / Specialization', default='any')

    # Age restrictions
    min_age = fields.Integer(string='Min Age', default=0)
    max_age = fields.Integer(string='Max Age', default=100)

    # Relations
    class_ids = fields.Many2many(
        'club.class',
        'club_class_package_rel',
        'package_id',
        'class_id',
        string='Linked Classes',
    )
    membership_ids = fields.One2many('club.membership', 'package_id', string='Memberships')
    membership_count = fields.Integer(compute='_compute_membership_count', string='Memberships')

    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Package code must be unique.'),
        ('total_sessions_positive', 'CHECK(total_sessions > 0)', 'Total sessions must be positive.'),
        ('sessions_per_week_positive', 'CHECK(sessions_per_week > 0)', 'Sessions per week must be positive.'),
        ('price_positive', 'CHECK(price >= 0)', 'Price cannot be negative.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('club.package') or 'New'
        return super().create(vals_list)

    @api.depends('total_sessions', 'sessions_per_week')
    def _compute_duration_weeks(self):
        for pkg in self:
            if pkg.sessions_per_week:
                import math
                pkg.duration_weeks = math.ceil(pkg.total_sessions / pkg.sessions_per_week)
            else:
                pkg.duration_weeks = 0

    @api.depends('price', 'total_sessions')
    def _compute_price_per_session(self):
        for pkg in self:
            if pkg.total_sessions:
                pkg.price_per_session = pkg.price / pkg.total_sessions
            else:
                pkg.price_per_session = 0.0

    @api.depends('membership_ids')
    def _compute_membership_count(self):
        for pkg in self:
            pkg.membership_count = len(pkg.membership_ids)

    @api.constrains('min_age', 'max_age')
    def _check_age_range(self):
        for pkg in self:
            if pkg.min_age > pkg.max_age:
                raise ValidationError('Min age cannot be greater than max age.')

    @api.constrains('sessions_per_week', 'total_sessions')
    def _check_sessions(self):
        for pkg in self:
            if pkg.sessions_per_week > pkg.total_sessions:
                raise ValidationError('Sessions per week cannot exceed total sessions.')

    def action_view_memberships(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Memberships',
            'res_model': 'club.membership',
            'view_mode': 'list,form',
            'domain': [('package_id', '=', self.id)],
            'context': {'default_package_id': self.id},
        }
