# -*- coding: utf-8 -*-
{
    'name': 'Factory Project Costing | تكلفة مشاريع المصنع',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Consolidated actual cost tracking per project | تجميع التكلفة الفعلية لكل مشروع',
    'description': """
Project Costing
===============
- Consolidates costs across modules: molds, mix, labor, installation, expenses
- Per-project profitability (estimated vs actual)
- Cost centers (mainly via analytic accounts)
- Automatic analytic line postings for material consumption, labor, mold usage
- Variance analysis (estimated vs actual)

تجميع التكاليف عبر الموديولات: قوالب، خلطات، عمالة، تركيب، مصاريف
ربحية كل مشروع (المتوقع مقابل الفعلي)
مراكز التكلفة (عبر الحسابات التحليلية)
ترحيل سطور تحليلية تلقائي لاستهلاك الخامات والعمالة واستخدام القوالب
تحليل الفروقات (المتوقع مقابل الفعلي)
    """,
    'author': 'Manufacturing ERP Team',
    'license': 'LGPL-3',
    'depends': [
        'factory_base',
        'factory_molds',
        'factory_mix_design',
        'factory_production',
        'factory_site_installation',
        'factory_project',
        'analytic',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/project_project_views.xml',
        'views/factory_sector_views_inherit.xml',
        'views/factory_costing_menus.xml',
    ],
    'application': False,
    'installable': True,
}
