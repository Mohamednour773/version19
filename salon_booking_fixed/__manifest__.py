# -*- coding: utf-8 -*-
{
    'name': 'Salon Booking',
    'version': '19.0.1.0.0',
    'summary': 'Unified real-time booking for barber shops and salons via POS and Website',
    'description': """
Integrates Odoo Appointments, POS, Website, and WhatsApp into a single
conflict-free booking engine for salons and barber shops.

Features
--------
* Atomic slot locking via PostgreSQL advisory locks  (no double-booking)
* POS booking popup (OWL component) linked to order lines
* Website appointment flow with employee selection and live availability
* WhatsApp Cloud API confirmation on successful booking from either channel
* Configurable settings: slot duration, advance limit, cancellation policy
    """,
    'category': 'Services/Appointments',
    'author': 'Salon Booking Contributors',
    'license': 'LGPL-3',
    'depends': [
        'appointment',
        'point_of_sale',
        'website_appointment',
        'hr',
        'resource',
        'mail',
        'website',
    ],
    'post_init_hook': 'post_init_hook',
    'data': [
        'security/salon_booking_security.xml',
        'security/ir.model.access.csv',
        'views/appointment_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/website_booking_templates.xml',
        'wizard/cancel_appointment_wizard_view.xml',
        # whatsapp_template.xml intentionally excluded:
        # Enterprise WhatsApp templates are created manually via WhatsApp > Templates.
        # Community uses Direct Meta Cloud API (no whatsapp module required).
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'salon_booking/static/src/xml/pos_booking_popup.xml',
            'salon_booking/static/src/js/pos_booking_popup.js',
            'salon_booking/static/src/scss/salon_booking.scss',
        ],
        'web.assets_backend': [
            'salon_booking/static/src/scss/salon_booking.scss',
        ],
        'web.assets_frontend': [
            'salon_booking/static/src/js/website_booking.js',
            'salon_booking/static/src/scss/salon_booking.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
