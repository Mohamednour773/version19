# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ClubBookingWizard(models.TransientModel):
    """
    Reception Booking Wizard

    Three booking modes
    -------------------
    auto    – Auto-book upcoming sessions respecting sessions_per_week cap.
    single  – Pick one session from a list and book (or join waitlist).
    custom  – Select multiple sessions via Many2many checkboxes and book all.
    """
    _name = 'club.booking.wizard'
    _description = 'Club Session Booking Wizard'

    # ------------------------------------------------------------------
    # Core fields
    # ------------------------------------------------------------------
    membership_id = fields.Many2one(
        'club.membership',
        string='Membership',
        required=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one(
        related='membership_id.partner_id',
        string='Member',
        readonly=True,
    )
    package_name = fields.Char(
        related='membership_id.package_id.name',
        string='Package',
        readonly=True,
    )
    sessions_remaining = fields.Integer(
        related='membership_id.sessions_remaining',
        string='Sessions Remaining',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------
    booking_mode = fields.Selection(
        selection=[
            ('auto',   'Auto — fill week from schedule'),
            ('single', 'Single — pick one session'),
            ('custom', 'Custom — select multiple sessions'),
        ],
        string='Booking Mode',
        default='auto',
        required=True,
    )

    # ------------------------------------------------------------------
    # Single mode
    # ------------------------------------------------------------------
    session_id = fields.Many2one(
        'club.session',
        string='Session',
        domain="[('state', 'not in', ['cancelled','done']), "
               "('branch_id', '=', branch_id)]",
    )
    force_waitlist = fields.Boolean(
        string='Join Waitlist if Full',
        default=False,
    )

    # ------------------------------------------------------------------
    # Custom mode
    # ------------------------------------------------------------------
    session_ids = fields.Many2many(
        'club.session',
        'club_booking_wizard_session_rel',
        'wizard_id',
        'session_id',
        string='Sessions',
        domain="[('state', 'not in', ['cancelled','done']), "
               "('branch_id', '=', branch_id)]",
    )

    # ------------------------------------------------------------------
    # Convenience / display
    # ------------------------------------------------------------------
    branch_id = fields.Many2one(
        related='membership_id.branch_id',
        string='Branch',
        readonly=True,
        store=False,
    )

    # ------------------------------------------------------------------
    # Post-booking result fields (shown after execution)
    # ------------------------------------------------------------------
    booking_done = fields.Boolean(default=False)
    result_booked = fields.Integer(string='Booked', readonly=True)
    result_waitlisted = fields.Integer(string='Waitlisted', readonly=True)
    result_skipped = fields.Integer(string='Skipped', readonly=True)
    result_summary = fields.Text(string='Summary', readonly=True)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_book(self):
        """Execute booking according to the selected mode."""
        self.ensure_one()
        membership = self.membership_id

        if self.booking_mode == 'auto':
            return self._do_auto_book(membership)
        elif self.booking_mode == 'single':
            return self._do_single_book(membership)
        elif self.booking_mode == 'custom':
            return self._do_custom_book(membership)
        else:
            raise UserError(_('Unknown booking mode: %s') % self.booking_mode)

    def _do_auto_book(self, membership):
        result = membership.auto_book_schedule()
        lines = []
        if result['booked']:
            lines.append(_('✅ Booked %d session(s):') % len(result['booked']))
            for s in result['booked']:
                lines.append('   • %s (%s)' % (s.get('name', ''), s.get('date', '')))
        if result['waitlisted']:
            lines.append(_('⏳ Waitlisted %d session(s):') % len(result['waitlisted']))
            for s in result['waitlisted']:
                lines.append('   • %s (%s)' % (s.get('name', ''), s.get('date', '')))
        if result['skipped']:
            lines.append(_('⏭ Skipped %d session(s)') % len(result['skipped']))
        if result['errors']:
            lines.append(_('⚠ Errors:'))
            lines.extend('   ' + e for e in result['errors'])
        if not lines:
            lines.append(_('No upcoming sessions found for this membership.'))

        self.write({
            'booking_done': True,
            'result_booked': len(result['booked']),
            'result_waitlisted': len(result['waitlisted']),
            'result_skipped': len(result['skipped']),
            'result_summary': '\n'.join(lines),
        })
        return self._reopen()

    def _do_single_book(self, membership):
        if not self.session_id:
            raise UserError(_('Please select a session first.'))
        result = membership.book_session(
            self.session_id.id, force_waitlist=self.force_waitlist
        )
        summary_icon = {
            'booked': '✅', 'waitlisted': '⏳',
            'full': '🚫', 'error': '⚠',
        }.get(result['status'], '?')
        self.write({
            'booking_done': True,
            'result_booked': 1 if result['status'] == 'booked' else 0,
            'result_waitlisted': 1 if result['status'] == 'waitlisted' else 0,
            'result_skipped': 1 if result['status'] in ('full',) else 0,
            'result_summary': '%s %s' % (summary_icon, result['message']),
        })
        return self._reopen()

    def _do_custom_book(self, membership):
        if not self.session_ids:
            raise UserError(_('Please select at least one session.'))
        booked_count = 0
        waitlisted_count = 0
        skipped_count = 0
        lines = []
        for session in self.session_ids:
            result = membership.book_session(
                session.id, force_waitlist=self.force_waitlist
            )
            icon = {
                'booked': '✅', 'waitlisted': '⏳',
                'full': '🚫', 'error': '⚠', 'not_enrolled': 'ℹ',
            }.get(result['status'], '?')
            lines.append('%s %s — %s' % (icon, session.name or session.id, result['message']))
            if result['status'] == 'booked':
                booked_count += 1
            elif result['status'] == 'waitlisted':
                waitlisted_count += 1
            else:
                skipped_count += 1

        self.write({
            'booking_done': True,
            'result_booked': booked_count,
            'result_waitlisted': waitlisted_count,
            'result_skipped': skipped_count,
            'result_summary': '\n'.join(lines),
        })
        return self._reopen()

    def _reopen(self):
        """Return the same wizard window so the user sees the result."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Booking Result'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_close(self):
        """Close the wizard and refresh the parent form."""
        return {'type': 'ir.actions.act_window_close'}
