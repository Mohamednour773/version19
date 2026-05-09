# -*- coding: utf-8 -*-
{
    'name': 'Configurable Approval Workflow (APW)',
    'version': '19.0.1.0.1',
    'category': 'Technical',
    'summary': 'Sequential configurable approval workflows for any Odoo model',
    'description': """
Configurable Approval Workflow (APW)
=====================================
A flexible, production-ready approval workflow engine that can be attached
to any Odoo model without conflicting with Odoo 19's built-in approvals app.

Features:
- Sequential multi-stage approvals on any model
- User / Group / Dynamic-field approver types
- Action blocking (write, delete, custom methods) while pending
- One-click approve/refuse dashboard
- Email notifications at each stage
- Full audit trail via chatter
- Conditional stages via Odoo domains
    """,
    'author': 'Custom Development',
    'depends': [
        'base',
        'mail',
        'web',
    ],
    'data': [
        'security/apw_security.xml',
        'security/ir.model.access.csv',
        'data/apw_data.xml',
        'views/apw_config_views.xml',
        'views/apw_stage_views.xml',
        'views/apw_request_views.xml',
        'views/apw_dashboard_views.xml',
        'views/apw_menus.xml',
        'wizard/apw_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'apw_workflow/static/src/css/apw_workflow.css',
            'apw_workflow/static/src/js/apw_status_widget.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
