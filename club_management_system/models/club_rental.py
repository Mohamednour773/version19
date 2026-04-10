# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import datetime


class ClubRental(models.Model):
    _name = 'club.rental'
    _description = 'Facility Rental Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'

    name = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        default='New',
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_use', 'In Use'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)
    color = fields.Integer(compute='_compute_color', store=True)

    # Client
    partner_id = fields.Many2one(
        'res.partner',
        string='Client',
        required=True,
        ondelete='restrict',
        tracking=True,
    )

    # Branch & Facility
    branch_id = fields.Many2one(
        'club.branch',
        string='Branch',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    facility_id = fields.Many2one(
        'club.facility',
        string='Facility',
        required=True,
        ondelete='restrict',
        tracking=True,
        domain="[('branch_id', '=', branch_id)]",
    )
    facility_type = fields.Selection(
        related='facility_id.facility_type',
        string='Facility Type',
        store=True,
    )
    lane_section = fields.Selection(
        related='facility_id.lane_section',
        string='Lane Section',
        store=True,
    )

    # No trainer for pure rentals — optional trainer
    trainer_id = fields.Many2one(
        'club.trainer',
        string='Trainer (Optional)',
        ondelete='set null',
        domain="[('branch_id', '=', branch_id)]",
    )
    has_trainer = fields.Boolean(
        string='With Trainer',
        default=False,
    )

    # Time slot
    date_start = fields.Datetime(
        string='Start',
        required=True,
        tracking=True,
    )
    date_end = fields.Datetime(
        string='End',
        required=True,
        tracking=True,
    )
    duration_hours = fields.Float(
        string='Duration (hrs)',
        compute='_compute_duration',
        store=True,
        digits=(5, 2),
    )

    # Pricing
    price_per_hour = fields.Float(
        related='facility_id.price_per_hour',
        string='Rate/Hour',
        store=True,
        digits=(16, 2),
    )
    total_price = fields.Float(
        string='Total Price',
        compute='_compute_total_price',
        store=True,
        digits=(16, 2),
    )

    # Invoice
    invoice_id = fields.Many2one('account.move', string='Invoice', copy=False)
    payment_state = fields.Selection(
        related='invoice_id.payment_state',
        string='Payment Status',
        store=True,
    )

    # Payment method
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('online', 'Online'),
        ('transfer', 'Bank Transfer'),
    ], string='Payment Method', default='cash')

    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Booking reference must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('club.rental') or 'New'
        return super().create(vals_list)

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rental in self:
            if rental.date_start and rental.date_end:
                delta = rental.date_end - rental.date_start
                rental.duration_hours = delta.total_seconds() / 3600.0
            else:
                rental.duration_hours = 0.0

    @api.depends('duration_hours', 'price_per_hour')
    def _compute_total_price(self):
        for rental in self:
            rental.total_price = rental.duration_hours * rental.price_per_hour

    @api.depends('state')
    def _compute_color(self):
        color_map = {
            'draft': 0,
            'confirmed': 4,
            'in_use': 2,
            'done': 10,
            'cancelled': 1,
        }
        for rental in self:
            rental.color = color_map.get(rental.state, 0)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rental in self:
            if rental.date_end <= rental.date_start:
                raise ValidationError('End time must be after start time.')

    @api.constrains('facility_id', 'date_start', 'date_end', 'state')
    def _check_facility_availability(self):
        for rental in self:
            if rental.state == 'cancelled':
                continue
            if not rental.facility_id or not rental.date_start or not rental.date_end:
                continue
            # Check other rentals
            overlapping_rentals = self.search([
                ('id', '!=', rental.id),
                ('facility_id', '=', rental.facility_id.id),
                ('state', 'not in', ('cancelled',)),
                ('date_start', '<', rental.date_end),
                ('date_end', '>', rental.date_start),
            ])
            if overlapping_rentals:
                raise ValidationError(
                    f'Facility "{rental.facility_id.name}" is already booked during this time slot.\n'
                    f'Conflicting booking: {overlapping_rentals[0].name}'
                )
            # Check sessions
            date_start_date = rental.date_start.date()
            date_end_date = rental.date_end.date()
            start_hour = rental.date_start.hour + rental.date_start.minute / 60.0
            end_hour = rental.date_end.hour + rental.date_end.minute / 60.0
            overlapping_sessions = self.env['club.session'].search([
                ('facility_id', '=', rental.facility_id.id),
                ('date', '>=', date_start_date),
                ('date', '<=', date_end_date),
                ('state', 'not in', ('cancelled',)),
                ('time_start', '<', end_hour),
                ('time_end', '>', start_hour),
            ])
            if overlapping_sessions:
                raise ValidationError(
                    f'Facility "{rental.facility_id.name}" has a scheduled class session during this time slot.'
                )

    def action_confirm(self):
        for rental in self:
            if rental.state != 'draft':
                raise UserError('Only draft bookings can be confirmed.')
            rental.state = 'confirmed'

    def action_start(self):
        self.write({'state': 'in_use'})

    def action_done(self):
        for rental in self:
            rental.state = 'done'

    def action_cancel(self):
        for rental in self:
            if rental.state == 'done':
                raise UserError('Cannot cancel a completed rental.')
            rental.state = 'cancelled'

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_create_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Invoice',
                'res_model': 'account.move',
                'res_id': self.invoice_id.id,
                'view_mode': 'form',
            }

        product = self.facility_id.product_id
        if not product:
            raise UserError(
                f'Please set a rental product on facility "{self.facility_id.name}" before invoicing.'
            )

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': f'Rental: {self.facility_id.name} ({self.date_start} → {self.date_end})',
                'quantity': self.duration_hours,
                'price_unit': self.price_per_hour,
            })],
        })
        self.invoice_id = invoice

        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoice',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
        }
