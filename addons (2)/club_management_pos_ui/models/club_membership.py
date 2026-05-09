# -*- coding: utf-8 -*-
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class ClubMembership(models.Model):
    _inherit = 'club.membership'

    # ------------------------------------------------------------------
    # RPC: get_partner_receipt_memberships
    # ------------------------------------------------------------------
    @api.model
    def get_partner_receipt_memberships(self, partner_id):
        """
        Return the active club memberships for a partner for POS receipt display.

        Called from ClubReceiptSection component after payment:
            orm.call('club.membership', 'get_partner_receipt_memberships', [partnerId])

        Uses partner_id (stable integer) instead of order name/id — avoids
        all string-matching and UUID issues.  Works on any receipt (club
        package sale, regular service sale, etc.) as long as the customer
        has active memberships in the system.

        Args:
            partner_id (int): res.partner database ID

        Returns:
            list of dict, one per confirmed/active membership.
        """
        _logger.info(
            'get_partner_receipt_memberships: called with partner_id=%s',
            partner_id,
        )

        if not partner_id:
            _logger.info('get_partner_receipt_memberships: no partner_id, returning []')
            return []

        memberships = self.search([
            ('partner_id', '=', partner_id),
            ('state', 'in', ['confirmed', 'active']),
        ])

        _logger.info(
            'get_partner_receipt_memberships: partner_id=%s → found %d membership(s): %s',
            partner_id, len(memberships), memberships.mapped('name'),
        )

        result = []
        for m in memberships:
            pkg = m.package_id
            result.append({
                'id':               m.id,
                'name':             m.name or '',
                'package_name':     pkg.name if pkg else '',
                'state':            m.state,
                'total_sessions':   pkg.total_sessions if pkg else 0,
                'sessions_per_week': pkg.sessions_per_week if pkg else 0,
                'date_start':       str(m.date_start) if m.date_start else '',
                'date_end':         str(m.date_end) if hasattr(m, 'date_end') and m.date_end else '',
                'branch_name':      m.branch_id.name if m.branch_id else '',
                'specialization':   pkg.specialization if pkg else '',
            })

        _logger.info(
            'get_partner_receipt_memberships: returning %d record(s)',
            len(result),
        )
        return result

    # ------------------------------------------------------------------
    # RPC: get_pos_receipt_memberships  (kept for reference, unused)
    # ------------------------------------------------------------------
    @api.model
    def get_pos_receipt_memberships(self, pos_order_name):
        """
        Kept for backwards compatibility.  The active code path now uses
        get_partner_receipt_memberships() which is more reliable.
        """
        _logger.info(
            'get_pos_receipt_memberships: called with pos_order_name=%r (legacy)',
            pos_order_name,
        )
        if not pos_order_name:
            return []
        order = self.env['pos.order'].search(
            [('name', '=', pos_order_name)], limit=1
        )
        if order:
            partner_id = order.partner_id.id
            if partner_id:
                return self.get_partner_receipt_memberships(partner_id)
        memberships = self.search([('payment_reference', '=', pos_order_name)])
        if not memberships:
            return []
        result = []
        for m in memberships:
            pkg = m.package_id
            result.append({
                'id':               m.id,
                'name':             m.name or '',
                'package_name':     pkg.name if pkg else '',
                'state':            m.state,
                'total_sessions':   pkg.total_sessions if pkg else 0,
                'sessions_per_week': pkg.sessions_per_week if pkg else 0,
                'date_start':       str(m.date_start) if m.date_start else '',
                'date_end':         str(m.date_end) if hasattr(m, 'date_end') and m.date_end else '',
                'branch_name':      m.branch_id.name if m.branch_id else '',
                'specialization':   pkg.specialization if pkg else '',
            })
        return result
