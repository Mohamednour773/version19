{
    'name': 'Access Right Management',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'Standalone Dynamic runtime access control engine for users, fields, menus, models, products, warehouses, journals, and partners.',
    'description': """
Access Right Management (Standalone)
====================================

Independent runtime security groups for Odoo 19. This module works as a standalone engine.

Features
--------
- User scoped dynamic access groups
- Runtime field hide / readonly / required rules
- Hidden menus per user group
- Model access restrictions with hidden notebook tabs
- Warehouse, location, picking type restrictions
- Product, partner, journal, and account restrictions
- Special permissions for product editing, quick create, and BoM behavior
- Domain-based dynamic deny rules
    """,
    'author': 'Codex',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'contacts',
        'product',
        'stock',
        'account',
        'mrp',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/access_right_group_views.xml',
    ],
    'installable': True,
    'application': True,
}
