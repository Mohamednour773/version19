# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    factory_auto_create_analytic = fields.Boolean(
        string='Auto-Create Analytic Account | إنشاء حساب تحليلي تلقائياً',
        config_parameter='factory.auto_create_analytic',
        default=True,
        help='Automatically create an analytic account when a project is created | إنشاء حساب تحليلي تلقائياً عند إنشاء مشروع',
    )
    factory_track_waste = fields.Boolean(
        string='Track Production Waste | تتبع هالك الإنتاج',
        config_parameter='factory.track_waste',
        default=True,
    )
    factory_default_waste_account_id = fields.Many2one(
        'account.account',
        string='Default Waste Account | حساب الهالك الافتراضي',
        config_parameter='factory.default_waste_account_id',
    )
    factory_mold_amortization_method = fields.Selection([
        ('linear', 'Linear (per use) | خطية (لكل استخدام)'),
        ('quantity', 'By Produced Quantity | حسب الكمية المنتجة'),
        ('time', 'By Time (months) | حسب الوقت (شهور)'),
    ], string='Mold Amortization Method | طريقة إهلاك القالب',
       config_parameter='factory.mold_amortization_method',
       default='linear')
