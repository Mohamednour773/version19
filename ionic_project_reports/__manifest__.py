{
    "name": "IONIC Project Reports",
    "summary": "Profitability, quantity tracking, variance, mold, and material dashboards",
    "version": "19.0.1.0.0",
    "category": "Manufacturing/Reporting",
    "author": "IONIC ERP",
    "license": "LGPL-3",
    "depends": [
        "ionic_site_installation",
        "web",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/ionic_project_dashboard_views.xml",
        "report/ionic_project_reports.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ionic_project_reports/static/src/js/ionic_project_dashboard.js",
            "ionic_project_reports/static/src/xml/ionic_project_dashboard.xml",
            "ionic_project_reports/static/src/scss/ionic_project_dashboard.scss",
        ],
    },
    "demo": [
        "demo/ionic_project_reports_demo.xml",
    ],
    "installable": True,
    "application": False,
}
