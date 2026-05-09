# -*- coding: utf-8 -*-
import logging
from datetime import date, timedelta

from odoo import api, models


_logger = logging.getLogger(__name__)


class ClubReportDashboard(models.TransientModel):
    _name = 'club.report.dashboard'
    _description = 'Reports Dashboard Data Provider'

    @api.model
    def get_data(self):
        """
        Return dashboard data in one RPC call.
        If one section fails, keep the rest of the dashboard usable.
        """
        today = date.today()
        month_start = today.replace(day=1)
        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
        week_start = today - timedelta(days=today.weekday())

        session_model = self.env['club.session']
        membership_model = self.env['club.membership']
        attendance_model = self.env['club.attendance']
        commission_model = self.env['club.trainer.commission']
        rental_model = self.env['club.rental']
        trainer_model = self.env['club.trainer']

        result = {
            'kpis': {
                'revenue_month': 0.0,
                'revenue_prev': 0.0,
                'rental_revenue': 0.0,
                'revenue_total': 0.0,
                'sessions_month': 0,
                'sessions_week': 0,
                'attended_month': 0,
                'attended_today': 0,
                'pending_amount': 0.0,
                'pending_count': 0,
                'paid_month': 0.0,
                'active_members': 0,
                'expiring_7': 0,
                'new_month': 0,
            },
            'charts': {
                'revenue_by_method': {
                    'Cash': 0.0,
                    'Card': 0.0,
                    'Online': 0.0,
                    'Transfer': 0.0,
                },
                'top_trainers': [],
                'daily_attendance': [],
                'utilization': {
                    'group': 0,
                    'private': 0,
                },
            },
            'recent_transactions': [],
        }

        try:
            memberships_this_month = membership_model.search([
                ('state', 'in', ['active', 'confirmed', 'expired']),
                ('date_start', '>=', month_start),
            ])
            memberships_prev_month = membership_model.search([
                ('state', 'in', ['active', 'confirmed', 'expired']),
                ('date_start', '>=', prev_month_start),
                ('date_start', '<', month_start),
            ])
            rentals_this_month = rental_model.search([
                ('state', 'in', ['confirmed', 'in_use', 'done']),
                ('date_start', '>=', month_start),
            ])
            revenue_month = round(sum(memberships_this_month.mapped('price')), 2)
            revenue_prev = round(sum(memberships_prev_month.mapped('price')), 2)
            rental_revenue = round(sum(rentals_this_month.mapped('total_price')), 2)
            result['kpis'].update({
                'revenue_month': revenue_month,
                'revenue_prev': revenue_prev,
                'rental_revenue': rental_revenue,
                'revenue_total': round(revenue_month + rental_revenue, 2),
            })
        except Exception:
            _logger.exception('Dashboard revenue block failed')

        try:
            result['kpis'].update({
                'sessions_month': session_model.search_count([
                    ('state', '=', 'done'),
                    ('date', '>=', month_start),
                ]),
                'sessions_week': session_model.search_count([
                    ('state', 'not in', ['cancelled']),
                    ('date', '>=', week_start),
                    ('date', '<=', today),
                ]),
            })
        except Exception:
            _logger.exception('Dashboard sessions block failed')

        try:
            result['kpis'].update({
                'attended_month': attendance_model.search_count([
                    ('state', '=', 'attended'),
                    ('date', '>=', month_start),
                ]),
                'attended_today': attendance_model.search_count([
                    ('state', '=', 'attended'),
                    ('date', '=', today),
                ]),
            })
        except Exception:
            _logger.exception('Dashboard attendance block failed')

        try:
            pending_commissions = commission_model.search([
                ('state', 'in', ['draft', 'confirmed']),
            ])
            paid_commissions = commission_model.search([
                ('state', '=', 'paid'),
                ('date', '>=', month_start),
            ])
            result['kpis'].update({
                'pending_amount': round(sum(pending_commissions.mapped('amount')), 2),
                'pending_count': len(pending_commissions),
                'paid_month': round(sum(paid_commissions.mapped('amount')), 2),
            })
        except Exception:
            _logger.exception('Dashboard commissions block failed')

        try:
            result['kpis'].update({
                'active_members': membership_model.search_count([('state', '=', 'active')]),
                'expiring_7': membership_model.search_count([
                    ('state', '=', 'active'),
                    ('date_end', '>=', today),
                    ('date_end', '<=', today + timedelta(days=7)),
                ]),
                'new_month': membership_model.search_count([
                    ('state', 'in', ['active', 'confirmed']),
                    ('date_start', '>=', month_start),
                ]),
            })
        except Exception:
            _logger.exception('Dashboard memberships block failed')

        try:
            method_labels = {
                'cash': 'Cash',
                'card': 'Card',
                'online': 'Online',
                'transfer': 'Transfer',
            }
            revenue_by_method = {}
            for method, label in method_labels.items():
                method_memberships = membership_model.search([
                    ('payment_method', '=', method),
                    ('state', 'in', ['active', 'confirmed', 'expired']),
                    ('date_start', '>=', month_start),
                ])
                revenue_by_method[label] = round(sum(method_memberships.mapped('price')), 2)
            result['charts']['revenue_by_method'] = revenue_by_method
        except Exception:
            _logger.exception('Dashboard payment-method chart failed')

        try:
            trainer_commissions = []
            for trainer in trainer_model.search([], limit=20):
                commissions = commission_model.search([
                    ('trainer_id', '=', trainer.id),
                    ('date', '>=', month_start),
                ])
                total = round(sum(commissions.mapped('amount')), 2)
                if total > 0:
                    trainer_commissions.append({
                        'name': trainer.name,
                        'amount': total,
                    })
            trainer_commissions.sort(key=lambda item: item['amount'], reverse=True)
            result['charts']['top_trainers'] = trainer_commissions[:5]
        except Exception:
            _logger.exception('Dashboard top-trainers chart failed')

        try:
            result['charts']['daily_attendance'] = [{
                'date': (today - timedelta(days=index)).strftime('%d/%m'),
                'count': attendance_model.search_count([
                    ('state', '=', 'attended'),
                    ('date', '=', today - timedelta(days=index)),
                ]),
            } for index in range(6, -1, -1)]
        except Exception:
            _logger.exception('Dashboard daily-attendance chart failed')

        try:
            group_sessions = session_model.search([
                ('class_type', '=', 'group'),
                ('state', '=', 'done'),
                ('date', '>=', month_start),
            ])
            private_sessions = session_model.search([
                ('class_type', '=', 'private'),
                ('state', '=', 'done'),
                ('date', '>=', month_start),
            ])
            group_caps = sum(session.max_capacity or 1 for session in group_sessions)
            group_atts = sum(session.attended_count for session in group_sessions)
            private_caps = sum(session.max_capacity or 1 for session in private_sessions)
            private_atts = sum(session.attended_count for session in private_sessions)
            result['charts']['utilization'] = {
                'group': round((group_atts / group_caps) * 100, 1) if group_caps else 0,
                'private': round((private_atts / private_caps) * 100, 1) if private_caps else 0,
            }
        except Exception:
            _logger.exception('Dashboard utilization chart failed')

        try:
            recent_memberships = membership_model.search([
                ('state', 'in', ['active', 'confirmed']),
            ], order='date_start desc', limit=8)
            result['recent_transactions'] = [{
                'id': membership.id,
                'ref': membership.name,
                'client': membership.partner_id.name if membership.partner_id else '—',
                'package': membership.package_id.name if membership.package_id else '—',
                'amount': membership.price,
                'method': membership.payment_method or '—',
                'payment_ref': membership.payment_reference or '—',
                'date': str(membership.date_start),
            } for membership in recent_memberships]
        except Exception:
            _logger.exception('Dashboard recent transactions block failed')

        return result
