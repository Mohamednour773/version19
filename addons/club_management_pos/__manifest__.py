# -*- coding: utf-8 -*-
{
    'name': 'Club Management — POS Connector',
    'version': '19.0.1.0.0',
    'category': 'Services/Sports',
    'summary': 'Phase 1 bridge: sell club packages from Point of Sale and auto-create draft memberships.',
    'depends': [
        'club_management_system_final',
        'point_of_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/club_package_views.xml',
        'views/pos_config_views.xml',
        'views/pos_order_views.xml',
    ],
    'license': 'LGPL-3',
    'application': False,
    'auto_install': False,
}
