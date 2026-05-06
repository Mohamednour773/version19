# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ClubNotification(models.Model):
    _name = 'club.notification'
    _description = 'Club Notification Log'
    _order = 'scheduled_date desc, id desc'

    name = fields.Char(string='Title', required=True)
    notification_type = fields.Selection([
        ('membership_expiry', 'Membership Expiry'),
        ('invoice_overdue', 'Invoice Overdue'),
        ('session_reminder', 'Session Reminder'),
        ('waitlist_offer', 'Waitlist Offer'),
        ('membership_frozen', 'Membership Frozen'),
        ('membership_renewed', 'Membership Renewed'),
    ], string='Type', required=True)
    channel = fields.Selection([
        ('in_app', 'In App'),
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
    ], string='Channel', default='in_app', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', copy=False)
    scheduled_date = fields.Datetime(
        string='Scheduled On',
        default=fields.Datetime.now,
        required=True,
    )
    sent_date = fields.Datetime(string='Sent On', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Client', ondelete='set null')
    membership_id = fields.Many2one('club.membership', string='Membership', ondelete='set null')
    session_id = fields.Many2one('club.session', string='Session', ondelete='set null')
    waitlist_id = fields.Many2one('club.session.waitlist', string='Waitlist Entry', ondelete='set null')
    branch_id = fields.Many2one('club.branch', string='Branch', ondelete='set null')
    body = fields.Text(string='Message')

    _sql_constraints = [
        (
            'unique_notification_signature',
            'UNIQUE(notification_type, channel, partner_id, membership_id, session_id, waitlist_id, scheduled_date)',
            'An identical notification is already scheduled for the same moment.',
        ),
    ]

    def action_mark_sent(self):
        self.write({
            'state': 'sent',
            'sent_date': fields.Datetime.now(),
        })

    @api.model
    def create_notification(self, vals):
        model = self.sudo()
        existing = model.search([
            ('notification_type', '=', vals.get('notification_type')),
            ('channel', '=', vals.get('channel', 'in_app')),
            ('partner_id', '=', vals.get('partner_id')),
            ('membership_id', '=', vals.get('membership_id')),
            ('session_id', '=', vals.get('session_id')),
            ('waitlist_id', '=', vals.get('waitlist_id')),
            ('state', '!=', 'cancelled'),
        ], limit=1)
        if existing:
            return existing
        return model.create(vals)

    @api.model
    def _cron_dispatch_in_app_notifications(self):
        due_notifications = self.sudo().search([
            ('state', '=', 'draft'),
            ('channel', '=', 'in_app'),
            ('scheduled_date', '<=', fields.Datetime.now()),
        ], limit=100)
        for notification in due_notifications:
            target = notification.membership_id or notification.session_id or notification.waitlist_id
            if target:
                target.message_post(body=notification.body or notification.name)
            notification.action_mark_sent()
