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

    # ── Payment reference for bank reconciliation ────────────
    payment_reference = fields.Char(
        string='Payment Reference',
        tracking=True,
        help='Bank transfer reference, receipt number, or cheque number.',
    )
    auto_renew = fields.Boolean(
        string='Auto Renew',
        tracking=True,
        help='Automatically prepare the next renewal membership near expiry.',
    )

    # ── Relations ───────────────────────────────────────────
    attendance_ids = fields.One2many('club.attendance', 'membership_id', string='Attendance')
    session_ids = fields.Many2many(
        'club.session',
        'club_session_membership_rel',
        'membership_id', 'session_id',
        string='Enrolled Sessions',
    )
    waitlist_ids = fields.One2many('club.session.waitlist', 'membership_id', string='Waitlist Entries')
    renewal_membership_id = fields.Many2one('club.membership', string='Renewal Membership', copy=False)
    renewed_from_id = fields.Many2one('club.membership', string='Renewed From', copy=False)
    schedule_session_ids = fields.Many2many(
        'club.session',
        compute='_compute_schedule_session_ids',
        string='Training Plan',
    )
    schedule_count = fields.Integer(compute='_compute_schedule_session_ids', string='Scheduled Sessions')
    waitlist_count = fields.Integer(compute='_compute_extra_counts', string='Waitlist Entries')
    freeze_count = fields.Integer(compute='_compute_extra_counts', string='Freeze Count')
    freeze_start_date = fields.Date(string='Freeze From', tracking=True)
    freeze_end_date = fields.Date(string='Freeze To', tracking=True)
    freeze_reason = fields.Char(string='Freeze Reason', tracking=True)
    freeze_days = fields.Integer(compute='_compute_freeze_stats', string='Freeze Days', store=True)
    freeze_applied = fields.Boolean(string='Freeze Applied', default=False, copy=False)
    is_currently_frozen = fields.Boolean(compute='_compute_freeze_stats', string='Currently Frozen')

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

    @api.depends('session_ids', 'session_ids.date', 'session_ids.state')
    def _compute_sessions_this_week(self):
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        for mem in self:
            real_id = mem._origin.id
            if not real_id:
                mem.sessions_this_week = 0
                continue
            mem.sessions_this_week = self.env['club.session'].search_count([
                ('membership_ids', 'in', [real_id]),
                ('date', '>=', week_start),
                ('date', '<=', week_end),
                ('state', 'not in', ('cancelled',)),
            ])

    @api.depends('session_ids', 'session_ids.date', 'session_ids.time_start', 'session_ids.state')
    def _compute_schedule_session_ids(self):
        today = fields.Date.today()
        for mem in self:
            sessions = mem.session_ids.filtered(
                lambda s: s.date and s.date >= today and s.state != 'cancelled'
            ).sorted(key=lambda s: (s.date, s.time_start))
            mem.schedule_session_ids = [(6, 0, sessions.ids)]
            mem.schedule_count = len(sessions)

    @api.depends('waitlist_ids', 'freeze_start_date', 'freeze_end_date')
    def _compute_extra_counts(self):
        for mem in self:
            mem.waitlist_count = len(mem.waitlist_ids.filtered(lambda w: w.state in ('waiting', 'offered')))
            mem.freeze_count = 1 if mem.freeze_start_date and mem.freeze_end_date else 0

    @api.depends('freeze_start_date', 'freeze_end_date')
    def _compute_freeze_stats(self):
        today = fields.Date.today()
        for mem in self:
            if mem.freeze_start_date and mem.freeze_end_date and mem.freeze_end_date >= mem.freeze_start_date:
                mem.freeze_days = (mem.freeze_end_date - mem.freeze_start_date).days + 1
                mem.is_currently_frozen = mem.freeze_start_date <= today <= mem.freeze_end_date
            else:
                mem.freeze_days = 0
                mem.is_currently_frozen = False

    # ════════════════════════════════════════════════════
    # STATE TRANSITIONS
    # ════════════════════════════════════════════════════

    def action_confirm(self):
        for mem in self:
            if mem.state != 'draft':
                raise UserError('Only draft memberships can be confirmed.')
            # GAP 1: Registration fee check
            if mem.package_id.requires_registration:
                has_reg = self.search_count([
                    ('partner_id', '=', mem.partner_id.id),
                    ('branch_id', '=', mem.branch_id.id),
                    ('package_id.is_registration_fee', '=', True),
                    ('state', 'in', ('confirmed', 'active')),
                ])
                if not has_reg:
                    raise UserError(
                        f'Client "{mem.partner_id.name}" must have an active registration fee '
                        f'membership for branch "{mem.branch_id.name}" before confirming '
                        f'"{mem.package_id.name}".'
                    )
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

    def action_apply_freeze(self):
        notifications = self.env['club.notification']
        for mem in self:
            if mem.state not in ('active', 'confirmed'):
                raise UserError('Only active or confirmed memberships can be frozen.')
            if not mem.freeze_start_date or not mem.freeze_end_date:
                raise UserError('Please set both freeze dates before applying freeze.')
            if mem.freeze_end_date < mem.freeze_start_date:
                raise UserError('Freeze end date must be after freeze start date.')
            mem.freeze_applied = False
            if mem.freeze_start_date <= fields.Date.today() <= mem.freeze_end_date:
                mem.state = 'suspended'
            mem.message_post(
                body='Membership freeze scheduled from %s to %s%s' % (
                    mem.freeze_start_date,
                    mem.freeze_end_date,
                    (' - %s' % mem.freeze_reason) if mem.freeze_reason else '',
                )
            )
            notifications.create_notification({
                'name': 'Membership Frozen',
                'notification_type': 'membership_frozen',
                'partner_id': mem.partner_id.id,
                'membership_id': mem.id,
                'branch_id': mem.branch_id.id,
                'body': 'Your membership has a freeze scheduled from %s to %s.' % (
                    mem.freeze_start_date, mem.freeze_end_date
                ),
            })

    def action_clear_freeze(self):
        for mem in self:
            mem.write({
                'freeze_start_date': False,
                'freeze_end_date': False,
                'freeze_reason': False,
                'freeze_applied': False,
            })
            if mem.state == 'suspended':
                mem.state = 'active'

    def action_create_renewal(self):
        action = False
        for mem in self:
            if mem.renewal_membership_id:
                action = {
                    'type': 'ir.actions.act_window',
                    'name': 'Renewal Membership',
                    'res_model': 'club.membership',
                    'res_id': mem.renewal_membership_id.id,
                    'view_mode': 'form',
                    'views': [[False, 'form']],
                }
                continue
            start_date = (mem.date_end or fields.Date.today()) + timedelta(days=1)
            renewal = self.create({
                'partner_id': mem.partner_id.id,
                'branch_id': mem.branch_id.id,
                'package_id': mem.package_id.id,
                'date_start': start_date,
                'payment_method': mem.payment_method,
                'payment_reference': mem.payment_reference,
                'auto_renew': mem.auto_renew,
                'renewed_from_id': mem.id,
                'notes': 'Renewal created from %s' % mem.name,
            })
            mem.renewal_membership_id = renewal.id
            mem.message_post(body='Renewal membership %s was created.' % renewal.name)
            self.env['club.notification'].create_notification({
                'name': 'Membership Renewal Created',
                'notification_type': 'membership_renewed',
                'partner_id': mem.partner_id.id,
                'membership_id': renewal.id,
                'branch_id': mem.branch_id.id,
                'body': 'A renewal membership has been prepared starting on %s.' % start_date,
            })
            action = {
                'type': 'ir.actions.act_window',
                'name': 'Renewal Membership',
                'res_model': 'club.membership',
                'res_id': renewal.id,
                'view_mode': 'form',
                'views': [[False, 'form']],
            }
        return action

    def action_view_schedule_plan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Training Plan',
            'res_model': 'club.session',
            'view_mode': 'calendar,list,form',
            'views': [[False, 'calendar'], [False, 'list'], [False, 'form']],
            'domain': [('id', 'in', self.schedule_session_ids.ids)],
        }

    def action_view_waitlist(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Waitlist Entries',
            'res_model': 'club.session.waitlist',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('membership_id', '=', self.id)],
            'context': {'default_membership_id': self.id},
        }

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
                'views': [[False, 'form']],
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
            'views': [[False, 'form']],
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
        notifications = self.env['club.notification']
        to_suspend = self.search([
            ('state', 'in', ('active', 'confirmed')),
            ('freeze_start_date', '<=', today),
            ('freeze_end_date', '>=', today),
        ])
        to_suspend.write({'state': 'suspended'})

        completed_freezes = self.search([
            ('freeze_applied', '=', False),
            ('freeze_end_date', '<', today),
            ('freeze_start_date', '!=', False),
        ])
        for mem in completed_freezes:
            if mem.freeze_days:
                mem.date_end = mem.date_end + timedelta(days=mem.freeze_days)
            if mem.state == 'suspended':
                mem.state = 'active'
            mem.freeze_applied = True
            mem.message_post(body='Freeze completed and membership end date extended by %s day(s).' % mem.freeze_days)

        expired = self.search([('state', '=', 'active'), ('date_end', '<', today)])
        expired.write({'state': 'expired'})
        # GAP 6: Day pass — auto-expire after 1 session used
        day_pass_done = self.search([
            ('state', 'in', ('active', 'confirmed')),
            ('package_id.package_type', '=', 'day_pass'),
            ('sessions_used', '>=', 1),
        ])
        if day_pass_done:
            day_pass_done.write({'state': 'expired'})

        renew_candidates = self.search([
            ('auto_renew', '=', True),
            ('renewal_membership_id', '=', False),
            ('state', 'in', ('active', 'confirmed')),
            ('date_end', '>=', today),
            ('date_end', '<=', today + timedelta(days=3)),
        ])
        for mem in renew_candidates:
            mem.action_create_renewal()

        expiring_soon = self.search([
            ('state', 'in', ('active', 'confirmed')),
            ('date_end', '>=', today),
            ('date_end', '<=', today + timedelta(days=3)),
        ])
        for mem in expiring_soon:
            notifications.create_notification({
                'name': 'Membership Expiry Reminder',
                'notification_type': 'membership_expiry',
                'partner_id': mem.partner_id.id,
                'membership_id': mem.id,
                'branch_id': mem.branch_id.id,
                'body': 'Your membership %s will expire on %s.' % (mem.name, mem.date_end),
            })

        overdue_invoices = self.env['club.report.overdue'].search([])
        for overdue in overdue_invoices:
            notifications.create_notification({
                'name': 'Invoice Overdue Reminder',
                'notification_type': 'invoice_overdue',
                'partner_id': overdue.partner_id.id,
                'branch_id': overdue.branch_id.id,
                'body': 'Invoice %s is overdue by %s day(s).' % (overdue.reference, overdue.days_overdue),
            })
