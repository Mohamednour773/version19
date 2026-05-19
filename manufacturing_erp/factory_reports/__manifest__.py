# -*- coding: utf-8 -*-
{
    'name': 'Factory Reports | تقارير المصنع',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Profitability and operational reports | تقارير الربحية والعمليات',
    'description': """
Factory Reports
===============
- Project profitability dashboard | لوحة ربحية المشاريع
- Mold utilization report | تقرير استخدام القوالب
- Waste analysis report | تقرير تحليل الهالك
- Production performance report | تقرير أداء الإنتاج
- Sector progress report | تقرير تقدم القطاعات
- PDF QWeb reports | تقارير PDF
    """,
    'author': 'Manufacturing ERP Team',
    'license': 'LGPL-3',
    'depends': [
        'factory_base',
        'factory_costing',
        'factory_project',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'reports/report_estimation.xml',
        'reports/report_delivery_permit.xml',
        'reports/report_paperformat.xml',
        'reports/factory_reports_actions.xml',
        'views/factory_profitability_report_views.xml',
        'views/factory_mold_report_views.xml',
        'views/factory_waste_report_views.xml',
        'views/factory_reports_menus.xml',
    ],
    'application': False,
    'installable': True,
}
