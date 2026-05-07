# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta
from urllib import request as url_request
from urllib.error import HTTPError, URLError

from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AppointmentType(models.Model):
    """Extend appointment.type with salon-specific fields."""
    _inherit = 'appointment.type'

    is_salon_service = fields.Boolean(
        string='Salon Service',
        default=False,
        help='Mark this appointment type as a salon/barber service.',
    )
    salon_product_id = fields.Many2one(
        comodel_name='product.template',
        string='Linked Product',
        domain=[('salon_is_bookable', '=', True)],
        ondelete='set null',
        help='POS product that triggers this appointment type.',
    )
    salon_whatsapp_confirmation_template_name = fields.Char(
        string='WhatsApp Confirmation Template',
        help='Optional Meta WhatsApp template name for this service.',
    )
    salon_whatsapp_language_code = fields.Char(
        string='WhatsApp Language',
        help='Optional Meta WhatsApp template language, for example en_US or ar.',
    )
    salon_color = fields.Integer(
        string='Calendar Color',
        default=1,
    )
    salon_employee_ids = fields.Many2many(
        comodel_name='hr.employee',
        relation='appointment_type_salon_employee_rel',
        column1='appointment_type_id',
        column2='employee_id',
        string='Barbers / Stylists',
        help='Employees who can perform this salon service.',
    )


class CalendarEvent(models.Model):
    """
    Extend calendar.event with salon-specific fields and the shared
    atomic slot-booking method used by both the POS and Website channels.
    """
    _inherit = 'calendar.event'

    # â”€â”€ Salon-specific fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    salon_channel = fields.Selection(
        selection=[
            ('pos', 'Point of Sale'),
            ('website', 'Website'),
            ('backend', 'Back-Office'),
        ],
        string='Booking Channel',
        readonly=True,
        index=True,
    )
    salon_employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Barber / Stylist',
        index=True,
        tracking=True,
    )
    salon_pos_order_line_id = fields.Many2one(
        comodel_name='pos.order.line',
        string='POS Order Line',
        readonly=True,
        ondelete='set null',
        index=True,
    )
    salon_pos_order_line_uuid = fields.Char(
        string='POS Order Line UUID',
        readonly=True,
        copy=False,
        index=True,
        help='Temporary POS frontend UUID used until the POS order is saved.',
    )
    salon_status = fields.Selection(
        selection=[
            ('draft', 'Pending'),
            ('confirmed', 'Confirmed'),
            ('cancelled', 'Cancelled'),
            ('no_show', 'No-Show'),
        ],
        string='Salon Status',
        default='confirmed',
        tracking=True,
        index=True,
    )
    salon_cancellation_reason = fields.Text(
        string='Cancellation Reason',
        readonly=True,
    )
    salon_whatsapp_sent = fields.Boolean(
        string='WhatsApp Sent',
        default=False,
        readonly=True,
    )
    salon_duration_minutes = fields.Integer(
        string='Duration (min)',
        compute='_compute_salon_duration',
        store=True,
    )

    # â”€â”€ Computed fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @api.depends('start', 'stop')
    def _compute_salon_duration(self):
        for rec in self:
            if rec.start and rec.stop:
                delta = rec.stop - rec.start
                rec.salon_duration_minutes = int(delta.total_seconds() / 60)
            else:
                rec.salon_duration_minutes = 0

    # â”€â”€ Core atomic booking method (shared by POS + Website) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @api.model
    def salon_atomic_book_slot(
        self,
        appointment_type_id: int,
        staff_user_id: int,
        employee_id: int,
        start_dt,
        stop_dt,
        partner_id: int,
        channel: str = 'website',
        pos_order_line_id: int = None,
    ):
        """
        Atomically verify slot availability and create a calendar.event booking.
        Uses PostgreSQL advisory transaction locks to eliminate race conditions.
        """
        slot_minute_ts = int(start_dt.timestamp() // 60)
        lock_key = (
            (staff_user_id      & 0xFFFF) << 48
            | (employee_id       & 0xFFFF) << 32
            | (slot_minute_ts     & 0xFFFFFFFF)
        )
        if lock_key >= 2 ** 63:
            lock_key -= 2 ** 64

        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(%s)", [lock_key]
        )

        staff_user = self.env['res.users'].browse(staff_user_id)
        if not staff_user.exists():
            raise UserError(_("Selected staff member does not exist."))

        overlapping = self.search([
            ('partner_ids', 'in', [staff_user.partner_id.id]),
            ('start', '<', stop_dt),
            ('stop', '>', start_dt),
            ('active', '=', True),
            ('salon_status', 'not in', ['cancelled']),
        ], limit=1)

        if overlapping:
            raise UserError(_(
                "Sorry, the %(start)s slot with %(employee)s is already taken. "
                "Please choose a different time.",
                start=start_dt.strftime('%H:%M'),
                employee=staff_user.name,
            ))

        appt_type = self.env['appointment.type'].browse(appointment_type_id)
        if not appt_type.exists():
            raise UserError(_("Appointment type not found."))

        partner  = self.env['res.partner'].browse(partner_id)
        employee = self.env['hr.employee'].browse(employee_id)

        # Build attendees: customer + staff (Odoo 19 requires attendee_ids)
        all_partner_ids = list({partner_id, staff_user.partner_id.id})
        attendee_vals = [
            Command.create({'partner_id': pid, 'state': 'accepted'})
            for pid in all_partner_ids
        ]

        vals = {
            'name': _('%(service)s â€“ %(customer)s',
                       service=appt_type.name, customer=partner.name),
            'appointment_type_id': appointment_type_id,
            'appointment_booker_id': partner_id,
            'appointment_status': 'booked',
            'start': fields.Datetime.to_string(start_dt),
            'stop': fields.Datetime.to_string(stop_dt),
            'attendee_ids': attendee_vals,
            'partner_ids': [Command.link(pid) for pid in all_partner_ids],
            'user_id': staff_user_id,
            'salon_channel': channel,
            'salon_employee_id': employee.id if employee.exists() else False,
            'salon_status': 'confirmed',
            'description': _(
                'Salon booking via %(channel)s\nService: %(service)s\nBarber: %(barber)s',
                channel=channel,
                service=appt_type.name,
                barber=employee.name if employee.exists() else staff_user.name,
            ),
        }

        if pos_order_line_id:
            vals['salon_pos_order_line_id'] = pos_order_line_id
        pos_order_line_uuid = self.env.context.get('salon_pos_order_line_uuid')
        if pos_order_line_uuid:
            vals['salon_pos_order_line_uuid'] = pos_order_line_uuid

        event = self.create(vals)
        _logger.info(
            'Salon booking created: event=%s channel=%s employee=%s start=%s',
            event.id, channel, staff_user.name, start_dt,
        )

        event._salon_send_whatsapp_confirmation()
        return event

    # ── WhatsApp (Enterprise + Community dual-mode) ────────────────────────

    def _salon_has_whatsapp_module(self):
        """Return True if Odoo Enterprise WhatsApp module is installed."""
        return 'whatsapp.message' in self.env

    def _salon_send_whatsapp_confirmation(self):
        """
        Send WhatsApp booking confirmation.

        - Enterprise (whatsapp module installed): route through whatsapp.message
          so messages appear in the WhatsApp conversation thread.
        - Community (no whatsapp module): send directly via Meta Cloud API.
        """
        self.ensure_one()

        config = self.env['ir.config_parameter'].sudo()
        # get_param always returns a string, never a real bool
        if config.get_param('salon_booking.whatsapp_enabled') != 'True':
            return

        customer_partner = self._salon_get_customer_partner()
        if not customer_partner:
            _logger.warning(
                'Salon booking %s: no customer partner found, skipping WhatsApp.',
                self.id,
            )
            return

        customer_mobile = customer_partner.mobile or customer_partner.phone
        if not customer_mobile:
            _logger.warning(
                'Salon booking %s: customer has no mobile/phone, skipping WhatsApp.',
                self.id,
            )
            return

        template_name = (
            self.appointment_type_id.salon_whatsapp_confirmation_template_name
            or config.get_param('salon_booking.whatsapp_confirmation_template_name')
        )
        language = (
            self.appointment_type_id.salon_whatsapp_language_code
            or config.get_param('salon_booking.whatsapp_language_code', 'en_US')
        )
        start_local = fields.Datetime.context_timestamp(self, self.start)
        body_values = [
            customer_partner.name,
            self.appointment_type_id.name or self.name,
            self.salon_employee_id.name or self.user_id.name,
            start_local.strftime('%Y-%m-%d'),
            start_local.strftime('%H:%M'),
        ]

        sent = False
        if self._salon_has_whatsapp_module():
            sent = self._salon_send_whatsapp_via_odoo(
                customer_partner, template_name, language, body_values
            )
        else:
            sent = self._salon_send_whatsapp_direct(
                customer_mobile, template_name, language, body_values
            )

        if sent:
            self.sudo().write({'salon_whatsapp_sent': True})

    def _salon_get_customer_partner(self):
        """Return the first partner that is NOT the assigned staff member."""
        self.ensure_one()
        staff_partner_ids = {self.user_id.partner_id.id}
        if self.salon_employee_id and self.salon_employee_id.user_id:
            staff_partner_ids.add(self.salon_employee_id.user_id.partner_id.id)
        return self.partner_ids.filtered(lambda p: p.id not in staff_partner_ids)[:1]

    # -- Enterprise path ------------------------------------------------------

    def _salon_send_whatsapp_via_odoo(self, partner, template_name, language, body_values):
        """
        Send via Odoo whatsapp.message (Enterprise only).
        Falls back to Direct API if template not found.
        """
        try:
            template = self.env['whatsapp.template'].sudo().search([
                ('name', '=', template_name),
                ('model', '=', 'calendar.event'),
            ], limit=1)

            if not template:
                _logger.warning(
                    'Salon booking %s: Enterprise WhatsApp template "%s" not found, '
                    'falling back to Direct API.',
                    self.id, template_name,
                )
                return self._salon_send_whatsapp_direct(
                    partner.mobile or partner.phone,
                    template_name, language, body_values,
                )

            self.env['whatsapp.message'].sudo().create({
                'mobile_number': partner.mobile or partner.phone,
                'partner_id': partner.id,
                'wa_template_id': template.id,
                'res_id': self.id,
                'model': 'calendar.event',
            })._send()

            _logger.info(
                'Salon booking %s: WhatsApp sent via Odoo Enterprise (template=%s).',
                self.id, template_name,
            )
            return True

        except Exception as exc:
            _logger.error(
                'Salon booking %s: Odoo WhatsApp send error: %s. Falling back to Direct API.',
                self.id, exc,
            )
            return self._salon_send_whatsapp_direct(
                partner.mobile or partner.phone,
                template_name, language, body_values,
            )

    # -- Community path (Meta Cloud API direct) --------------------------------

    @staticmethod
    def _salon_normalize_phone(mobile):
        """
        Strip non-digits and ensure international format.
        Egyptian local format 01xxxxxxxxx -> 201xxxxxxxxx.
        """
        digits = ''.join(ch for ch in mobile if ch.isdigit())
        if len(digits) == 11 and digits.startswith('0'):
            digits = '20' + digits[1:]
        return digits

    def _salon_send_whatsapp_direct(self, mobile, template_name, language, body_values):
        """Send directly via Meta WhatsApp Cloud API (Community-compatible)."""
        config = self.env['ir.config_parameter'].sudo()
        phone_number_id = config.get_param('salon_booking.whatsapp_phone_number_id')
        token = config.get_param('salon_booking.whatsapp_api_token')
        api_version = config.get_param('salon_booking.whatsapp_api_version', 'v20.0')

        if not phone_number_id or not token or not template_name:
            _logger.warning(
                'Salon booking %s: WhatsApp Cloud API not fully configured.',
                self.id,
            )
            return False

        clean_mobile = self._salon_normalize_phone(mobile)
        components = []
        if body_values:
            components.append({
                'type': 'body',
                'parameters': [
                    {'type': 'text', 'text': str(v or '')} for v in body_values
                ],
            })
        payload = {
            'messaging_product': 'whatsapp',
            'to': clean_mobile,
            'type': 'template',
            'template': {
                'name': template_name,
                'language': {'code': language or 'en_US'},
                'components': components,
            },
        }
        req = url_request.Request(
            f'https://graph.facebook.com/{api_version}/{phone_number_id}/messages',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        try:
            with url_request.urlopen(req, timeout=15) as response:
                if response.status in (200, 201):
                    _logger.info(
                        'Salon booking %s: WhatsApp sent via Direct API to %s.',
                        self.id, clean_mobile,
                    )
                    return True
                _logger.error(
                    'Salon booking %s: WhatsApp Direct API HTTP %s.',
                    self.id, response.status,
                )
        except HTTPError as exc:
            _logger.error(
                'Salon booking %s: WhatsApp Direct API HTTP %s: %s',
                self.id, exc.code, exc.read().decode('utf-8', errors='replace'),
            )
        except URLError as exc:
            _logger.error('Salon booking %s: WhatsApp Direct API error: %s', self.id, exc)
        return False
    def action_salon_cancel(self):
        """Open the cancellation wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cancel Appointment'),
            'res_model': 'salon.cancel.appointment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_appointment_id': self.id},
        }

    def _salon_do_cancel(self, reason=''):
        """Mark appointment as cancelled (called by the wizard)."""
        for rec in self:
            rec.write({
                'salon_status': 'cancelled',
                'salon_cancellation_reason': reason,
                'active': False,
            })

    # â”€â”€ Availability query (used by website AJAX + POS RPC) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @api.model
    def salon_get_available_slots(
        self,
        appointment_type_id: int,
        staff_user_id: int,
        date_str: str,
        slot_duration: int = None,
    ):
        """
        Return a list of time slots for a given date with availability flags.

        In Odoo 19, appointment.slot.weekday uses '1'=Monday â€¦ '7'=Sunday
        (NOT the old 'mon','tue'â€¦ style from earlier Odoo versions).
        Python's datetime.weekday() returns Mon=0 â€¦ Sun=6.
        """
        from datetime import datetime, date as date_type
        import pytz

        appt_type = self.env['appointment.type'].browse(appointment_type_id)
        if not appt_type.exists():
            return []

        config = self.env['ir.config_parameter'].sudo()
        duration = slot_duration or int(
            config.get_param('salon_booking.default_slot_duration', 30)
        )
        advance_days = int(
            config.get_param('salon_booking.advance_booking_days', 30)
        )

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return []

        today = date_type.today()
        if target_date < today or (target_date - today).days > advance_days:
            return []

        tz = pytz.timezone(
            appt_type.appointment_tz
            or self.env.user.tz
            or 'Africa/Cairo'
        )

        # Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
        # Odoo 19 weekday field: '1'=Mon, '2'=Tue, '3'=Wed, '4'=Thu,
        #                        '5'=Fri, '6'=Sat, '7'=Sun
        dow = target_date.weekday()  # 0-6

        # Map Odoo 19 weekday string â†’ Python weekday int
        odoo_to_python_dow = {
            '1': 0,  # Monday
            '2': 1,  # Tuesday
            '3': 2,  # Wednesday
            '4': 3,  # Thursday
            '5': 4,  # Friday
            '6': 5,  # Saturday
            '7': 6,  # Sunday
        }

        slots = self.env['appointment.slot'].search([
            ('appointment_type_id', '=', appointment_type_id),
            ('slot_type', '=', 'recurring'),
        ])
        day_slots = slots.filtered(
            lambda s: odoo_to_python_dow.get(s.weekday, -1) == dow
        )

        if not day_slots:
            _logger.debug(
                'salon_get_available_slots: no recurring slots found for '
                'appointment_type=%s date=%s (dow=%s)',
                appointment_type_id, date_str, dow,
            )
            return []

        staff_user = self.env['res.users'].browse(staff_user_id)
        staff_partner_id = staff_user.partner_id.id

        # Fetch already-booked events for this staff on this date
        day_start_local = datetime.combine(target_date, datetime.min.time())
        day_end_local   = datetime.combine(target_date, datetime.max.time())
        day_start_utc = (
            tz.localize(day_start_local).astimezone(pytz.utc).replace(tzinfo=None)
        )
        day_end_utc = (
            tz.localize(day_end_local).astimezone(pytz.utc).replace(tzinfo=None)
        )

        booked_events = self.search([
            ('partner_ids', 'in', [staff_partner_id]),
            ('start', '>=', day_start_utc),
            ('start', '<',  day_end_utc),
            ('active', '=', True),
            ('salon_status', 'not in', ['cancelled']),
        ])
        booked_ranges = [(e.start, e.stop) for e in booked_events]

        result = []
        for slot in day_slots:
            s_h = int(slot.start_hour)
            s_m = int(round((slot.start_hour - s_h) * 60))
            e_h = int(slot.end_hour)
            e_m = int(round((slot.end_hour - e_h) * 60))

            slot_open  = datetime.combine(
                target_date,
                datetime.min.time().replace(hour=s_h, minute=s_m),
            )
            slot_close = datetime.combine(
                target_date,
                datetime.min.time().replace(hour=e_h, minute=e_m),
            )

            current = slot_open
            while current + timedelta(minutes=duration) <= slot_close:
                end = current + timedelta(minutes=duration)

                cur_utc = (
                    tz.localize(current).astimezone(pytz.utc).replace(tzinfo=None)
                )
                end_utc = (
                    tz.localize(end).astimezone(pytz.utc).replace(tzinfo=None)
                )

                is_booked = any(
                    b_s < end_utc and b_e > cur_utc
                    for b_s, b_e in booked_ranges
                )

                result.append({
                    'start':     current.strftime('%H:%M'),
                    'end':       end.strftime('%H:%M'),
                    'start_iso': cur_utc.isoformat(),
                    'end_iso':   end_utc.isoformat(),
                    'available': not is_booked,
                })

                current = end

        return result
