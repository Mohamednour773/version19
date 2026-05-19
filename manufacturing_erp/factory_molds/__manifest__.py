# -*- coding: utf-8 -*-
{
    'name': 'Factory Molds Management | إدارة قوالب المصنع',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Manage molds, their lifecycle, and cost allocation per produced unit | إدارة القوالب ودورة حياتها وتوزيع تكلفتها على كل وحدة منتجة',
    'description': """
Factory Molds Management
========================
- Define molds with manufacturing cost and expected lifespan
- Track number of uses per mold
- Allocate mold cost per produced unit (linear, by quantity, or by time)
- Link molds to projects, sectors, and production orders
- Mold maintenance and refurbishment tracking
- Mold inventory location

تعريف القوالب وتكلفة تصنيعها وعمرها الافتراضي، تتبع عدد مرات الاستخدام،
وتوزيع تكلفة القالب على كل وحدة منتجة، وربط القوالب بالمشاريع والقطاعات والإنتاج.
    """,
    'author': 'Manufacturing ERP Team',
    'license': 'LGPL-3',
    'depends': [
        'factory_base',
        'stock',
        'account',
        'maintenance',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/mold_sequences.xml',
        'data/mold_categories_data.xml',
        'views/factory_mold_views.xml',
        'views/factory_mold_usage_views.xml',
        'views/factory_mold_category_views.xml',
        'views/factory_sector_views_inherit.xml',
        'views/factory_mold_menus.xml',
    ],
    'application': False,
    'installable': True,
}
