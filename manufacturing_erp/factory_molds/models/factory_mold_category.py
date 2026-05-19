# -*- coding: utf-8 -*-
from odoo import models, fields


class FactoryMoldCategory(models.Model):
    """Mold Category | فئة القالب"""
    _name = 'factory.mold.category'
    _description = 'Mold Category | فئة القالب'
    _parent_store = True
    _parent_name = 'parent_id'
    _order = 'parent_path'

    name = fields.Char(string='Name | الاسم', required=True, translate=True)
    code = fields.Char(string='Code | الكود')
    parent_id = fields.Many2one('factory.mold.category', string='Parent | الفئة الأم', ondelete='cascade')
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many('factory.mold.category', 'parent_id', string='Children | الفئات الفرعية')
    description = fields.Text(string='Description | الوصف')
    default_expected_uses = fields.Integer(
        string='Default Expected Uses | عدد الاستخدامات الافتراضي',
        default=50,
        help='Default expected number of uses for molds in this category | العدد الافتراضي لمرات استخدام القوالب في هذه الفئة',
    )
    active = fields.Boolean(default=True)
