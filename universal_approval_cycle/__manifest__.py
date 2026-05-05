# -*- coding: utf-8 -*-
{
    'name': 'Universal Approval Cycle',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Apply multi-stage approval cycles to any Odoo model',
    'description': """
Universal Approval Cycle
========================
This module enables you to define and apply multi-stage approval workflows
to any existing model in Odoo 19.

Features:
---------
* Define approval cycles on any Odoo model
* Multi-stage approvals with configurable approvers per stage
* Smart buttons and status tracking on source records
* Full audit log with comments
* Email notifications to approvers
* Automatic trigger conditions
* Role-based access control
    """,
    'author': 'Mohamed Nour',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/approval_security.xml',
        'security/ir.model.access.csv',
        'data/approval_mail_template.xml',
        'views/approval_cycle_views.xml',
        'views/approval_stage_views.xml',
        'views/approval_request_views.xml',
        'views/approval_log_views.xml',
        'views/approval_menus.xml',
        'wizard/approval_action_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/icon.png'],
}
