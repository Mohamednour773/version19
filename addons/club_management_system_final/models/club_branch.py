# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ClubBranch(models.Model):
    _name = 'club.branch'
    _description = 'Club Branch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Branch Name', required=True, tracking=True)
    code = fields.Char(string='Branch Code', required=True, size=10, copy=False)
    active = fields.Boolean(default=True, tracking=True)

    # Location
    street = fields.Char(string='Street')
    city = fields.Char(string='City')
    country_id = fields.Many2one('res.country', string='Country')
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')

    # Pricing
    pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Price List',
        required=True,
        tracking=True,
    )

    # Relations
    trainer_ids = fields.One2many('club.trainer', 'branch_id', string='Trainers')
    facility_ids = fields.One2many('club.facility', 'branch_id', string='Facilities')
    class_ids = fields.One2many('club.class', 'branch_id', string='Classes')
    package_ids = fields.One2many('club.package', 'branch_id', string='Packages')
    membership_ids = fields.One2many('club.membership', 'branch_id', string='Memberships')

    # Allowed users (for record rules)
    user_ids = fields.Many2many(
        'res.users',
        'club_branch_user_rel',
        'branch_id',
        'user_id',
        string='Allowed Users',
    )
    manager_id = fields.Many2one('res.users', string='Branch Manager', tracking=True)

    # Computed counters
    trainer_count = fields.Integer(compute='_compute_counts', string='Trainers')
    facility_count = fields.Integer(compute='_compute_counts', string='Facilities')
    class_count = fields.Integer(compute='_compute_counts', string='Classes')
    membership_count = fields.Integer(compute='_compute_counts', string='Memberships')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Branch code must be unique.'),
    ]

    @api.depends('trainer_ids', 'facility_ids', 'class_ids', 'membership_ids')
    def _compute_counts(self):
        for branch in self:
            branch.trainer_count = len(branch.trainer_ids)
            branch.facility_count = len(branch.facility_ids)
            branch.class_count = len(branch.class_ids)
            branch.membership_count = len(branch.membership_ids)

    def action_view_trainers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Trainers',
            'res_model': 'club.trainer',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }

    def action_view_facilities(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Facilities',
            'res_model': 'club.facility',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }

    def action_view_classes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Classes',
            'res_model': 'club.class',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }

    def action_view_memberships(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Memberships',
            'res_model': 'club.membership',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }
