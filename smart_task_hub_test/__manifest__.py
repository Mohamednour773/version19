# -*- coding: utf-8 -*-
{
    'name': 'Smart Task Hub',
    'version': '19.0.2.0.0',
    'category': 'Project',
    'summary': 'Intelligent Task Management with AI Analysis (GPT + Claude)',
    'author': 'Smart Consulting',
    'depends': ['project', 'helpdesk', 'mail', 'base_setup'],
    'data': [
        # Security first
        'security/ir.model.access.csv',
        # Data
        'data/smart_task_data.xml',
        # Core Views
        'views/smart_task_views.xml',
        'views/smart_task_kanban.xml',
        'views/smart_task_dashboard.xml',
        # Model-specific views (after their models are loaded)
        'views/smart_ai_log_views.xml',
        'views/smart_kb_views.xml',
        # Settings (before menus)
        'views/smart_task_settings.xml',
        # Menus last (depends on actions)
        'views/smart_excel_generator_views.xml',
        'views/smart_task_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_task_hub_test/static/src/js/voice_recorder.js',
            'smart_task_hub_test/static/src/css/smart_task.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
