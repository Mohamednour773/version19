# -*- coding: utf-8 -*-
{
    'name': 'Petty Cash Management | إدارة الخزينة الصغيرة والعهد',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Finance',
    'summary': 'Complete Petty Cash & Employee Custody Management for Arabic/Gulf/Egyptian Market',
    'description': """
Petty Cash Management
=====================
Full lifecycle management for petty cash funds and employee custodies:

- Petty Cash Funds with multi-branch support
- Temporary & Permanent Employee Custodies (عهدة مؤقتة / دائمة)
- Expense Settlement with receipt tracking
- Fund replenishment and transfers
- Arabic RTL reports with amount in words
- Multi-level approval workflow
- Dashboard with charts
    """,
    'author': 'Your Company Name',
    'website': 'https://yourcompany.com',
    'license': 'OPL-1',
    'price': 299.0,
    'currency': 'USD',
    'depends': [
        'account',
        'hr',
        'mail',
        'analytic',
        'base_setup',
    ],
    'data': [
        # Security — must come first
        'security/petty_cash_security.xml',
        'security/petty_cash_record_rules.xml',
        'security/ir.model.access.csv',
        # Data — sequences first, then seed data
        'data/petty_cash_scheduled_actions.xml',
        'data/petty_cash_expense_categories.xml',
        'data/petty_cash_mail_templates.xml',
        # Views
        'views/petty_cash_expense_category_views.xml',
        'views/petty_cash_fund_views.xml',
        'views/petty_cash_custody_views.xml',
        'views/petty_cash_settlement_views.xml',
        'views/petty_cash_fund_transfer_views.xml',
        'views/petty_cash_config_views.xml',
        'views/petty_cash_dashboard_views.xml',
        'views/petty_cash_wizard_views.xml',
        # Reports
        'report/petty_cash_report_templates.xml',
        'report/petty_cash_report_custody_statement.xml',
        'report/petty_cash_report_fund_balance.xml',
        'report/petty_cash_report_outstanding.xml',
        'report/petty_cash_report_settlement_voucher.xml',
        # Menus — must come last
        'views/petty_cash_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'petty_cash_management/static/src/js/petty_cash_dashboard.js',
            'petty_cash_management/static/src/xml/petty_cash_dashboard.xml',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
