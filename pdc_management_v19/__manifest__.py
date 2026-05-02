{
    'name': 'Post-Dated Checks Management',
    'version': '19.0.2.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Complete PDC management for received and issued checks (Odoo 19)',
    'description': """
Post-Dated Checks Management
=============================
Comprehensive check management module designed for MENA region:

* Received and issued checks lifecycle management
* Check books with sequence tracking
* Full accounting integration
* Bounced checks handling with bank charges
* Guarantee checks tracking (off-balance sheet)
* Multi-bank check printing with configurable layouts
* Comprehensive reporting suite (PDF + Excel)
* Automated due-date notifications
* Multi-company and multi-currency support
* Arabic + English UI
* Hijri date support (Saudi market)
    """,
    'author': 'Mostafa',
    'website': '',
    'license': 'OPL-1',
    'price': 49.90,
    'currency': 'USD',
    'depends': [
        'base',
        'mail',
        'account',
    ],
    'external_dependencies': {
        'python': ['num2words'],
    },
    'data': [
        # ── Security (must load first) ────────────────────────────────────
        'security/pdc_security.xml',
        'security/ir.model.access.csv',

        # ── Views ─────────────────────────────────────────────────────────
        'views/pdc_bounce_reason_views.xml',
        'views/pdc_bank_views.xml',
        'views/pdc_bank_layout_views.xml',
        'views/pdc_check_book_views.xml',
        'views/pdc_check_operation_views.xml',
        'views/pdc_check_views.xml',
        'views/account_journal_views.xml',
        'views/account_payment_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',

        # ── Phase 4: Default bank layouts ─────────────────────────────────
        'data/pdc_default_layouts_data.xml',

        # ── Phase 5: Data ─────────────────────────────────────────────────
        'data/ir_sequence_data.xml',
        'data/pdc_bounce_reasons_data.xml',
        'data/mail_template_data.xml',
        'data/pdc_cron_data.xml',

        # ── Phase 5: Wizards ──────────────────────────────────────────────
        'wizards/pdc_register_wizard_views.xml',
        'wizards/pdc_deposit_wizard_views.xml',
        'wizards/pdc_clear_wizard_views.xml',
        'wizards/pdc_bounce_wizard_views.xml',
        'wizards/pdc_cancel_wizard_views.xml',
        'wizards/pdc_print_check_wizard_views.xml',

        # ── Phase 4: Reports ──────────────────────────────────────────────
        'reports/report_pdc_check_receipt.xml',
        'reports/report_pdc_check_delivery.xml',
        'reports/report_pdc_check.xml',
        'reports/report_pdc_aging.xml',
        'reports/report_pdc_partner_statement.xml',
        'reports/report_pdc_under_collection.xml',
        'reports/report_pdc_due_soon.xml',
        'reports/report_pdc_bounced.xml',

        # ── Menus — always last ───────────────────────────────────────────
        'views/pdc_menus.xml',
    ],
    'demo': [
        'demo/pdc_demo_partners.xml',
        'demo/pdc_demo_check_books.xml',
        'demo/pdc_demo_journal_setup.xml',
        'demo/pdc_demo_checks.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Phase 2: 'pdc_management_v19/static/src/scss/pdc_styles.scss',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
