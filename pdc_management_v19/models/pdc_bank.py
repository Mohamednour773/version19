from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PDCBank(models.Model):
    _name = 'pdc.bank'
    _description = 'PDC Bank'
    _order = 'sequence, name'

    name = fields.Char(string='Bank Name', required=True, translate=True)
    name_ar = fields.Char(
        string='Bank Name (Arabic)',
        translate=False,
        help='Arabic name of the bank as it appears on Arabic receipts and check prints.\n'
             'Example: البنك التجاري الدولي',
    )
    code = fields.Char(string='Code', required=True, size=20,
                       help='Short bank code, e.g. CIB, NBE, RAJHI.')
    country_id = fields.Many2one(
        'res.country', string='Country', required=True,
        default=lambda self: self.env.ref('base.eg', raise_if_not_found=False),
    )
    swift_code = fields.Char(string='SWIFT / BIC', size=11)
    logo = fields.Binary(string='Bank Logo', attachment=True)
    active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10)
    notes = fields.Text(string='Internal Notes')
    company_id = fields.Many2one(
        'res.company', string='Company',
        help='Leave blank to share this bank across all companies.',
    )
    layout_ids = fields.One2many('pdc.bank.layout', 'bank_id', string='Print Layouts')

    # ── display ──────────────────────────────────────────────────────────────
    @api.depends('code', 'name')
    def _compute_display_name(self):
        for bank in self:
            bank.display_name = f'[{bank.code}] {bank.name}' if bank.code else bank.name

    # ── constraints ──────────────────────────────────────────────────────────
    @api.constrains('code', 'company_id')
    def _check_unique_code(self):
        for bank in self:
            domain = [('code', '=', bank.code), ('id', '!=', bank.id)]
            if bank.company_id:
                domain += [('company_id', 'in', [bank.company_id.id, False])]
            else:
                domain += [('company_id', '=', False)]
            if self.search_count(domain):
                raise ValidationError(
                    _('Bank code "%s" already exists. Codes must be unique per company.', bank.code)
                )
