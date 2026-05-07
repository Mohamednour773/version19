# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Salon Booking configuration settings."""
    _inherit = 'res.config.settings'

    # ── WhatsApp ──────────────────────────────────────────────────────────────

    salon_whatsapp_enabled = fields.Boolean(
        string='Send WhatsApp Confirmations',
        config_parameter='salon_booking.whatsapp_enabled',
        help='Automatically send a WhatsApp message after each successful booking.',
    )
    salon_whatsapp_api_version = fields.Char(
        string='Graph API Version',
        config_parameter='salon_booking.whatsapp_api_version',
        default='v20.0',
    )
    salon_whatsapp_phone_number_id = fields.Char(
        string='Phone Number ID',
        config_parameter='salon_booking.whatsapp_phone_number_id',
    )
    salon_whatsapp_api_token = fields.Char(
        string='Access Token',
        config_parameter='salon_booking.whatsapp_api_token',
    )
    salon_whatsapp_language_code = fields.Char(
        string='Template Language',
        config_parameter='salon_booking.whatsapp_language_code',
        default='en_US',
    )
    salon_whatsapp_confirmation_template_name = fields.Char(
        string='Confirmation Template',
        config_parameter='salon_booking.whatsapp_confirmation_template_name',
        help='Meta WhatsApp template name used for booking confirmations.',
    )
    salon_whatsapp_cancellation_template_name = fields.Char(
        string='Cancellation Template',
        config_parameter='salon_booking.whatsapp_cancellation_template_name',
        help='Meta WhatsApp template name used for cancellation messages.',
    )

    # ── Slot configuration ─────────────────────────────────────────────────────

    salon_default_slot_duration = fields.Integer(
        string='Default Slot Duration (min)',
        config_parameter='salon_booking.default_slot_duration',
        default=30,
        help='Default appointment duration in minutes if not overridden per service.',
    )
    salon_advance_booking_days = fields.Integer(
        string='Advance Booking Limit (days)',
        config_parameter='salon_booking.advance_booking_days',
        default=30,
        help='How many days ahead customers can book online.',
    )

    # ── Cancellation policy ────────────────────────────────────────────────────

    salon_cancellation_policy_enabled = fields.Boolean(
        string='Enable Cancellation Policy',
        config_parameter='salon_booking.cancellation_policy_enabled',
        help='Require a reason and enforce minimum notice when cancelling.',
    )
    salon_cancellation_hours_limit = fields.Integer(
        string='Cancellation Notice (hours)',
        config_parameter='salon_booking.cancellation_hours_limit',
        default=2,
        help='Minimum hours before appointment start that cancellation is allowed.',
    )

    # ── Many2one persistence via ir.config_parameter ──────────────────────────
