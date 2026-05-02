from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # All fields mirror res.company via related — readonly=False allows editing.

    pdc_due_soon_days = fields.Integer(
        related='company_id.pdc_due_soon_days', readonly=False,
        string='Due Soon Threshold (Days)',
    )
    pdc_alert_days_first = fields.Integer(
        related='company_id.pdc_alert_days_first', readonly=False,
        string='First Reminder (Days Before Due)',
    )
    pdc_alert_days_second = fields.Integer(
        related='company_id.pdc_alert_days_second', readonly=False,
        string='Second Reminder (Days Before Due)',
    )
    pdc_alert_days_third = fields.Integer(
        related='company_id.pdc_alert_days_third', readonly=False,
        string='Third Reminder (Days Before Due)',
    )
    pdc_auto_block_partners = fields.Boolean(
        related='company_id.pdc_auto_block_partners', readonly=False,
        string='Auto-Block Partners After Bounces',
    )
    pdc_block_threshold = fields.Integer(
        related='company_id.pdc_block_threshold', readonly=False,
        string='Bounce Block Threshold',
    )
    pdc_require_image = fields.Boolean(
        related='company_id.pdc_require_image', readonly=False,
        string='Require Check Image Upload',
    )
    pdc_company_city = fields.Char(
        related='company_id.pdc_company_city', readonly=False,
        string='Default City for Check Printing',
    )
    pdc_use_hijri = fields.Boolean(
        related='company_id.pdc_use_hijri', readonly=False,
        string='Display Hijri Dates',
    )
    pdc_default_layout_ar = fields.Boolean(
        related='company_id.pdc_default_layout_ar', readonly=False,
        string='Default to Arabic Printing',
    )
