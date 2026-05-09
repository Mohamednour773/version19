# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ClubSessionWaitlist(models.Model):
    _name = 'club.session.waitlist'
    _description = 'Session Waitlist Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority, create_date, id'

    name = fields.Char(
        string='Reference',
        compute='_compute_name',
        store=True,
    )
    session_id = fields.Many2one(
        'club.session',
        string='Session',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    branch_id = fields.Many2one(
        related='session_id.branch_id',
        string='Branch',
        store=True,
    )
    membership_id = fields.Many2one(
        'club.membership',
        string='Membership',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    partner_id = fields.Many2one(
        related='membership_id.partner_id',
        string='Client',
        store=True,
    )
    priority = fields.Integer(string='Priority', default=10, tracking=True)
    state = fields.Selection([
        ('waiting', 'Waiting'),
        ('offered', 'Spot Offered'),
        ('joined', 'Joined'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ], string='Status', default='waiting', tracking=True, copy=False)
    offered_on = fields.Datetime(string='Offered On', readonly=True, copy=False)
    joined_on = fields.Datetime(string='Joined On', readonly=True, copy=False)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        (
            'session_membership_waitlist_unique',
            'UNIQUE(session_id, membership_id)',
            'This membership is already on the waitlist for the selected session.',
        ),
    ]

    @api.depends('session_id', 'partner_id')
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.partner_id:
                parts.append(rec.partner_id.name)
            if rec.session_id:
                parts.append(rec.session_id.name)
            rec.name = ' / '.join(parts) if parts else 'Waitlist Entry'

    @api.constrains('membership_id', 'session_id')
    def _check_membership_session(self):
        for rec in self:
            if not rec.membership_id or not rec.session_id:
                continue
            if rec.membership_id.branch_id != rec.session_id.branch_id:
                raise ValidationError('Membership branch must match the session branch.')
            if rec.membership_id in rec.session_id.membership_ids:
                raise ValidationError('This membership is already enrolled in the session.')

    def action_offer_spot(self):
        for rec in self.filtered(lambda r: r.state == 'waiting'):
            rec.write({
                'state': 'offered',
                'offered_on': fields.Datetime.now(),
            })
            rec.message_post(body='A spot became available for this session.')

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_mark_joined(self):
        for rec in self:
            if rec.state not in ('waiting', 'offered'):
                continue
            rec.session_id.action_enroll_membership(rec.membership_id.id)
            rec.write({
                'state': 'joined',
                'joined_on': fields.Datetime.now(),
            })

    def action_reset_waiting(self):
        self.write({'state': 'waiting'})
