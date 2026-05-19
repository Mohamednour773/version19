# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_factory_product = fields.Boolean(
        string='Factory Product | منتج المصنع',
        help='Check if this product is manufactured in-house | فعّل إذا كان المنتج يصنع داخلياً',
    )
    factory_product_type = fields.Selection([
        ('raw_material', 'Raw Material | خامة'),
        ('mold', 'Mold | قالب'),
        ('accessory', 'Installation Accessory | إكسسوار تركيب'),
        ('finishing', 'Finishing Material | خامة تشطيب'),
        ('finished', 'Finished Product | منتج نهائي'),
        ('semi_finished', 'Semi-Finished | نصف مصنع'),
    ], string='Factory Product Type | نوع منتج المصنع')
    
    # Waste tracking | تتبع الهالك
    standard_waste_percent = fields.Float(
        string='Standard Waste % | نسبة الهالك القياسية',
        digits=(5, 2),
        help='Expected waste percentage during production | نسبة الهالك المتوقعة أثناء الإنتاج',
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_factory_product = fields.Boolean(related='product_tmpl_id.is_factory_product', store=True)
    factory_product_type = fields.Selection(related='product_tmpl_id.factory_product_type', store=True)
