# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import date, timedelta
import math


class ClubMembership(models.Model):
    _name = 'club.membership'
    _description = 'Client Membership'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'
    _rec_name = 'display_name'

    name = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    display_name = fields.Char(compute='_compute_display_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    # ── Client ──────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner', string='Client', required=True,
        ondelete='restrict', tracking=True,
        domain=[('is_club_client', '=', True)],
    )
    is_child = fields.Boolean(related='partner_id.is_child_member', string='Is Child', store=True)
    parent_partner_id = fields.Many2one(
        related='partner_id.parent_member_id', string='Parent / Guardian', store=True,
    )

    # ── Branch & Package ────────────────────────────────────
    branch_id = fields.Many2one(
        'club.branch', string='Branch', required=True,
        tracking=True, ondelete='restrict',
    )
    package_id = fields.Many2one(
        'club.package', string='Package', required=True,
        ondelete='restrict', tracking=True,
        domain="[('branch_id', '=', branch_id), ('active', '=', True)]",
    )

    # ── Dates ───────────────────────────────────────────────
    date_start = fields.Date(string='Start Date', required=True, tracking=True)
    date_end = fields.Date(
        string='End Date', compute='_compute_date_end',
        store=True, readonly=False, tracking=True,
    )

    # ── Session tracking ────────────────────────────────────
    total_sessions = fields.Integer(related='package_id.total_sessions', string='Total Sessions', store=True)
    sessions_per_week = fields.Integer(related='package_id.sessions_per_week', string='Sessions/Week', store=True)
    sessions_used = fields.Integer(compute='_compute_session_stats', string='Sessions Used', store=True)
    sessions_remaining = fields.Integer(compute='_compute_session_stats', string='Sessions Remaining', store=True)
    sessions_this_week = fields.Integer(compute='_compute_sessions_this_week', string='Sessions This Week')
    sessions_enrolled_total = fields.Integer(
        compute='_compute_session_stats', string='Total Enrolled', store=True,
        help='Sessions already booked (not necessarily attended yet).',
    )
    progress_pct = fields.Float(compute='_compute_session_stats', string='Progress %', digits=(5, 1))

    # ── Financial ───────────────────────────────────────────
    price = fields.Float(related='package_id.price', string='Package Price', store=True, digits=(16, 2))
    invoice_id = fields.Many2one('account.move', string='Invoice', copy=False)
    payment_state = fields.Selection(related='invoice_id.payment_state', string='Payment Status', store=True)

    # ── Payment method (tracked on membership itself) ────────
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('online', 'Online'),
        ('transfer', 'Bank Transfer'),
    ], string='Payment Method', tracking=True)

    # ── Relations ───────────────────────────────────────────
    attendance_ids = fields.One2many('club.attendance', 'membership_id', string='Attendance')
    session_ids = fields.Many2many(
        'club.session',
        'club_session_membership_rel',
        'membership_id', 'session_id',
        string='Enrolled Sessions',
    )

    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Membership reference must be unique.'),
    ]

    # ════════════════════════════════════════════════════
    # COMPUTE
    # ════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('club.membership') or 'New'
        return super().create(vals_list)

    @api.depends('partner_id', 'package_id')
    def _compute_display_name(self):
        for mem in self:
            parts = []
            if mem.partner_id:
                parts.append(mem.partner_id.name)
            if mem.package_id:
                parts.append(mem.package_id.name)
            mem.display_name = ' / '.join(parts) if parts else mem.name

    @api.depends('date_start', 'package_id.duration_weeks')
    def _compute_date_end(self):
        for mem in self:
            if mem.date_start and mem.package_id.duration_weeks:
                mem.date_end = mem.date_start + timedelta(weeks=mem.package_id.duration_weeks)
            elif mem.date_start:
                mem.date_end = mem.date_start + timedelta(weeks=4)

    @api.depends('attendance_ids', 'attendance_ids.state', 'total_sessions', 'session_ids')
    def _compute_session_stats(self):
        for mem in self:
            attended = len(mem.attendance_ids.filtered(lambda a: a.state == 'attended'))
            enrolled = len(mem.session_ids)
            mem.sessions_used = attended
            mem.sessions_enrolled_total = enrolled
            mem.sessions_remaining = max(0, (mem.total_sessions or 0) - attended)
            if mem.total_sessions:
                mem.progress_pct = (attended / mem.total_sessions) * 100
            else:
                mem.progress_pct = 0.0

    def _compute_sessions_this_week(self):
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        for mem in self:
            if not isinstance(mem.id, int):
                mem.sessions_this_week = 0
                continue
            mem.sessions_this_week = self.env['club.session'].search_count([
                ('membership_ids', 'in', [mem.id]),
                ('date', '>=', week_start),
                ('date', '<=', week_end),
                ('state', 'not in', ('cancelled',)),
            ])

    # ════════════════════════════════════════════════════
    # STATE TRANSITIONS
    # ════════════════════════════════════════════════════

    def action_confirm(self):
        for mem in self:
            if mem.state != 'draft':
                raise UserError('Only draft memberships can be confirmed.')
            mem.state = 'confirmed'

    def action_activate(self):
        for mem in self:
            if mem.state not in ('draft', 'confirmed'):
                raise UserError('Cannot activate this membership.')
            mem.state = 'active'

    def action_suspend(self):
        self.write({'state': 'suspended'})

    def action_expire(self):
        self.write({'state': 'expired'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    # ════════════════════════════════════════════════════
    # INVOICE
    # ════════════════════════════════════════════════════

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
        if not self.package_id.product_id:
            raise UserError('Package must have a product defined.')

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.package_id.product_id.id,
                'name': self.package_id.name,
                'quantity': 1,
                'price_unit': self.price,
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

    # ════════════════════════════════════════════════════
    # VALIDATION HELPERS (called from session enrollment)
    # ════════════════════════════════════════════════════

    def check_weekly_limit(self):
        self.ensure_one()
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        enrolled_this_week = self.env['club.session'].search_count([
            ('membership_ids', 'in', [self.id]),
            ('date', '>=', week_start),
            ('date', '<=', week_end),
            ('state', 'not in', ('cancelled',)),
        ])
        if enrolled_this_week >= self.sessions_per_week:
            raise ValidationError(
                f'Client {self.partner_id.name} has already reached the weekly '
                f'limit ({self.sessions_per_week} sessions/week) for "{self.name}".'
            )

    def check_total_sessions_limit(self):
        self.ensure_one()
        if self.sessions_remaining <= 0:
            raise ValidationError(
                f'Client {self.partner_id.name} has used all sessions in "{self.name}".'
            )

    # ════════════════════════════════════════════════════
    # SCHEDULED ACTION
    # ════════════════════════════════════════════════════

    @api.model
    def _cron_check_expired_memberships(self):
        today = fields.Date.today()
        expired = self.search([('state', '=', 'active'), ('date_end', '<', today)])
        expired.write({'state': 'expired'})
