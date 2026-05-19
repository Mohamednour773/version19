# -*- coding: utf-8 -*-
{
    'name': 'Factory Mix Design | تصميم الخلطات',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Define and manage mix designs (recipes) with per-sector assignment | تعريف وإدارة الخلطات (الوصفات) مع تخصيصها لكل قطاع',
    'description': """
Mix Design Module
=================
- Define multiple mix designs (recipes) per product/sector
- Track theoretical vs actual material consumption
- Calculate waste/loss per material
- Per-sector mix assignment
- Material cost per mix and per produced unit
- Integration with stock and analytic accounting

تعريف خلطات متعددة للمنتج / القطاع، تتبع الاستهلاك النظري مقابل الفعلي،
حساب الهالك والفقد، تخصيص خلطة لكل قطاع، تكلفة الخامات لكل خلطة ولكل وحدة منتجة.
    """,
    'author': 'Manufacturing ERP Team',
    'license': 'LGPL-3',
    'depends': [
        'factory_base',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/mix_sequences.xml',
        'views/factory_mix_views.xml',
        'views/factory_mix_consumption_views.xml',
        'views/factory_sector_views_inherit.xml',
        'views/factory_mix_menus.xml',
    ],
    'application': False,
    'installable': True,
}
