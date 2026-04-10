# -*- coding: utf-8 -*-
{
    'name': 'Sports Club & Swimming Academy Management',
    'version': '19.0.2.0.0',
    'category': 'Services/Sports',
    'summary': 'Complete management system for sports clubs and swimming academies',
    'description': """
        Sports Club & Swimming Academy Management System v2
        ====================================================
        Features:
        - Multi-branch management with data isolation
        - Group classes & private sessions with recurring schedule
        - Membership packages with weekly + total session limits enforced at booking
        - Multi-trainer sessions with commission split
        - Quick reschedule wizard with conflict detection
        - Calendar drag & drop scheduling
        - Trainer commission → Vendor Bill payment flow
        - Facility & rental booking
        - Advanced reporting: Cash, Trainer Revenue, Session Utilization
        - Excel export on all reports
        - Sales & accounting integration
    """,
    'author': 'Sports Club Solutions',
    'depends': [
        'base',
        'mail',
        'account',
        'sale',
        'product',
        'resource',
    ],
    'data': [
        # Security
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'security/club_security.xml',
        # Data
        'data/club_data.xml',
        # Views
        'views/club_branch_views.xml',
        'views/club_trainer_views.xml',
        'views/club_facility_views.xml',
        'views/club_package_views.xml',
        'views/club_membership_views.xml',
        'views/club_class_views.xml',
        'views/club_session_views.xml',
        'views/club_attendance_views.xml',
        'views/club_rental_views.xml',
        'views/res_partner_views.xml',
        'views/club_report_views.xml',
        'views/club_menus.xml',
        # Wizards
        'wizards/generate_sessions_wizard_views.xml',
        'wizards/reschedule_session_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
