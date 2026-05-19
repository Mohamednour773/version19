# -*- coding: utf-8 -*-
{
    'name': 'Factory Project & Estimation | مشاريع وتسعير المصنع',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Project-based estimation and pricing for factory projects | تسعير ومقايسة المشاريع المصنعية',
    'description': """
Project & Estimation
====================
- Project estimation (مقايسة) with detailed cost build-up
- Convert estimations to confirmed projects with sectors
- Per-project profitability tracking
- Integration with sale orders, analytic accounting, and sectors

مقايسة المشاريع مع تفصيل بنود التكلفة، تحويل المقايسة إلى مشروع مؤكد بقطاعاته،
تتبع الربحية لكل مشروع، التكامل مع أوامر البيع والمحاسبة التحليلية.
    """,
    'author': 'Manufacturing ERP Team',
    'license': 'LGPL-3',
    'depends': [
        'factory_base',
        'factory_molds',
        'factory_mix_design',
        'sale_management',
        'project',
        'analytic',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/estimation_sequences.xml',
        'views/factory_estimation_views.xml',
        'views/project_project_views.xml',
        'views/factory_project_menus.xml',
    ],
    'application': False,
    'installable': True,
}
