# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ------------------------------------------------------------------
    # Computed field: active memberships (for UI display)
    # ------------------------------------------------------------------
    club_active_membership_ids = fields.One2many(
        comodel_name='club.membership',
        inverse_name='partner_id',
        string='Active Memberships',
        compute='_compute_club_active_membership_ids',
    )

    @api.depends()
    def _compute_club_active_membership_ids(self):
        """Return confirmed/active memberships for this partner."""
        for partner in self:
            partner.club_active_membership_ids = self.env['club.membership'].search([
                ('partner_id', '=', partner.id),
                ('state', 'in', ['confirmed', 'active']),
            ])

    # ------------------------------------------------------------------
    # POS data loading: expose extra fields to the POS frontend
    # ------------------------------------------------------------------
    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        extra = ['is_club_client', 'category_id']
        for f in extra:
            if f not in fields_list:
                fields_list.append(f)
        return fields_list

    # ------------------------------------------------------------------
    # RPC: get_club_pos_info
    # ------------------------------------------------------------------
    @api.model
    def get_club_pos_info(self, partner_id):
        """
        Return a lightweight dict with club-relevant data for the POS
        customer info card.

        Called from the frontend via:
            orm.call('res.partner', 'get_club_pos_info', [partner_id])

        Returns:
            {
                'partner_id': int,
                'name': str,
                'is_club_client': bool,
                'memberships': [
                    {
                        'id': int,
                        'package_name': str,
                        'state': str,
                        'sessions_remaining': int,
                        'sessions_per_week': int,
                        'expiry_date': str|False,
                        'branch_name': str,
                        'specialization': str,
                    }, ...
                ],
                'alerts': [str, ...],   # human-readable warnings
            }
        """
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return {'error': 'Partner not found / العميل غير موجود'}

        memberships = self.env['club.membership'].search([
            ('partner_id', '=', partner_id),
            ('state', 'in', ['confirmed', 'active']),
        ])

        membership_data = []
        alerts = []

        for m in memberships:
            pkg = m.package_id
            remaining = m.sessions_remaining if hasattr(m, 'sessions_remaining') else 0

            # Collect alerts
            if hasattr(m, 'sessions_remaining') and m.sessions_remaining == 0:
                alerts.append(
                    f'⚠️ {m.package_id.name}: No sessions remaining / لا جلسات متبقية'
                )
            if hasattr(m, 'expiry_date') and m.expiry_date:
                import datetime
                today = fields.Date.today()
                days_left = (m.expiry_date - today).days if m.expiry_date else None
                if days_left is not None and days_left <= 7:
                    alerts.append(
                        f'⏰ {m.package_id.name}: Expires in {days_left} day(s) / '
                        f'تنتهي خلال {days_left} يوم'
                    )

            membership_data.append({
                'id': m.id,
                'package_name': pkg.name if pkg else '',
                'state': m.state,
                'sessions_remaining': remaining,
                'sessions_per_week': pkg.sessions_per_week if pkg else 0,
                'expiry_date': str(m.expiry_date) if hasattr(m, 'expiry_date') and m.expiry_date else False,
                'branch_name': m.branch_id.name if m.branch_id else '',
                'specialization': pkg.specialization if pkg else '',
            })

        # Check for registration fee
        has_reg_fee = self.env['club.membership'].search_count([
            ('partner_id', '=', partner_id),
            ('package_id.is_registration_fee', '=', True),
            ('state', 'in', ['confirmed', 'active']),
        ]) > 0
        if not has_reg_fee and partner.is_club_client:
            alerts.append('📋 No registration fee paid / لم يتم سداد رسوم التسجيل')

        return {
            'partner_id': partner.id,
            'name': partner.name,
            'is_club_client': partner.is_club_client,
            'memberships': membership_data,
            'alerts': alerts,
        }
