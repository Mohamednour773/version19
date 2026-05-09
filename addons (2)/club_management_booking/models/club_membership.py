# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ClubMembershipBooking(models.Model):
    _inherit = 'club.membership'

    # Convenience count for the stat button (total enrolled sessions)
    booked_session_count = fields.Integer(
        compute='_compute_booked_session_count',
        string='Booked Sessions',
    )

    @api.depends('session_ids')
    def _compute_booked_session_count(self):
        for mem in self:
            mem.booked_session_count = len(mem.session_ids)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def book_session(self, session_id, force_waitlist=False):
        """
        Attempt to enroll this membership in the given session.

        Args:
            session_id (int): ID of the club.session to book.
            force_waitlist (bool): If True, create a waitlist entry when
                                   the session is full instead of refusing.

        Returns:
            dict with keys:
                status  – 'booked' | 'waitlisted' | 'full' | 'error'
                message – human-readable Arabic/English description
        """
        self.ensure_one()
        session = self.env['club.session'].browse(session_id)
        if not session.exists():
            return {'status': 'error', 'message': _('Session not found.')}

        if self.id in session.membership_ids.ids:
            return {
                'status': 'booked',
                'message': _('Already enrolled in this session.'),
            }

        if session.is_full:
            if not force_waitlist:
                return {
                    'status': 'full',
                    'message': _(
                        'Session is full. Use force_waitlist=True to join the waitlist.'
                    ),
                }
            # Join waitlist
            existing_waitlist = self.env['club.session.waitlist'].search([
                ('session_id', '=', session_id),
                ('membership_id', '=', self.id),
            ], limit=1)
            if existing_waitlist:
                return {
                    'status': 'waitlisted',
                    'message': _('Already on the waitlist for this session.'),
                }
            self.env['club.session.waitlist'].create({
                'session_id': session_id,
                'membership_id': self.id,
            })
            _logger.info(
                'book_session: membership %s added to waitlist for session %s',
                self.id, session_id,
            )
            return {
                'status': 'waitlisted',
                'message': _('Session is full. Added to waitlist.'),
            }

        # Session has capacity — enroll
        try:
            session.action_enroll_membership(self.id)
        except UserError as e:
            _logger.warning(
                'book_session: action_enroll_membership raised UserError for '
                'membership %s / session %s: %s', self.id, session_id, e,
            )
            return {'status': 'error', 'message': str(e)}

        _logger.info(
            'book_session: membership %s booked into session %s',
            self.id, session_id,
        )
        return {
            'status': 'booked',
            'message': _('Successfully booked into session.'),
        }

    def unbook_session(self, session_id):
        """
        Remove this membership from the given session and promote the
        first waitlist entry (if any).

        Args:
            session_id (int): ID of the club.session to unbook from.

        Returns:
            dict with keys:
                status  – 'unbooked' | 'not_enrolled' | 'error'
                message – human-readable description
        """
        self.ensure_one()
        session = self.env['club.session'].browse(session_id)
        if not session.exists():
            return {'status': 'error', 'message': _('Session not found.')}

        if self.id not in session.membership_ids.ids:
            return {
                'status': 'not_enrolled',
                'message': _('Membership is not enrolled in this session.'),
            }

        session.write({'membership_ids': [(3, self.id)]})
        _logger.info(
            'unbook_session: membership %s removed from session %s',
            self.id, session_id,
        )

        # Promote first waitlist entry (method lives on club.session)
        try:
            session._process_waitlist()
        except Exception as e:
            _logger.warning(
                'unbook_session: _process_waitlist failed for session %s: %s',
                session_id, e,
            )

        return {
            'status': 'unbooked',
            'message': _('Removed from session. Waitlist updated.'),
        }

    def auto_book_schedule(self):
        """
        Automatically book sessions from this membership's branch weekly
        schedule, respecting the sessions_per_week cap.

        Logic:
        - Find all upcoming, non-full sessions for this membership's branch
          that match the membership's specialization (if set).
        - Group by ISO (year, week).
        - Pre-load the weeks already covered by existing enrolled sessions
          (self.session_ids) so we never double-count.
        - For each future week, book up to (sessions_per_week - already_booked)
          additional sessions.

        Returns:
            dict:
                booked      – list of session dicts that were newly booked
                waitlisted  – list of session dicts added to waitlist
                skipped     – list of session dicts skipped (full / cap reached)
                errors      – list of error message strings
        """
        self.ensure_one()
        from datetime import date

        sessions_per_week = self.sessions_per_week or 0
        if sessions_per_week <= 0:
            return {
                'booked': [], 'waitlisted': [], 'skipped': [],
                'errors': [_('No sessions_per_week configured on this membership\'s package.')],
            }

        today = date.today()
        domain = [
            ('date', '>=', today),
            ('state', 'not in', ['cancelled', 'done']),
        ]
        if self.branch_id:
            domain.append(('branch_id', '=', self.branch_id.id))
        if self.package_id and self.package_id.specialization:
            domain.append(('specialization', '=', self.package_id.specialization))

        upcoming_sessions = self.env['club.session'].search(
            domain, order='date asc, id asc'
        )

        # Pre-compute weeks already covered by existing enrolled sessions
        already_enrolled_ids = set(self.session_ids.ids)
        weekly_booked = {}  # {(iso_year, iso_week): count}
        for s in self.session_ids:
            if s.date and s.date >= today:
                iso = s.date.isocalendar()
                key = (iso[0], iso[1])
                weekly_booked[key] = weekly_booked.get(key, 0) + 1

        booked = []
        waitlisted = []
        skipped = []
        errors = []

        for session in upcoming_sessions:
            if session.id in already_enrolled_ids:
                # Already enrolled — count was pre-loaded above
                continue

            if not session.date:
                continue

            iso = session.date.isocalendar()
            key = (iso[0], iso[1])
            current_count = weekly_booked.get(key, 0)

            if current_count >= sessions_per_week:
                skipped.append({
                    'id': session.id,
                    'name': session.name or '',
                    'date': str(session.date),
                    'reason': 'weekly_cap_reached',
                })
                continue

            result = self.book_session(session.id, force_waitlist=False)

            session_info = {
                'id': session.id,
                'name': session.name or '',
                'date': str(session.date),
            }

            if result['status'] == 'booked':
                weekly_booked[key] = current_count + 1
                already_enrolled_ids.add(session.id)
                booked.append(session_info)
            elif result['status'] == 'full':
                skipped.append({**session_info, 'reason': 'full'})
            elif result['status'] == 'error':
                errors.append(result['message'])
            else:
                skipped.append({**session_info, 'reason': result['status']})

        _logger.info(
            'auto_book_schedule: membership %s — booked=%d, waitlisted=%d, '
            'skipped=%d, errors=%d',
            self.id, len(booked), len(waitlisted), len(skipped), len(errors),
        )
        return {
            'booked': booked,
            'waitlisted': waitlisted,
            'skipped': skipped,
            'errors': errors,
        }

    def action_open_booking_wizard(self):
        """Open the Reception Booking Wizard pre-filled for this membership."""
        self.ensure_one()
        wizard = self.env['club.booking.wizard'].create({
            'membership_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Book Sessions'),
            'res_model': 'club.booking.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
