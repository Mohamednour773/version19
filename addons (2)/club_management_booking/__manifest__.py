# -*- coding: utf-8 -*-
{
    'name': 'Club Management — Booking Engine',
    'version': '19.0.1.0.0',
    'category': 'Services/Sports',
    'summary': 'Session booking engine for Club Management memberships',
    'description': """
        Adds a session booking layer on top of Club Management:
        - Book individual sessions for a membership
        - Auto-book from the weekly schedule (respects sessions_per_week cap)
        - Waitlist support when sessions are full
        - Un-book sessions (promotes next waitlist entry automatically)
        - Reception Booking Wizard with three modes: auto / single / custom
        - "Book Sessions" stat button on the membership form

        Standalone module — does NOT depend on any POS module.
        Requires: club_management_system_final
    """,
    'depends': ['club_management_system_final'],
    'data': [
        'security/ir.model.access.csv',
        'wizards/booking_wizard_views.xml',
        'views/club_membership_views.xml',
        'views/club_menus.xml',
    ],
    'license': 'LGPL-3',
    'application': False,
    'auto_install': False,
    'installable': True,
}
