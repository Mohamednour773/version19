# -*- coding: utf-8 -*-
{
    'name': 'Club Management — POS Custom UI',
    'version': '19.0.1.0.6',
    'category': 'Services/Sports',
    'summary': 'Custom POS frontend for Club Management',
    'description': """
        Adds a tailored POS experience for sports clubs and swimming academies:
        - Smart customer search by phone or name
        - Customer info card with active memberships and alerts
        - Optional one-click attendance check-in from POS (OFF by default)
        - Custom walk-in registration form
        - Custom receipt with membership details

        Optional companion to club_management_pos (Phase 1+2).
        Uninstalling this module leaves club_management_pos fully functional.
    """,
    'depends': ['club_management_pos'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'club_management_pos_ui/static/src/components/**/*',
            'club_management_pos_ui/static/src/overrides/**/*',
        ],
    },
    'license': 'LGPL-3',
    'application': False,
    'auto_install': False,
    'installable': True,
}
