# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Club client flag
    is_club_client = fields.Boolean(string='Is Club Client', default=False, index=True)

    # Child member support
    is_child_member = fields.Boolean(string='Is Child Member', default=False)
    parent_member_id = fields.Many2one(
        'res.partner',
        string='Parent / Guardian',
        domain=[('is_club_client', '=', True), ('is_child_member', '=', False)],
        ondelete='restrict',
    )
    child_member_ids = fields.One2many(
        'res.partner',
        'parent_member_id',
        string='Child Members',
    )
    child_member_count = fields.Integer(
        compute='_compute_child_member_count',
        string='Children',
    )

    # Demographics
    date_of_birth = fields.Date(string='Date of Birth')
    age = fields.Integer(
        string='Age',
        compute='_compute_age',
        store=True,
    )
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ], string='Gender')

    # Emergency contact
    emergency_contact = fields.Char(string='Emergency Contact Name')
    emergency_phone = fields.Char(string='Emergency Phone')

    # Medical
    medical_notes = fields.Text(string='Medical Notes')

    # Club memberships
    membership_ids = fields.One2many(
        'club.membership',
        'partner_id',
        string='Memberships',
    )
    membership_count = fields.Integer(
        compute='_compute_membership_count',
        string='Memberships',
    )
    active_membership_ids = fields.One2many(
        'club.membership',
        'partner_id',
        string='Active Memberships',
        domain=[('state', '=', 'active')],
    )

    # Attendance
    attendance_ids = fields.One2many(
        'club.attendance',
        'partner_id',
        string='Attendance History',
    )
    attendance_count = fields.Integer(
        compute='_compute_attendance_count',
        string='Attendance',
    )

    @api.depends('child_member_ids')
    def _compute_child_member_count(self):
        for partner in self:
            partner.child_member_count = len(partner.child_member_ids)

    @api.depends('date_of_birth')
    def _compute_age(self):
        today = fields.Date.today()
        for partner in self:
            if partner.date_of_birth:
                dob = partner.date_of_birth
                partner.age = (
                    today.year - dob.year
                    - ((today.month, today.day) < (dob.month, dob.day))
                )
            else:
                partner.age = 0

    @api.depends('membership_ids')
    def _compute_membership_count(self):
        for partner in self:
            partner.membership_count = len(partner.membership_ids)

    @api.depends('attendance_ids')
    def _compute_attendance_count(self):
        for partner in self:
            partner.attendance_count = len(partner.attendance_ids)

    @api.constrains('is_child_member', 'parent_member_id')
    def _check_child_parent(self):
        for partner in self:
            if partner.is_child_member and not partner.parent_member_id:
                raise ValidationError(
                    f'Child member "{partner.name}" must have a parent/guardian assigned.'
                )
            if partner.parent_member_id and partner.parent_member_id == partner:
                raise ValidationError('A member cannot be their own parent/guardian.')

    @api.constrains('parent_member_id')
    def _check_no_duplicate_parent(self):
        """Prevent creating duplicate parent records."""
        for partner in self:
            if partner.parent_member_id:
                # Ensure parent is not also a child member
                if partner.parent_member_id.is_child_member:
                    raise ValidationError(
                        f'"{partner.parent_member_id.name}" is a child member and cannot be a parent/guardian.'
                    )

    def action_view_memberships(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Memberships',
            'res_model': 'club.membership',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def action_view_attendance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Attendance History',
            'res_model': 'club.attendance',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('partner_id', '=', self.id)],
        }

    def action_view_children(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Child Members',
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('parent_member_id', '=', self.id)],
            'context': {
                'default_parent_member_id': self.id,
                'default_is_child_member': True,
                'default_is_club_client': True,
            },
        }
