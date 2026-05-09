# -*- coding: utf-8 -*-
{
    'name': 'Club Management — POS Connector',
    'version': '19.0.2.1.0',
    'category': 'Services/Sports',
    'summary': 'Phase 2: auto-confirm, walk-in support, branch filtering, eligibility warnings, accurate payment mapping.',
    'depends': [
        'club_management_system_final',
        'point_of_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/walkin_data.xml',
        'views/club_package_views.xml',
        'views/pos_config_views.xml',
        'views/pos_order_views.xml',
    ],
    'license': 'LGPL-3',
    'application': False,
    'auto_install': False,
}
