# -*- coding: utf-8 -*-
{
    'name': 'Configurable Approval Workflow',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Sequential approval workflows for any Odoo model',
    'description': """
Configurable Approval Workflow
===============================
A flexible, production-ready approval workflow engine that can be attached
to any Odoo model. Features include:

- Drag-and-drop approval stage configuration
- Sequential multi-stage approvals
- Action blocking until approvals are complete
- Real-time dashboard with pending approval tracking
- Approval history and audit trail
- Email notifications
- Group-based or user-based approvers
- Conditional approval rules
    """,
    'author': 'Custom Development',
    'depends': [
        'base',
        'mail',
        'web',
    ],
    'data': [
        'security/approval_workflow_security.xml',
        'security/ir.model.access.csv',
        'data/approval_workflow_data.xml',
        'views/approval_workflow_config_views.xml',
        'views/approval_stage_views.xml',
        'views/approval_request_views.xml',
        'views/approval_dashboard_views.xml',
        'views/approval_workflow_menus.xml',
        'wizard/approval_action_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'approval_workflow/static/src/css/approval_workflow.css',
            'approval_workflow/static/src/js/approval_status_widget.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
