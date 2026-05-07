# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SalonWebsiteBookingController(http.Controller):
    """
    AJAX / JSON-RPC endpoints consumed by the website appointment flow
    and the POS OWL popup. All routes return JSON.
    """

    # ══════════════════════════════════════════════════════════════════════════
    #  WEBSITE  (public, auth='public')
    # ══════════════════════════════════════════════════════════════════════════

    @http.route('/salon/booking', type='http', auth='public', website=True)
    def salon_booking_page(self, **kw):
        """Render the public salon booking page."""
        return request.render('salon_booking.website_salon_booking_page', {
            'csrf_token': request.csrf_token(),
        })

    @http.route(
        '/salon/get_services',
        type='json',
        auth='public',
        methods=['POST'],
        website=True,
        csrf=True,
    )
    def get_services(self, **kw):
        products = request.env['product.template'].sudo().search([
            ('salon_is_bookable', '=', True),
            ('salon_appointment_type_id', '!=', False),
            ('sale_ok', '=', True),
        ], order='sequence, name')
        base_url = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('web.base.url')
        )
        services = []
        for product in products:
            appt_type = product.salon_appointment_type_id
            if not appt_type.is_salon_service:
                continue
            services.append({
                'id': product.id,
                'name': product.name,
                'price': product.list_price,
                'duration': product.salon_default_duration or 30,
                'appointment_type_id': appt_type.id,
                'image_url': f'{base_url}/web/image/product.template/{product.id}/image_512',
            })
        return {'services': services}

    @http.route(
        '/salon/get_employees',
        type='json',
        auth='public',
        methods=['POST'],
        website=True,
        csrf=True,
    )
    def get_employees(self, appointment_type_id=None, **kw):
        if not appointment_type_id:
            return {'error': _('appointment_type_id is required'), 'employees': []}

        appt_type = request.env['appointment.type'].sudo().browse(
            int(appointment_type_id)
        )
        if not appt_type.exists() or not appt_type.is_salon_service:
            return {'error': _('Invalid appointment type'), 'employees': []}

        employees = appt_type.salon_employee_ids
        if not employees:
            employees = request.env['hr.employee'].sudo().search([
                ('user_id', 'in', appt_type.staff_user_ids.ids),
            ])

        base_url = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('web.base.url')
        )
        result = [
            {
                'id':        emp.id,
                'user_id':   emp.user_id.id,
                'name':      emp.name,
                'job_title': emp.job_title or '',
                'image_url': f'{base_url}/web/image/hr.employee/{emp.id}/image_128',
            }
            for emp in employees
        ]
        return {'employees': result}

    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/salon/get_slots',
        type='json',
        auth='public',
        methods=['POST'],
        website=True,
        csrf=True,
    )
    def get_slots(
        self,
        appointment_type_id=None,
        employee_id=None,
        date=None,
        **kw,
    ):
        if not all([appointment_type_id, employee_id, date]):
            return {
                'error': _('appointment_type_id, employee_id and date are required'),
                'slots': [],
            }

        employee = request.env['hr.employee'].sudo().browse(int(employee_id))
        if not employee.exists() or not employee.user_id:
            return {'error': _('Invalid employee'), 'slots': []}

        try:
            slots = request.env['calendar.event'].sudo().salon_get_available_slots(
                appointment_type_id=int(appointment_type_id),
                staff_user_id=employee.user_id.id,
                date_str=str(date),
            )
        except Exception as exc:
            _logger.exception('salon_get_available_slots failed')
            return {'error': str(exc), 'slots': []}

        return {'slots': slots}

    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/salon/book',
        type='json',
        auth='public',
        methods=['POST'],
        website=True,
        csrf=True,
    )
    def book_slot(
        self,
        appointment_type_id=None,
        employee_id=None,
        start_iso=None,
        end_iso=None,
        customer_name=None,
        customer_mobile=None,
        customer_email=None,
        **kw,
    ):
        required = {
            'appointment_type_id': appointment_type_id,
            'employee_id':         employee_id,
            'start_iso':           start_iso,
            'end_iso':             end_iso,
            'customer_name':       customer_name,
            'customer_mobile':     customer_mobile,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            return {
                'success': False,
                'message': _('Missing required fields: %s') % ', '.join(missing),
            }

        env = request.env

        partner_model = env['res.partner']
        phone_field = 'mobile' if 'mobile' in partner_model._fields else 'phone'

        partner_domain = [(phone_field, '=', customer_mobile)]
        if customer_email:
            partner_domain = [
                '|',
                (phone_field, '=', customer_mobile),
                ('email',  '=', customer_email),
            ]

        partner = partner_model.sudo().search(partner_domain, limit=1)
        if not partner:
            vals = {
                'name':          customer_name,
                phone_field:     customer_mobile,
                'customer_rank': 1,
            }
            if customer_email:
                vals['email'] = customer_email
            partner = env['res.partner'].sudo().create(vals)

        employee = env['hr.employee'].sudo().browse(int(employee_id))
        if not employee.exists() or not employee.user_id:
            return {'success': False, 'message': _('Invalid employee selection.')}

        try:
            start_dt = datetime.fromisoformat(start_iso).replace(tzinfo=None)
            end_dt   = datetime.fromisoformat(end_iso).replace(tzinfo=None)
        except (ValueError, TypeError):
            return {'success': False, 'message': _('Invalid date/time format.')}

        try:
            event = env['calendar.event'].sudo().salon_atomic_book_slot(
                appointment_type_id=int(appointment_type_id),
                staff_user_id=employee.user_id.id,
                employee_id=employee.id,
                start_dt=start_dt,
                stop_dt=end_dt,
                partner_id=partner.id,
                channel='website',
            )
        except UserError as exc:
            return {'success': False, 'message': str(exc)}
        except Exception:
            _logger.exception('Salon website booking failed')
            return {'success': False, 'message': _('Booking failed. Please try again.')}

        appt_type = env['appointment.type'].sudo().browse(int(appointment_type_id))
        return {
            'success':        True,
            'appointment_id': event.id,
            'message': _(
                'Your appointment for %(service)s with %(barber)s '
                'on %(date)s at %(time)s has been confirmed!',
                service=appt_type.name,
                barber=employee.name,
                date=start_dt.strftime('%A, %d %B %Y'),
                time=start_dt.strftime('%H:%M'),
            ),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  POS  (authenticated, auth='user')
    # ══════════════════════════════════════════════════════════════════════════

    @http.route(
        '/salon/pos/get_employees',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True,
    )
    def pos_get_employees(self, product_tmpl_id=None, **kw):
        """Return bookable employees for a POS product template."""
        if not product_tmpl_id:
            return {'employees': [], 'appointment_type_id': False}

        tmpl = request.env['product.template'].browse(int(product_tmpl_id))
        if not tmpl.exists() or not tmpl.salon_is_bookable:
            return {'employees': [], 'appointment_type_id': False}

        appt_type = tmpl.salon_appointment_type_id
        employees = tmpl.salon_employee_ids
        if not employees and appt_type:
            employees = appt_type.salon_employee_ids

        result = [
            {
                'id':        emp.id,
                'user_id':   emp.user_id.id,
                'name':      emp.name,
                'job_title': emp.job_title or '',
            }
            for emp in employees
        ]
        return {
            'employees':           result,
            'appointment_type_id': appt_type.id if appt_type else False,
            'slot_duration':       tmpl.salon_default_duration or 30,
        }

    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/salon/pos/get_slots',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True,
    )
    def pos_get_slots(
        self,
        appointment_type_id=None,
        employee_id=None,
        date=None,
        slot_duration=None,
        **kw,
    ):
        """Return available slots for the POS booking popup."""
        if not all([appointment_type_id, employee_id, date]):
            return {'slots': []}

        employee = request.env['hr.employee'].browse(int(employee_id))
        if not employee.exists() or not employee.user_id:
            return {'slots': []}

        slots = request.env['calendar.event'].salon_get_available_slots(
            appointment_type_id=int(appointment_type_id),
            staff_user_id=employee.user_id.id,
            date_str=str(date),
            slot_duration=int(slot_duration) if slot_duration else None,
        )
        return {'slots': slots}

    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/salon/pos/book',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True,
    )
    def pos_book_slot(
        self,
        appointment_type_id=None,
        employee_id=None,
        start_iso=None,
        end_iso=None,
        partner_id=None,
        pos_order_line_id=None,
        **kw,
    ):
        """
        Create a salon appointment from the POS OWL popup.

        In Odoo 19, pos.order.line uses UUID-based IDs in the frontend.
        We safely ignore pos_order_line_id if it is not a valid integer.
        """
        if not all([appointment_type_id, employee_id, start_iso, end_iso]):
            return {'success': False, 'message': _('Missing required parameters.')}

        employee = request.env['hr.employee'].browse(int(employee_id))
        if not employee.exists() or not employee.user_id:
            return {'success': False, 'message': _('Invalid employee.')}

        try:
            start_dt = datetime.fromisoformat(start_iso).replace(tzinfo=None)
            end_dt   = datetime.fromisoformat(end_iso).replace(tzinfo=None)
        except (ValueError, TypeError):
            return {'success': False, 'message': _('Invalid datetime.')}

        resolved_partner_id = (
            int(partner_id) if partner_id
            else request.env.user.partner_id.id
        )

        # In Odoo 19, POS order line IDs in the frontend are UUIDs (strings).
        # Safely convert only if it looks like a plain integer.
        safe_order_line_id = None
        order_line_uuid = None
        if pos_order_line_id:
            try:
                safe_order_line_id = int(pos_order_line_id)
            except (ValueError, TypeError):
                order_line_uuid = str(pos_order_line_id)
                _logger.debug(
                    'pos_book_slot: pos_order_line_id %r is not an integer '
                    '(Odoo 19 UUID), skipping order line link.',
                    pos_order_line_id,
                )

        try:
            event = request.env['calendar.event'].with_context(
                salon_pos_order_line_uuid=order_line_uuid
            ).salon_atomic_book_slot(
                appointment_type_id=int(appointment_type_id),
                staff_user_id=employee.user_id.id,
                employee_id=employee.id,
                start_dt=start_dt,
                stop_dt=end_dt,
                partner_id=resolved_partner_id,
                channel='pos',
                pos_order_line_id=safe_order_line_id,
            )
        except UserError as exc:
            return {'success': False, 'message': str(exc)}
        except Exception:
            _logger.exception('POS salon booking failed')
            return {'success': False, 'message': _('Booking failed. Please try again.')}

        return {
            'success':        True,
            'appointment_id': event.id,
            'message':        _('Appointment booked successfully.'),
        }
