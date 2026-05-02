from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PDCCheckBook(models.Model):
    _name = 'pdc.check.book'
    _description = 'PDC Check Book'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'issue_date desc, name'

    name = fields.Char(
        string='Reference', required=True, copy=False,
        default=lambda self: _('New'),
        tracking=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('depleted', 'Depleted'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', required=True, tracking=True)

    # ── Bank / Journal ────────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        'account.journal', string='Bank Journal', required=True,
        domain=[('type', '=', 'bank')],
        tracking=True,
    )
    bank_id = fields.Many2one(
        'pdc.bank', string='Bank',
        compute='_compute_bank_id', store=True, readonly=False,
    )
    layout_id = fields.Many2one(
        'pdc.bank.layout', string='Default Print Layout',
        domain="[('bank_id', '=', bank_id)]",
    )

    # ── Number range ─────────────────────────────────────────────────────────
    start_number = fields.Integer(string='First Check Number', required=True, tracking=True)
    end_number = fields.Integer(string='Last Check Number', required=True, tracking=True)
    next_number = fields.Integer(
        string='Next Available Number',
        compute='_compute_next_number', store=False,
    )

    # ── Computed statistics ───────────────────────────────────────────────────
    total_checks = fields.Integer(
        string='Total Checks', compute='_compute_check_counts', store=True,
    )
    used_checks = fields.Integer(
        string='Used', compute='_compute_check_counts', store=True,
    )
    available_checks = fields.Integer(
        string='Available', compute='_compute_check_counts', store=True,
    )
    cancelled_checks = fields.Integer(
        string='Cancelled', compute='_compute_check_counts', store=True,
    )
    low_stock_threshold = fields.Integer(
        string='Low Stock Alert Threshold', default=10,
        help='Show alert when available checks fall below this number.',
    )
    low_stock_alert = fields.Boolean(
        string='Low Stock Alert', compute='_compute_low_stock_alert', store=True,
    )

    # ── Dates / Company ───────────────────────────────────────────────────────
    issue_date = fields.Date(
        string='Received from Bank', required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company,
    )
    notes = fields.Text(string='Notes')

    # ── Checks O2M ────────────────────────────────────────────────────────────
    check_ids = fields.One2many('pdc.check', 'check_book_id', string='Checks')

    # ── display ──────────────────────────────────────────────────────────────
    @api.depends('name', 'bank_id')
    def _compute_display_name(self):
        for book in self:
            bank = book.bank_id.code or book.bank_id.name or ''
            book.display_name = f'[{bank}] {book.name}' if bank else (book.name or '')

    # ── Compute methods ───────────────────────────────────────────────────────
    @api.depends('journal_id')
    def _compute_bank_id(self):
        for book in self:
            if book.journal_id and book.journal_id.pdc_default_bank_id:
                book.bank_id = book.journal_id.pdc_default_bank_id
            else:
                book.bank_id = False

    @api.depends('check_ids', 'check_ids.state', 'start_number', 'end_number')
    def _compute_check_counts(self):
        for book in self:
            if not book.start_number or not book.end_number:
                book.total_checks = 0
                book.used_checks = 0
                book.cancelled_checks = 0
                book.available_checks = 0
                continue
            total = book.end_number - book.start_number + 1
            all_checks = book.check_ids
            cancelled = all_checks.filtered(lambda c: c.state == 'cancelled')
            used = len(all_checks)
            book.total_checks = total
            book.used_checks = used
            book.cancelled_checks = len(cancelled)
            book.available_checks = total - used

    @api.depends('check_ids.check_number', 'check_ids.state', 'start_number', 'end_number')
    def _compute_next_number(self):
        for book in self:
            if not book.start_number or not book.end_number:
                book.next_number = 0
                continue
            used_numbers = set(book.check_ids.mapped('check_number'))
            found = 0
            for num in range(book.start_number, book.end_number + 1):
                if str(num) not in used_numbers:
                    found = num
                    break
            book.next_number = found

    @api.depends('available_checks', 'low_stock_threshold', 'state')
    def _compute_low_stock_alert(self):
        for book in self:
            book.low_stock_alert = (
                book.state == 'active' and
                book.available_checks <= book.low_stock_threshold
            )

    # ── Onchange ──────────────────────────────────────────────────────────────
    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id and self.journal_id.pdc_default_bank_id:
            self.bank_id = self.journal_id.pdc_default_bank_id

    # ── Constraints ───────────────────────────────────────────────────────────
    @api.constrains('start_number', 'end_number')
    def _check_number_range(self):
        for book in self:
            if book.start_number <= 0:
                raise ValidationError(_('Start number must be greater than zero.'))
            if book.end_number <= 0:
                raise ValidationError(_('End number must be greater than zero.'))
            if book.start_number >= book.end_number:
                raise ValidationError(_('Start number must be less than end number.'))

    @api.constrains('journal_id', 'start_number', 'end_number', 'state')
    def _check_no_overlap(self):
        for book in self:
            if not book.journal_id or book.state == 'archived':
                continue
            overlapping = self.search([
                ('id', '!=', book.id),
                ('journal_id', '=', book.journal_id.id),
                ('state', 'not in', ['archived']),
                ('start_number', '<=', book.end_number),
                ('end_number', '>=', book.start_number),
            ])
            if overlapping:
                raise ValidationError(_(
                    'Number range %d–%d overlaps with check book "%s" (%d–%d).',
                    book.start_number, book.end_number,
                    overlapping[0].name,
                    overlapping[0].start_number, overlapping[0].end_number,
                ))

    # ── CRUD ─────────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('pdc.check.book') or _('New')
        return super().create(vals_list)

    # ── Smart-button actions ──────────────────────────────────────────────────

    def action_view_checks(self):
        """Open the list of all checks that belong to this check book."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Checks — %s', self.name),
            'res_model': 'pdc.check',
            'view_mode': 'list,form',
            'domain': [('check_book_id', '=', self.id)],
            'context': {
                'default_check_book_id': self.id,
                'default_check_type': 'issued',
            },
        }

    # ── State actions ─────────────────────────────────────────────────────────
    def action_activate(self):
        for book in self:
            if book.state != 'draft':
                raise UserError(_('Only draft check books can be activated.'))
            book.write({'state': 'active'})
            book.message_post(body=_('Check book activated.'))

    def action_archive_book(self):
        for book in self:
            if book.state not in ('active', 'depleted'):
                raise UserError(_('Only active or depleted check books can be archived.'))
            book.write({'state': 'archived'})
            book.message_post(body=_('Check book archived.'))

    # ── Business methods ──────────────────────────────────────────────────────
    def _get_next_check_number(self):
        """Return the next available check number as a string, or raise if depleted."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('Check book "%s" is not active.', self.name))
        if self.next_number == 0:
            self.sudo().write({'state': 'depleted'})  # internal state change; user may lack write perm
            raise UserError(_(
                'Check book "%s" is depleted. All %d checks have been used.',
                self.name, self.total_checks,
            ))
        return str(self.next_number)

    def _validate_check_number(self, number):
        """Validate that a number belongs to this book and has not been used."""
        self.ensure_one()
        try:
            num_int = int(number)
        except (ValueError, TypeError):
            raise ValidationError(_('Check number must be numeric for book validation.'))
        if not (self.start_number <= num_int <= self.end_number):
            raise ValidationError(_(
                'Check number %s is not within the range of book "%s" (%d–%d).',
                number, self.name, self.start_number, self.end_number,
            ))
        if number in self.check_ids.mapped('check_number'):
            raise ValidationError(_(
                'Check number %s has already been used in book "%s".',
                number, self.name,
            ))
        return True
