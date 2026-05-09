# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError, ValidationError


class ClubSessionExtension(models.Model):
    _inherit = 'club.session'

    waitlist_ids = fields.One2many('club.session.waitlist', 'session_id', string='Waitlist')
    waitlist_count = fields.Integer(compute='_compute_attendance_stats', string='Waitlist', store=True)

    def _compute_attendance_stats(self):
        super()._compute_attendance_stats()
        for session in self:
            session.waitlist_count = len(
                session.waitlist_ids.filtered(lambda w: w.state in ('waiting', 'offered'))
            )

    def write(self, vals):
        membership_before = {}
        if 'membership_ids' in vals:
            for session in self:
                membership_before[session.id] = set(session.membership_ids.ids)
        result = super().write(vals)
        if 'membership_ids' in vals:
            for session in self:
                if session.max_capacity and len(session.membership_ids) > session.max_capacity:
                    raise ValidationError(
                        'Session "%s" exceeds its capacity of %s members.'
                        % (session.name, session.max_capacity)
                    )
                membership_after = set(session.membership_ids.ids)
                removed_member_ids = membership_before.get(session.id, set()) - membership_after
                if removed_member_ids or session.available_spots > 0:
                    session._process_waitlist()
        return result

    def action_enroll_membership(self, membership_id):
        self.ensure_one()
        if self.is_full:
            raise UserError(
                'Session "%s" is fully booked (capacity: %s). Add the member to the waitlist instead.'
                % (self.name, self.max_capacity)
            )
        result = super().action_enroll_membership(membership_id)
        wait_entry = self.waitlist_ids.filtered(
            lambda w: w.membership_id.id == membership_id and w.state in ('waiting', 'offered')
        )[:1]
        if wait_entry:
            wait_entry.write({
                'state': 'joined',
                'joined_on': fields.Datetime.now(),
            })
        return result

    def action_cancel(self):
        result = super().action_cancel()
        self.waitlist_ids.filtered(lambda w: w.state in ('waiting', 'offered')).write({'state': 'expired'})
        return result

    def action_view_waitlist(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Session Waitlist',
            'res_model': 'club.session.waitlist',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id},
        }

    def _process_waitlist(self):
        for session in self:
            if session.available_spots <= 0:
                continue
            waiting_entries = session.waitlist_ids.filtered(
                lambda w: w.state == 'waiting'
            ).sorted(key=lambda w: (w.priority, w.create_date or fields.Datetime.now()))
            for entry in waiting_entries[:session.available_spots]:
                entry.action_offer_spot()
                self.env['club.notification'].create_notification({
                    'name': 'Waitlist Spot Available',
                    'notification_type': 'waitlist_offer',
                    'partner_id': entry.partner_id.id,
                    'membership_id': entry.membership_id.id,
                    'session_id': session.id,
                    'waitlist_id': entry.id,
                    'branch_id': session.branch_id.id,
                    'body': 'A spot is now available in session %s.' % session.name,
                })
