from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ── Due-date alerting ─────────────────────────────────────────────────────
    pdc_due_soon_days = fields.Integer(
        string='Due Soon Threshold (Days)',
        default=7,
        help='Checks due within this many days are flagged as "Due Soon".',
    )
    pdc_alert_days_first = fields.Integer(
        string='First Reminder (Days Before Due)',
        default=3,
        help='Send first (most urgent) reminder this many days before due date. Set 0 to disable.',
    )
    pdc_alert_days_second = fields.Integer(
        string='Second Reminder (Days Before Due)',
        default=7,
        help='Send second reminder this many days before due date. Set 0 to disable.',
    )
    pdc_alert_days_third = fields.Integer(
        string='Third Reminder (Days Before Due)',
        default=15,
        help='Send third (early warning) reminder this many days before due date. Set 0 to disable.',
    )

    # ── Partner auto-blocking ─────────────────────────────────────────────────
    pdc_auto_block_partners = fields.Boolean(
        string='Auto-Block Partners After Bounces',
        default=False,
        help='Automatically flag a partner as blocked after N bounced checks.',
    )
    pdc_block_threshold = fields.Integer(
        string='Bounce Block Threshold',
        default=3,
        help='Number of unsettled bounced checks that triggers partner auto-block.',
    )

    # ── Operational settings ──────────────────────────────────────────────────
    pdc_require_image = fields.Boolean(
        string='Require Check Image Upload',
        default=False,
        help='Enforce uploading a front-image of the check before registration.',
    )
    pdc_company_city = fields.Char(
        string='Default City for Check Printing',
        help='Pre-filled city/place on printed checks.',
    )

    # ── Localization ──────────────────────────────────────────────────────────
    pdc_use_hijri = fields.Boolean(
        string='Display Hijri Dates',
        default=False,
        help='Show Hijri (Islamic calendar) dates alongside Gregorian dates.',
    )
    pdc_default_layout_ar = fields.Boolean(
        string='Default to Arabic Printing',
        default=False,
        help='Check print layout defaults to Arabic language.',
    )
