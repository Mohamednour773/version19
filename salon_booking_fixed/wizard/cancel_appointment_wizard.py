# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SalonCancelAppointmentWizard(models.TransientModel):
    """Wizard for cancelling a salon appointment with a mandatory reason."""
    _name = 'salon.cancel.appointment.wizard'
    _description = 'Cancel Salon Appointment'

    appointment_id = fields.Many2one(
        comodel_name='calendar.event',
        string='Appointment',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    appointment_name = fields.Char(
        string='Service',
        related='appointment_id.name',
        readonly=True,
    )
    appointment_start = fields.Datetime(
        string='Scheduled At',
        related='appointment_id.start',
        readonly=True,
    )
    employee_name = fields.Char(
        string='Barber / Stylist',
        related='appointment_id.salon_employee_id.name',
        readonly=True,
    )
    cancellation_reason = fields.Text(
        string='Cancellation Reason',
        required=True,
        help='Please provide a reason for cancelling this appointment.',
    )
    notify_customer = fields.Boolean(
        string='Notify Customer via WhatsApp',
        default=True,
        help='Send a WhatsApp cancellation notice to the customer (if WhatsApp is enabled).',
    )
    within_policy = fields.Boolean(
        string='Within Cancellation Window',
        compute='_compute_within_policy',
        store=False,
    )

    @api.depends('appointment_id', 'appointment_id.start')
    def _compute_within_policy(self):
        config = self.env['ir.config_parameter'].sudo()
        hours_limit = int(
            config.get_param('salon_booking.cancellation_hours_limit', 2)
        )
        policy_enabled = config.get_param(
            'salon_booking.cancellation_policy_enabled', False
        )
        for rec in self:
            if not policy_enabled or not rec.appointment_id or not rec.appointment_id.start:
                rec.within_policy = True
                continue
            remaining = rec.appointment_id.start - datetime.now()
            rec.within_policy = remaining >= timedelta(hours=hours_limit)

    def action_confirm_cancel(self):
        """Execute the cancellation after wizard confirmation."""
        self.ensure_one()

        config = self.env['ir.config_parameter'].sudo()
        policy_enabled = config.get_param(
            'salon_booking.cancellation_policy_enabled', False
        )

        if policy_enabled and not self.within_policy:
            hours = config.get_param('salon_booking.cancellation_hours_limit', 2)
            raise UserError(_(
                'This appointment cannot be cancelled because it starts in less than '
                '%(hours)s hour(s). Please contact the salon directly.',
                hours=hours,
            ))

        if not (self.cancellation_reason or '').strip():
            raise UserError(_('A cancellation reason is required.'))

        self.appointment_id._salon_do_cancel(reason=self.cancellation_reason)

        if self.notify_customer:
            self._send_cancellation_notification()

        return {'type': 'ir.actions.act_window_close'}

    def _send_cancellation_notification(self):
        """Send a best-effort WhatsApp cancellation notice (Enterprise + Community)."""
        try:
            appt = self.appointment_id
            config = self.env['ir.config_parameter'].sudo()
            # get_param returns string, not bool
            if config.get_param('salon_booking.whatsapp_enabled') != 'True':
                return
            customer = appt._salon_get_customer_partner()
            if not customer:
                return
            customer_mobile = customer.mobile or customer.phone
            if not customer_mobile:
                return
            template_name = config.get_param(
                'salon_booking.whatsapp_cancellation_template_name'
            )
            language = config.get_param('salon_booking.whatsapp_language_code', 'en_US')
            start_local = fields.Datetime.context_timestamp(appt, appt.start)
            body_values = [
                customer.name,
                appt.appointment_type_id.name or appt.name,
                appt.salon_employee_id.name or appt.user_id.name,
                start_local.strftime('%Y-%m-%d'),
                start_local.strftime('%H:%M'),
                self.cancellation_reason,
            ]
            # Use dual-mode: Enterprise whatsapp.message or Direct Meta API
            if appt._salon_has_whatsapp_module():
                sent = appt._salon_send_whatsapp_via_odoo(
                    customer, template_name, language, body_values
                )
            else:
                sent = appt._salon_send_whatsapp_direct(
                    customer_mobile, template_name, language, body_values
                )
            appt.sudo().message_post(
                body=_(
                    'Cancellation notice %(status)s for %(name)s (%(mobile)s). '
                    'Reason: %(reason)s',
                    status='sent' if sent else 'not sent',
                    name=customer.name,
                    mobile=customer_mobile or 'N/A',
                    reason=self.cancellation_reason,
                )
            )
        except Exception:
            pass  # Non-fatal – do not block the cancellation flow
