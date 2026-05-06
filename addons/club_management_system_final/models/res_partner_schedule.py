# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartnerSchedule(models.Model):
    _inherit = 'res.partner'

    upcoming_session_ids = fields.Many2many(
        'club.session',
        compute='_compute_upcoming_session_ids',
        string='Upcoming Sessions',
    )
    upcoming_session_count = fields.Integer(
        compute='_compute_upcoming_session_ids',
        string='Upcoming Sessions Count',
    )

    @api.depends('membership_ids.session_ids', 'membership_ids.session_ids.date',
                 'membership_ids.session_ids.state', 'membership_ids.state')
    def _compute_upcoming_session_ids(self):
        today = fields.Date.today()
        for partner in self:
            active_memberships = partner.membership_ids.filtered(
                lambda m: m.state in ('active', 'confirmed')
            )
            sessions = active_memberships.mapped('session_ids').filtered(
                lambda s: s.date and s.date >= today and s.state != 'cancelled'
            ).sorted(key=lambda s: (s.date, s.time_start))
            partner.upcoming_session_ids = [(6, 0, sessions.ids)]
            partner.upcoming_session_count = len(sessions)

    def action_view_schedule_plan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Training Plan',
            'res_model': 'club.session',
            'view_mode': 'calendar,list,form',
            'views': [[False, 'calendar'], [False, 'list'], [False, 'form']],
            'domain': [('id', 'in', self.upcoming_session_ids.ids)],
        }
