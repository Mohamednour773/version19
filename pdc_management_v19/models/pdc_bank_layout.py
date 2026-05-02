from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PDCBankLayout(models.Model):
    _name = 'pdc.bank.layout'
    _description = 'PDC Bank Check Print Layout'
    _order = 'bank_id, is_default desc, name'

    name = fields.Char(string='Layout Name', required=True)
    bank_id = fields.Many2one('pdc.bank', string='Bank', required=True, ondelete='cascade')
    active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(string='Default Layout', default=False)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )

    # ── Paper format ──────────────────────────────────────────────────────────
    paper_format = fields.Selection([
        ('a4', 'A4'),
        ('a5', 'A5'),
        ('custom', 'Custom'),
    ], string='Paper Format', default='a5', required=True)
    paper_width = fields.Float(string='Width (mm)', default=210.0,
                               help='Used only when format is Custom.')
    paper_height = fields.Float(string='Height (mm)', default=148.0,
                                help='Used only when format is Custom.')
    orientation = fields.Selection([
        ('portrait', 'Portrait'),
        ('landscape', 'Landscape'),
    ], string='Orientation', default='landscape', required=True)

    # ── Date field coordinates ────────────────────────────────────────────────
    date_x = fields.Float(string='Date X (mm)', required=True, default=175.0)
    date_y = fields.Float(string='Date Y (mm)', required=True, default=22.0)
    date_format = fields.Char(string='Date Format', default='DD/MM/YYYY',
                              help='e.g. DD/MM/YYYY or YYYY/MM/DD')

    # ── Payee field coordinates ───────────────────────────────────────────────
    payee_x = fields.Float(string='Payee X (mm)', required=True, default=35.0)
    payee_y = fields.Float(string='Payee Y (mm)', required=True, default=38.0)

    # ── Amount in words coordinates ───────────────────────────────────────────
    amount_words_x = fields.Float(string='Amount Words X (mm)', required=True, default=35.0)
    amount_words_y = fields.Float(string='Amount Words Y (mm)', required=True, default=53.0)
    amount_words_max_width = fields.Float(string='Amount Words Max Width (mm)',
                                         required=True, default=130.0)

    # ── Amount in numbers coordinates ─────────────────────────────────────────
    amount_numbers_x = fields.Float(string='Amount Numbers X (mm)', required=True, default=175.0)
    amount_numbers_y = fields.Float(string='Amount Numbers Y (mm)', required=True, default=53.0)

    # ── City / place coordinates (optional) ──────────────────────────────────
    city_x = fields.Float(string='City X (mm)', default=35.0)
    city_y = fields.Float(string='City Y (mm)', default=22.0)

    # ── Typography ────────────────────────────────────────────────────────────
    font_size = fields.Integer(string='Font Size (pt)', default=11)
    font_family = fields.Selection([
        ('Arial', 'Arial'),
        ('Times New Roman', 'Times New Roman'),
        ('Courier New', 'Courier New'),
        ('Tahoma', 'Tahoma'),
        ('Simplified Arabic', 'Simplified Arabic'),
    ], string='Font Family', default='Arial')
    use_arabic = fields.Boolean(string='Print in Arabic', default=False)

    # ── display ──────────────────────────────────────────────────────────────
    @api.depends('name', 'bank_id')
    def _compute_display_name(self):
        for layout in self:
            bank = layout.bank_id.code or layout.bank_id.name or ''
            layout.display_name = f'[{bank}] {layout.name}' if bank else (layout.name or '')

    # ── constraints ──────────────────────────────────────────────────────────
    @api.constrains('is_default', 'bank_id', 'company_id')
    def _check_single_default(self):
        for layout in self:
            if not layout.is_default:
                continue
            domain = [
                ('bank_id', '=', layout.bank_id.id),
                ('company_id', '=', layout.company_id.id),
                ('is_default', '=', True),
                ('id', '!=', layout.id),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _('Bank "%s" already has a default layout for this company.',
                      layout.bank_id.name)
                )

    # ── actions ──────────────────────────────────────────────────────────────
    def action_test_print(self):
        """Print a calibration page with grid lines and field markers."""
        self.ensure_one()
        return self.env.ref('pdc_management_v19.action_report_pdc_layout_test').report_action(self)

    def action_duplicate(self):
        """Duplicate this layout for editing without affecting the original."""
        self.ensure_one()
        new = self.copy({'name': _('%s (Copy)', self.name), 'is_default': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': new.id,
            'view_mode': 'form',
        }
