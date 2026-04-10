# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ClubFacility(models.Model):
    _name = 'club.facility'
    _description = 'Club Facility'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'branch_id, facility_type, name'

    name = fields.Char(string='Facility Name', required=True)
    branch_id = fields.Many2one(
        'club.branch',
        string='Branch',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    active = fields.Boolean(default=True)

    facility_type = fields.Selection([
        ('pool', 'Swimming Pool'),
        ('lane', 'Swimming Lane'),
        ('court', 'Court'),
        ('gym', 'Gym'),
        ('room', 'Multi-Purpose Room'),
        ('other', 'Other'),
    ], string='Type', required=True, default='pool')

    # Lane-specific
    parent_facility_id = fields.Many2one(
        'club.facility',
        string='Parent Facility (Pool)',
        domain=[('facility_type', '=', 'pool')],
        ondelete='set null',
    )
    lane_section = fields.Selection([
        ('A', 'Section A'),
        ('B', 'Section B'),
        ('full', 'Full Lane'),
    ], string='Lane Section', default='full')
    is_split = fields.Boolean(string='Split Lane', default=False)

    # Capacity
    capacity = fields.Integer(string='Capacity', default=1)
    max_trainers = fields.Integer(string='Max Trainers', default=1)

    # Pricing per hour
    price_per_hour = fields.Float(string='Price/Hour', digits=(16, 2))
    product_id = fields.Many2one(
        'product.product',
        string='Rental Product',
        domain=[('type', '=', 'service')],
    )

    # Relations
    rental_ids = fields.One2many('club.rental', 'facility_id', string='Bookings')
    class_ids = fields.One2many('club.class', 'facility_id', string='Classes')
    child_facility_ids = fields.One2many(
        'club.facility', 'parent_facility_id', string='Lanes / Sub-facilities'
    )

    notes = fields.Text(string='Notes')
    color = fields.Integer(string='Color Index', default=0)

    # Computed
    rental_count = fields.Integer(compute='_compute_counts', string='Rentals')
    class_count = fields.Integer(compute='_compute_counts', string='Classes')

    @api.depends('rental_ids', 'class_ids')
    def _compute_counts(self):
        for facility in self:
            facility.rental_count = len(facility.rental_ids)
            facility.class_count = len(facility.class_ids)

    @api.constrains('is_split', 'facility_type')
    def _check_split_lane(self):
        for rec in self:
            if rec.is_split and rec.facility_type != 'lane':
                raise ValidationError('Only lanes can be split into sections.')

    @api.constrains('parent_facility_id', 'facility_type')
    def _check_parent_facility(self):
        for rec in self:
            if rec.parent_facility_id and rec.facility_type != 'lane':
                raise ValidationError('Only lanes can have a parent pool.')

    def action_view_rentals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bookings',
            'res_model': 'club.rental',
            'view_mode': 'list,form,calendar',
            'domain': [('facility_id', '=', self.id)],
            'context': {'default_facility_id': self.id},
        }
