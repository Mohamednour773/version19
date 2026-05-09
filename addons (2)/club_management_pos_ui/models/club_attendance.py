# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ClubAttendance(models.Model):
    _inherit = 'club.attendance'

    # ------------------------------------------------------------------
    # RPC: pos_check_in_partner
    # ------------------------------------------------------------------
    @api.model
    def pos_check_in_partner(self, partner_id, branch_id):
        """
        Create a one-click attendance check-in from POS for a partner.

        Wraps all logic in try/except so no raw exception ever reaches
        the cashier screen.

        Called from the POS frontend via:
            orm.call('club.attendance', 'pos_check_in_partner', [partner_id, branch_id])

        Returns:
            {
                'status': 'ok' | 'no_session' | 'no_membership' |
                          'already_marked' | 'error',
                'message': str,           # bilingual
                'attendance_id': int | False,
            }
        """
        try:
            return self._do_pos_check_in(partner_id, branch_id)
        except Exception:
            _logger.error(
                'pos_check_in_partner: unexpected error for partner_id=%s branch_id=%s',
                partner_id, branch_id, exc_info=True,
            )
            return {
                'status': 'error',
                'message': (
                    'حدث خطأ أثناء تسجيل الحضور. يرجى المحاولة مرة أخرى أو التواصل مع الإدارة. / '
                    'An error occurred while checking in. Please try again or contact administration.'
                ),
                'attendance_id': False,
            }

    def _do_pos_check_in(self, partner_id, branch_id):
        """Core logic — called by pos_check_in_partner inside a try/except."""

        # ── 1. Validate partner ────────────────────────────────────────
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return {
                'status': 'error',
                'message': 'Partner not found. / العميل غير موجود.',
                'attendance_id': False,
            }

        today = fields.Date.context_today(self)
        now = fields.Datetime.now()

        _logger.info(
            'pos_check_in: searching sessions for partner=%s (id=%s), branch=%s, today=%s',
            partner.name, partner_id, branch_id, today,
        )

        # ── 2. Find active memberships ─────────────────────────────────
        memberships = self.env['club.membership'].search([
            ('partner_id', '=', partner_id),
            ('state', 'in', ['confirmed', 'active']),
        ])

        if not memberships:
            _logger.info(
                'pos_check_in: no active memberships for partner=%s (id=%s)',
                partner.name, partner_id,
            )
            return {
                'status': 'no_membership',
                'message': (
                    f'{partner.name} ليس لديه عضوية نشطة. / '
                    f'{partner.name} has no active membership.'
                ),
                'attendance_id': False,
            }

        # ── 3. Find today's session where a membership is enrolled ─────
        session_domain = [
            ('date', '=', today),
            ('state', 'in', ['confirmed', 'in_progress']),
            ('membership_ids', 'in', memberships.ids),
        ]
        if branch_id:
            session_domain.append(('branch_id', '=', branch_id))

        sessions = self.env['club.session'].search(
            session_domain,
            order='datetime_start asc',
            limit=1,
        )

        _logger.info(
            'pos_check_in: found %d candidate session(s) for partner=%s today=%s branch=%s',
            len(sessions), partner.name, today, branch_id,
        )

        if not sessions:
            return {
                'status': 'no_session',
                'message': (
                    f'لا توجد حصص مجدولة اليوم لـ {partner.name}. / '
                    f'No sessions scheduled today for {partner.name}.'
                ),
                'attendance_id': False,
            }

        session = sessions  # already limited to 1

        _logger.info(
            'pos_check_in: selected session id=%s name=%s start=%s',
            session.id, session.name, session.datetime_start,
        )

        # ── 4. Identify which membership is enrolled in this session ───
        # membership_ids is the M2M of club.membership records on the session
        enrolled_membership = memberships.filtered(
            lambda m: m in session.membership_ids
        )
        if not enrolled_membership:
            # Edge case: session found but via branch/date match, not membership link.
            # Fall back to the most recent active membership.
            enrolled_membership = memberships.sorted('date_start', reverse=True)

        enrolled_membership = enrolled_membership[:1]

        # ── 5. Check for existing attendance (unique: session + membership) ──
        existing = self.search([
            ('session_id', '=', session.id),
            ('membership_id', '=', enrolled_membership.id),
        ], limit=1)

        if existing:
            _logger.info(
                'pos_check_in: existing attendance id=%s state=%s',
                existing.id, existing.state,
            )
            if existing.state in ('present', 'attended'):
                return {
                    'status': 'already_marked',
                    'message': (
                        f'تم تسجيل حضور {partner.name} بالفعل لهذه الحصة. / '
                        f'{partner.name} is already checked in for this session.'
                    ),
                    'attendance_id': existing.id,
                }
            # State is absent/excused — update to present
            existing.write({'state': 'present', 'check_in': now})
            _logger.info(
                'pos_check_in: updated attendance %s → present for partner=%s',
                existing.id, partner.name,
            )
            return {
                'status': 'ok',
                'message': (
                    f'تم تحديث حضور {partner.name} في حصة {session.name}. / '
                    f'Attendance updated to Present for {partner.name} in {session.name}.'
                ),
                'attendance_id': existing.id,
            }

        # ── 6. Create new attendance record (all required fields supplied) ──
        # NOTE: branch_id on club.attendance is a RELATED from session_id.branch_id
        # and must NOT be passed to create() — it is set automatically.
        attendance = self.create({
            'session_id': session.id,
            'membership_id': enrolled_membership.id,
            'partner_id': partner_id,
            'date': today,
            'check_in': now,
            'state': 'present',
        })

        _logger.info(
            'pos_check_in: result=ok — created attendance %s for partner=%s session=%s',
            attendance.id, partner.name, session.name,
        )

        return {
            'status': 'ok',
            'message': (
                f'تم تسجيل حضور {partner.name} في حصة {session.name}. / '
                f'Check-in recorded for {partner.name} in session {session.name}.'
            ),
            'attendance_id': attendance.id,
        }
