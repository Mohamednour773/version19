from odoo import api, fields, models


class PDCBounceReason(models.Model):
    _name = 'pdc.bounce.reason'
    _description = 'PDC Bounce Reason'
    _order = 'sequence, name'

    name = fields.Char(string='Reason', required=True, translate=True)
    code = fields.Char(string='Code', required=True, size=50)
    description = fields.Text(string='Description', translate=True)
    is_legal_action = fields.Boolean(
        string='Requires Legal Action',
        default=False,
        help='Flag checks with this reason for legal follow-up.',
    )
    active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10)

    # ── display ──────────────────────────────────────────────────────────────
    @api.depends('code', 'name')
    def _compute_display_name(self):
        for reason in self:
            reason.display_name = f'[{reason.code}] {reason.name}' if reason.code else (reason.name or '')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Bounce reason code must be unique.'),
    ]
