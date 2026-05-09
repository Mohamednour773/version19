{
    "name": "Universal Approval Engine Pro",
    "summary": "Configurable multi-level approvals for any Odoo document.",
    "version": "19.0.1.0.0",
    "category": "Productivity/Approvals",
    "author": "Mostafa / Codex",
    "license": "LGPL-3",
    "depends": ["base", "mail", "hr"],
    "data": [
        "security/approval_security.xml",
        "security/ir.model.access.csv",
        "data/approval_data.xml",
        "data/approval_cron.xml",
        "views/approval_menus.xml",
        "views/approval_workflow_views.xml",
        "views/approval_request_views.xml",
        "views/approval_admin_views.xml",
        "views/approval_dashboard_views.xml",
        "wizards/approval_decision_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "universal_approval_engine_19/static/src/scss/approval_engine.scss",
        ],
    },
    "installable": True,
    "application": True,
}
