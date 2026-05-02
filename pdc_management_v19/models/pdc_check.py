import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)

# Soft dependency: hijri_converter is optional (Saudi Hijri date feature).
# The module installs and runs normally without it; Hijri fields return ''.
try:
    from hijri_converter import convert as _hijri_convert
    HIJRI_AVAILABLE = True
except ImportError:
    _hijri_convert = None
    HIJRI_AVAILABLE = False

# ── State transition map ───────────────────────────────────────────────────────
# Defines the allowed next states for each (check_type, current_state) pair.
#
# Guarantee activation is NOT a state transition — it is a type conversion:
#   action_activate_guarantee() changes check_type to 'received'/'issued' and
#   sets state='registered', then the check follows the normal received/issued flow.
#   The was_guarantee flag preserves historical context after activation.
_VALID_TRANSITIONS = {
    'received': {
        'draft': ['registered', 'cancelled'],
        'registered': ['under_collection', 'cancelled'],
        'under_collection': ['cleared', 'bounced', 'cancelled'],  # manager-only via cancel wizard
        'bounced': ['settled', 'cancelled'],
        'settled': [],
        'cleared': [],
        'cancelled': [],
    },
    'issued': {
        'draft': ['registered', 'cancelled'],
        'registered': ['printed', 'cancelled'],
        'printed': ['delivered', 'cancelled'],
        'delivered': ['paid', 'bounced', 'cancelled'],
        'bounced': ['settled', 'cancelled'],
        'settled': [],
        'paid': [],
        'cancelled': [],
    },
    # Guarantees only cover the pre-activation lifecycle.
    # Once activated, check_type flips to 'received'/'issued' and the
    # normal transitions above take over from 'registered'.
    'guarantee_received': {
        'draft': ['registered', 'cancelled'],
        'registered': ['returned', 'cancelled'],
        'returned': [],
        'cancelled': [],
    },
    'guarantee_issued': {
        'draft': ['registered', 'cancelled'],
        'registered': ['returned', 'cancelled'],
        'returned': [],
        'cancelled': [],
    },
}

_TERMINAL_STATES = frozenset(['cleared', 'paid', 'settled', 'returned', 'cancelled'])

# Core financial/identity fields that must not be edited in terminal states.
_PROTECTED_FIELDS = frozenset([
    'amount', 'currency_id', 'check_number', 'bank_id', 'partner_id',
    'issue_date', 'due_date', 'check_type', 'journal_id', 'check_book_id',
])

# Kanban color map  (0=grey, 1=red, 3=yellow, 4=light-blue, 6=salmon, 10=green)
_STATE_COLOR = {
    'draft': 0,
    'registered': 4,
    'under_collection': 3,
    'printed': 3,
    'delivered': 3,
    'cleared': 10,
    'paid': 10,
    'settled': 6,
    'bounced': 1,
    'returned': 6,
    'cancelled': 9,
}


class PDCCheck(models.Model):
    _name = 'pdc.check'
    _description = 'PDC Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_date, name'

    # =========================================================================
    # FIELDS
    # =========================================================================

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Reference', required=True, copy=False,
        default=lambda self: _('New'), tracking=True,
    )
    check_type = fields.Selection([
        ('received', 'Received'),
        ('issued', 'Issued'),
        ('guarantee_received', 'Guarantee (Received)'),
        ('guarantee_issued', 'Guarantee (Issued)'),
    ], string='Check Type', required=True, default='received',
        tracking=True, index=True,
    )
    check_number = fields.Char(
        string='Check Number', required=True,
        help='Number printed on the physical check.',
        index=True,
    )
    check_book_id = fields.Many2one(
        'pdc.check.book', string='Check Book',
        ondelete='restrict',
        help='Required for issued checks. The book this check belongs to.',
    )

    # ── Bank / Branch ─────────────────────────────────────────────────────────
    bank_id = fields.Many2one(
        'pdc.bank', string='Drawee Bank', required=True, index=True,
        tracking=True,
    )
    branch = fields.Char(string='Bank Branch')

    # ── Dates ─────────────────────────────────────────────────────────────────
    issue_date = fields.Date(
        string='Issue Date', required=True,
        default=fields.Date.today, tracking=True,
    )
    due_date = fields.Date(
        string='Due Date', required=True, tracking=True, index=True,
    )

    # ── Amount ────────────────────────────────────────────────────────────────
    amount = fields.Monetary(
        string='Amount', required=True, tracking=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id,
    )
    amount_in_words = fields.Char(
        string='Amount in Words (EN)',
        compute='_compute_amount_in_words', store=True,
    )
    amount_in_words_ar = fields.Char(
        string='Amount in Words (AR)',
        compute='_compute_amount_in_words_ar', store=True,
    )
    display_amount = fields.Char(
        string='Amount Display',
        compute='_compute_display_amount', store=False,
    )

    # ── Parties ───────────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True,
        tracking=True, index=True,
        help='Customer for received checks; Supplier for issued checks.',
    )
    drawer_name = fields.Char(
        string='Drawer Name',
        help='Name of the person/company who signed the check (received checks).',
    )
    payee_name = fields.Char(
        string='Payee Name',
        help='Name of the beneficiary printed on the check (issued checks).',
    )
    signatory = fields.Char(string='Signatory')
    partner_pdc_blocked = fields.Boolean(
        related='partner_id.pdc_blocked',
        string='Partner Blocked',
        store=False,
        help='True when the partner is PDC-blocked due to excessive bounced checks.',
    )
    responsible_id = fields.Many2one(
        'res.users', string='Responsible',
        default=lambda self: self.env.user,
        tracking=True, index=True,
        help='Person responsible for follow-up on this check '
             '(collections officer, treasury, etc.).',
    )
    display_responsible = fields.Char(
        string='Responsible Name',
        compute='_compute_display_responsible', store=False,
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('registered', 'Registered'),
        ('under_collection', 'Under Collection'),
        ('cleared', 'Cleared'),
        ('bounced', 'Bounced'),
        ('settled', 'Settled'),
        ('printed', 'Printed'),
        ('delivered', 'Delivered'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Returned'),
    ], string='Status', default='draft', required=True,
        tracking=True, index=True, copy=False,
    )
    substate = fields.Char(
        string='Status Detail',
        compute='_compute_substate', store=False,
    )
    color = fields.Integer(
        string='Kanban Color',
        compute='_compute_color', store=False,
    )
    was_guarantee = fields.Boolean(
        string='Originally a Guarantee',
        default=False, copy=False,
        help='Set to True when a guarantee check is activated and converted to a '
             'regular received/issued check. Preserved for historical reporting.',
    )

    # ── Accounting ────────────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        'account.journal', string='Bank Journal',
        required=True, domain=[('type', '=', 'bank')],
        default=lambda self: self._default_journal_id(),
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company,
        index=True,
    )
    move_ids = fields.Many2many(
        'account.move',
        'pdc_check_move_rel',
        'check_id', 'move_id',
        string='Journal Entries',
        copy=False,
    )
    move_count = fields.Integer(
        string='Journal Entries',
        compute='_compute_move_count', store=False,
    )
    account_payment_id = fields.Many2one(
        'account.payment', string='Payment',
        copy=False, ondelete='set null',
    )
    invoice_ids = fields.Many2many(
        'account.move',
        'pdc_check_invoice_rel',
        'check_id', 'invoice_id',
        string='Invoices',
        domain=[('move_type', 'in', ['out_invoice', 'in_invoice', 'out_refund', 'in_refund'])],
        copy=False,
    )
    invoice_count = fields.Integer(
        string='Invoices',
        compute='_compute_invoice_count', store=False,
    )

    # ── Banking details (populated during workflow) ────────────────────────────
    deposit_date = fields.Date(string='Deposit Date', tracking=True)
    clear_date = fields.Date(string='Clear Date', tracking=True)
    deposit_journal_id = fields.Many2one(
        'account.journal', string='Deposit Bank',
        domain=[('type', '=', 'bank')],
    )

    # ── Bounce information ────────────────────────────────────────────────────
    is_bounced = fields.Boolean(
        string='Bounced', compute='_compute_is_bounced', store=True,
    )
    bounce_date = fields.Date(string='Bounce Date', tracking=True)
    bounce_reason_id = fields.Many2one(
        'pdc.bounce.reason', string='Bounce Reason',
    )
    bounce_charges = fields.Monetary(
        string='Bank Charges', currency_field='currency_id',
    )
    bounce_charges_source = fields.Selection([
        ('deposit_journal', 'Deposit Bank Journal (Recommended)'),
        ('original_journal', 'Original Check Journal'),
        ('custom_account', 'Custom Account'),
    ], string='Bounce Charges Source', default='deposit_journal',
        help='Determines which journal/account books the bank charges on a bounced check.\n'
             '• Deposit Bank Journal: most common for received checks '
             '(charges raised by the collecting bank)\n'
             '• Original Check Journal: most common for issued checks '
             '(charges raised by your own bank)\n'
             '• Custom Account: select a specific P&L account directly',
    )
    bounce_charges_account_id = fields.Many2one(
        'account.account',
        string='Custom Charges Account',
        domain=[('account_type', '=', 'expense')],
        help='Expense account for bounce charges. '
             'Used only when "Bounce Charges Source" is set to "Custom Account".',
    )
    bounce_notes = fields.Text(string='Bounce Notes')
    settled_date = fields.Date(string='Settlement Date')

    # ── Operations log ────────────────────────────────────────────────────────
    operation_ids = fields.One2many(
        'pdc.check.operation', 'check_id', string='Operations', readonly=True,
    )
    operation_count = fields.Integer(
        string='Operations',
        compute='_compute_operation_count', store=False,
    )

    # ── Attachments / Notes ───────────────────────────────────────────────────
    check_image_front = fields.Binary(string='Check Image (Front)', attachment=True)
    check_image_back = fields.Binary(string='Check Image (Back)', attachment=True)
    narration = fields.Text(string='Notes / Narration')

    # ── Computed helpers ──────────────────────────────────────────────────────
    days_to_due = fields.Integer(
        string='Days to Due Date',
        compute='_compute_days_to_due', store=False,
    )
    is_overdue = fields.Boolean(
        string='Overdue',
        compute='_compute_is_overdue', search='_search_is_overdue', store=False,
    )
    is_due_soon = fields.Boolean(
        string='Due Soon',
        compute='_compute_is_due_soon', search='_search_is_due_soon', store=False,
    )

    # Button visibility helpers (used directly in views as invisible= conditions)
    can_register = fields.Boolean(compute='_compute_can_actions', store=False)
    can_deposit = fields.Boolean(compute='_compute_can_actions', store=False)
    can_clear = fields.Boolean(compute='_compute_can_actions', store=False)
    can_bounce = fields.Boolean(compute='_compute_can_actions', store=False)
    can_print = fields.Boolean(compute='_compute_can_actions', store=False)
    can_deliver = fields.Boolean(compute='_compute_can_actions', store=False)
    can_pay = fields.Boolean(compute='_compute_can_actions', store=False)
    can_settle = fields.Boolean(compute='_compute_can_actions', store=False)
    can_cancel = fields.Boolean(compute='_compute_can_actions', store=False)
    can_return_guarantee = fields.Boolean(compute='_compute_can_actions', store=False)
    can_activate_guarantee = fields.Boolean(compute='_compute_can_actions', store=False)

    # ── Hijri dates ───────────────────────────────────────────────────────────
    issue_date_hijri = fields.Char(
        string='Issue Date (Hijri)',
        compute='_compute_dates_hijri', store=False,
    )
    due_date_hijri = fields.Char(
        string='Due Date (Hijri)',
        compute='_compute_dates_hijri', store=False,
    )

    # ── display ──────────────────────────────────────────────────────────────
    @api.depends('name', 'check_type', 'check_number')
    def _compute_display_name(self):
        for check in self:
            check.display_name = check.name or ''

    # =========================================================================
    # DEFAULTS
    # =========================================================================

    def _default_journal_id(self):
        return self.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', self.env.company.id)],
            limit=1,
        )

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('amount', 'currency_id')
    def _compute_amount_in_words(self):
        for check in self:
            check.amount_in_words = check._get_amount_in_words('en')

    @api.depends('amount', 'currency_id')
    def _compute_amount_in_words_ar(self):
        for check in self:
            check.amount_in_words_ar = check._get_amount_in_words('ar')

    @api.depends('amount', 'currency_id')
    def _compute_display_amount(self):
        for check in self:
            if check.currency_id and check.amount:
                check.display_amount = formatLang(
                    self.env, check.amount, currency_obj=check.currency_id
                )
            else:
                check.display_amount = ''

    @api.depends('due_date')
    def _compute_days_to_due(self):
        today = fields.Date.today()
        for check in self:
            if check.due_date:
                check.days_to_due = (check.due_date - today).days
            else:
                check.days_to_due = 0

    @api.depends('due_date', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for check in self:
            check.is_overdue = (
                bool(check.due_date)
                and check.due_date < today
                and check.state not in _TERMINAL_STATES
            )

    def _search_is_overdue(self, operator, value):
        today = fields.Date.today()
        overdue_domain = [
            ('due_date', '<', today),
            ('state', 'not in', list(_TERMINAL_STATES)),
        ]
        not_overdue_domain = [
            '|', '|',
            ('due_date', '=', False),
            ('due_date', '>=', today),
            ('state', 'in', list(_TERMINAL_STATES)),
        ]
        want_true = (operator != '!=' and bool(value)) or (operator == '!=' and not bool(value))
        return overdue_domain if want_true else not_overdue_domain
    @api.depends('due_date', 'state', 'company_id.pdc_due_soon_days')
    def _compute_is_due_soon(self):
        today = fields.Date.today()
        for check in self:
            if not check.due_date or check.state in _TERMINAL_STATES:
                check.is_due_soon = False
                continue
            threshold = check.company_id.pdc_due_soon_days or 7
            days = (check.due_date - today).days
            check.is_due_soon = 0 <= days <= threshold

    def _search_is_due_soon(self, operator, value):
        today = fields.Date.today()
        threshold = self.env.company.pdc_due_soon_days or 7
        due_limit = fields.Date.add(today, days=threshold)
        due_soon_domain = [
            ('due_date', '>=', today),
            ('due_date', '<=', due_limit),
            ('state', 'not in', list(_TERMINAL_STATES)),
        ]
        not_due_soon_domain = [
            '|', '|', '|',
            ('due_date', '=', False),
            ('due_date', '<', today),
            ('due_date', '>', due_limit),
            ('state', 'in', list(_TERMINAL_STATES)),
        ]
        want_true = (operator != '!=' and bool(value)) or (operator == '!=' and not bool(value))
        return due_soon_domain if want_true else not_due_soon_domain
    @api.depends('state')
    def _compute_is_bounced(self):
        for check in self:
            check.is_bounced = check.state == 'bounced'

    @api.depends('move_ids')
    def _compute_move_count(self):
        for check in self:
            check.move_count = len(check.move_ids)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for check in self:
            check.invoice_count = len(check.invoice_ids)

    @api.depends('operation_ids')
    def _compute_operation_count(self):
        for check in self:
            check.operation_count = len(check.operation_ids)

    @api.depends('state')
    def _compute_color(self):
        for check in self:
            check.color = _STATE_COLOR.get(check.state, 0)

    @api.depends('state', 'check_type', 'was_guarantee')
    def _compute_substate(self):
        labels = {
            ('received', 'draft'): _('Pending Registration'),
            ('received', 'registered'): _('Registered — Not Deposited'),
            ('received', 'under_collection'): _('Deposited — Awaiting Clearance'),
            ('received', 'cleared'): _('Cleared'),
            ('received', 'bounced'): _('Bounced — Pending Settlement'),
            ('received', 'settled'): _('Bounce Settled'),
            ('received', 'cancelled'): _('Cancelled'),
            ('issued', 'draft'): _('Pending Registration'),
            ('issued', 'registered'): _('Registered — Not Printed'),
            ('issued', 'printed'): _('Printed — Not Delivered'),
            ('issued', 'delivered'): _('Delivered — Awaiting Payment'),
            ('issued', 'paid'): _('Paid'),
            ('issued', 'bounced'): _('Bounced — Pending Settlement'),
            ('issued', 'settled'): _('Bounce Settled'),
            ('issued', 'cancelled'): _('Cancelled'),
            ('guarantee_received', 'draft'): _('Guarantee — Pending Registration'),
            ('guarantee_received', 'registered'): _('Guarantee — Registered (Awaiting Activation or Return)'),
            ('guarantee_received', 'returned'): _('Guarantee Returned'),
            ('guarantee_received', 'cancelled'): _('Cancelled'),
            ('guarantee_issued', 'draft'): _('Guarantee — Pending Registration'),
            ('guarantee_issued', 'registered'): _('Guarantee — Registered (Awaiting Activation or Return)'),
            ('guarantee_issued', 'returned'): _('Guarantee Returned'),
            ('guarantee_issued', 'cancelled'): _('Cancelled'),
        }
        for check in self:
            label = labels.get((check.check_type, check.state))
            if not label:
                label = dict(self._fields['state'].selection).get(check.state, check.state)
            # Append a note for activated guarantees that are now in normal flow
            if check.was_guarantee and check.check_type in ('received', 'issued'):
                label = _('(ex-Guarantee) ') + label
            check.substate = label

    @api.depends('state', 'check_type')
    def _compute_can_actions(self):
        for check in self:
            s = check.state
            t = check.check_type
            check.can_register = s == 'draft'
            # After guarantee activation, check_type is already 'received'/'issued'
            # so these conditions simply cover both original and post-activation cases.
            check.can_deposit = t == 'received' and s == 'registered'
            check.can_print = t == 'issued' and s == 'registered'
            check.can_clear = s == 'under_collection'
            check.can_bounce = s in ('under_collection', 'delivered')
            check.can_deliver = s == 'printed'
            check.can_pay = s == 'delivered'
            check.can_settle = s == 'bounced'
            check.can_cancel = s not in _TERMINAL_STATES
            check.can_return_guarantee = (
                t in ('guarantee_received', 'guarantee_issued') and s == 'registered'
            )
            check.can_activate_guarantee = (
                t in ('guarantee_received', 'guarantee_issued') and s == 'registered'
            )

    @api.depends('issue_date', 'due_date')
    def _compute_dates_hijri(self):
        for check in self:
            check.issue_date_hijri = self._to_hijri(check.issue_date)
            check.due_date_hijri = self._to_hijri(check.due_date)

    @api.depends('responsible_id', 'create_uid')
    def _compute_display_responsible(self):
        for check in self:
            check.display_responsible = (
                check.responsible_id.name if check.responsible_id
                else (check.create_uid.name if check.create_uid else '')
            )

    # =========================================================================
    # CONSTRAINTS
    # =========================================================================

    @api.constrains('issue_date', 'due_date')
    def _check_dates(self):
        for check in self:
            if check.issue_date and check.due_date:
                if check.due_date < check.issue_date:
                    raise ValidationError(
                        _('Due date cannot be before issue date on check "%s".', check.name)
                    )

    @api.constrains('amount')
    def _check_amount(self):
        for check in self:
            if check.amount <= 0:
                raise ValidationError(
                    _('Check amount must be greater than zero on check "%s".', check.name)
                )

    @api.constrains('check_number', 'bank_id', 'company_id', 'issue_date', 'check_type')
    def _check_unique_check_number(self):
        for check in self:
            if not all([check.check_number, check.bank_id, check.issue_date, check.check_type]):
                continue
            year = check.issue_date.year
            domain = [
                ('id', '!=', check.id),
                ('check_number', '=', check.check_number),
                ('bank_id', '=', check.bank_id.id),
                ('company_id', '=', check.company_id.id),
                ('check_type', '=', check.check_type),
                ('issue_date', '>=', f'{year}-01-01'),
                ('issue_date', '<=', f'{year}-12-31'),
                ('state', '!=', 'cancelled'),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    'Check number "%(number)s" already exists for %(type)s checks '
                    'at bank "%(bank)s" in %(year)s.',
                    number=check.check_number,
                    type=dict(self._fields['check_type'].selection).get(check.check_type),
                    bank=check.bank_id.name,
                    year=year,
                ))

    @api.constrains('check_type', 'check_book_id')
    def _check_check_book_required(self):
        for check in self:
            if check.check_type in ('issued', 'guarantee_issued') and not check.check_book_id:
                raise ValidationError(
                    _('A check book is required for issued checks ("%s").', check.name)
                )

    # =========================================================================
    # ONCHANGE METHODS
    # =========================================================================

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            if self.check_type in ('received', 'guarantee_received'):
                self.drawer_name = self.partner_id.name
            else:
                self.payee_name = self.partner_id.name

    @api.onchange('check_book_id')
    def _onchange_check_book_id(self):
        if self.check_book_id:
            self.journal_id = self.check_book_id.journal_id
            self.bank_id = self.check_book_id.bank_id
            if self.check_book_id.next_number:
                self.check_number = str(self.check_book_id.next_number)

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id:
            self.currency_id = (
                self.journal_id.currency_id or self.journal_id.company_id.currency_id
            )

    @api.onchange('check_type')
    def _onchange_check_type_bounce_source(self):
        """Adjust bounce charges source default when check type changes on the form."""
        if self.check_type in ('issued', 'guarantee_issued'):
            self.bounce_charges_source = 'original_journal'
        else:
            self.bounce_charges_source = 'deposit_journal'

    # =========================================================================
    # CRUD OVERRIDES
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        _sequence_map = {
            'received': 'pdc.check.received',
            'issued': 'pdc.check.issued',
            'guarantee_received': 'pdc.check.guarantee',
            'guarantee_issued': 'pdc.check.guarantee',
        }
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                check_type = vals.get('check_type', 'received')
                seq_code = _sequence_map.get(check_type, 'pdc.check.received')
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
            # Issued checks default to 'original_journal' for bounce charges source
            # (charges are raised by your own bank, not the collecting bank).
            if vals.get('check_type') in ('issued', 'guarantee_issued'):
                vals.setdefault('bounce_charges_source', 'original_journal')
        return super().create(vals_list)

    def write(self, vals):
        # Protect financial/identity fields in terminal states.
        protected = _PROTECTED_FIELDS.intersection(vals.keys())
        if protected:
            for check in self:
                if check.state in _TERMINAL_STATES:
                    raise UserError(_(
                        'Cannot modify fields %s on a %s check "%s".',
                        ', '.join(protected), check.state, check.name,
                    ))
        return super().write(vals)

    def unlink(self):
        for check in self:
            if check.operation_ids:
                raise UserError(_(
                    'Cannot delete check "%s" because it has operations history. '
                    'Cancel it instead.',
                    check.name,
                ))
        return super().unlink()

    # =========================================================================
    # STATE TRANSITION ACTIONS
    # =========================================================================

    def action_register(self):
        """Register a check and create the opening journal entry.

        Received:          Dr PDC-Received  /  Cr Partner-Receivable
        Issued:            Dr Partner-Payable  /  Cr PDC-Issued
        Guarantee (both):  Off-balance-sheet — state change only, no entry
        """
        for check in self:
            check._check_state_transition('registered')
            move = check._create_registration_move()
            check._create_operation(
                'register', to_state='registered',
                move_id=move,
                notes=_(
                    'Guarantee check — off-balance sheet.'
                ) if not move else None,
            )
            check.write({'state': 'registered'})
            check.message_post(body=_('Check registered.'))
        return True

    def action_deposit(self):
        """Deposit a received check into the bank for collection.

        Requires on the check record before calling:
          - deposit_journal_id  (the collecting bank journal)
          - deposit_date        (optional; defaults to today)

        Journal entry (posted to deposit_journal_id):
          Dr PDC-Under-Collection  /  Cr PDC-Received
        """
        for check in self:
            check._check_state_transition('under_collection')

            if not check.deposit_journal_id:
                raise UserError(_(
                    'Please set the "Deposit Bank" on check "%s" before depositing.',
                    check.name,
                ))

            # ── Validate required accounts on both journals ────────────────
            check._validate_journal_accounts(
                check.journal_id, 'pdc_received_account_id',
            )
            check._validate_journal_accounts(
                check.deposit_journal_id, 'pdc_received_collection_account_id',
            )

            pdc_acc = check.journal_id.pdc_received_account_id
            collection_acc = check.deposit_journal_id.pdc_received_collection_account_id
            deposit_date = check.deposit_date or fields.Date.today()

            amount_co, amount_fx, fx_cur = check._get_amounts(date=deposit_date)
            cur_id = fx_cur.id if fx_cur else False
            label = _('PDC Deposited: %s', check.check_number)
            lines = [
                check._build_move_line(
                    collection_acc.id, check.partner_id.id,
                    amount_co, 0.0, label,
                    cur_id, amount_fx,
                ),
                check._build_move_line(
                    pdc_acc.id, check.partner_id.id,
                    0.0, amount_co, label,
                    cur_id, -amount_fx if amount_fx is not None else None,
                ),
            ]
            move = check._post_move(
                check.deposit_journal_id.id,
                _('%s - Deposited for Collection', check.name),
                lines,
                date=deposit_date,
            )
            check._create_operation('deposit', to_state='under_collection', move_id=move)
            check.write({
                'state': 'under_collection',
                'deposit_date': deposit_date,
            })
            check.message_post(body=_(
                'Check deposited for collection via journal "%s".',
                check.deposit_journal_id.name,
            ))
        return True

    def action_clear(self):
        """Clear a check confirmed paid by the bank.

        Journal entry (posted to deposit_journal_id):
          Dr Bank  /  Cr PDC-Under-Collection
        """
        for check in self:
            check._check_state_transition('cleared')

            if not check.deposit_journal_id:
                raise UserError(_(
                    'No deposit journal on check "%s". '
                    'The check must be deposited before it can be cleared.',
                    check.name,
                ))
            check._validate_journal_accounts(
                check.deposit_journal_id, 'pdc_received_collection_account_id',
            )
            if not check.deposit_journal_id.default_account_id:
                raise UserError(_(
                    'Deposit journal "%s" has no default bank account set.',
                    check.deposit_journal_id.name,
                ))

            collection_acc = check.deposit_journal_id.pdc_received_collection_account_id
            bank_acc = check.deposit_journal_id.default_account_id
            clear_date = check.clear_date or fields.Date.today()

            amount_co, amount_fx, fx_cur = check._get_amounts(date=clear_date)
            cur_id = fx_cur.id if fx_cur else False
            label = _('PDC Cleared: %s', check.check_number)
            lines = [
                check._build_move_line(
                    bank_acc.id, check.partner_id.id,
                    amount_co, 0.0, label,
                    cur_id, amount_fx,
                ),
                check._build_move_line(
                    collection_acc.id, check.partner_id.id,
                    0.0, amount_co, label,
                    cur_id, -amount_fx if amount_fx is not None else None,
                ),
            ]
            move = check._post_move(
                check.deposit_journal_id.id,
                _('%s - Cleared', check.name),
                lines,
                date=clear_date,
            )
            check._create_operation('clear', to_state='cleared', move_id=move)
            check.write({
                'state': 'cleared',
                'clear_date': clear_date,
            })
            check.message_post(body=_('Check cleared — payment confirmed by bank.'))
        return True

    def action_bounce(self):
        """Record a bounced check and create the reversal + charges entry.

        Requires on the check record before calling:
          - bounce_date             (optional; defaults to today)
          - bounce_reason_id        (optional but strongly recommended)
          - bounce_charges          (optional; defaults to 0.0)
          - bounce_charges_source   (default: 'deposit_journal' for received,
                                             'original_journal' for issued)
          - bounce_charges_account_id (required only when source='custom_account')

        Received check (from under_collection):
          Dr Partner-Receivable [check amount]
          Dr Bounce-Charges-Expense [charges, if any]  ← source-selected account
            Cr PDC-Under-Collection [check amount]
            Cr Bank [charges, if any]                  ← source-selected bank

        Issued check (from delivered):
          Dr PDC-Issued-Delivered [check amount]
          Dr Bounce-Charges-Expense [charges, if any]  ← source-selected account
            Cr Partner-Payable [check amount]
            Cr Bank [charges, if any]                  ← source-selected bank
        """
        for check in self:
            check._check_state_transition('bounced')
            bounce_date = check.bounce_date or fields.Date.today()
            charges = check.bounce_charges or 0.0

            amount_co, amount_fx, fx_cur = check._get_amounts(date=bounce_date)
            cur_id = fx_cur.id if fx_cur else False

            # Convert charges to company currency (charges stored in check currency)
            charges_co = charges
            if charges and fx_cur:
                charges_co = fx_cur._convert(
                    charges, check.company_id.currency_id,
                    check.company_id, bounce_date,
                )

            if check.state == 'under_collection':
                # ── Received check bounce ──────────────────────────────────
                if not check.deposit_journal_id:
                    raise UserError(_(
                        'No deposit journal on check "%s". '
                        'Cannot record bounce without the collection journal.',
                        check.name,
                    ))
                check._validate_journal_accounts(
                    check.deposit_journal_id, 'pdc_received_collection_account_id',
                )
                if not check.deposit_journal_id.default_account_id:
                    raise UserError(_(
                        'Deposit journal "%s" has no default bank account set.',
                        check.deposit_journal_id.name,
                    ))
                partner_acc = check.partner_id.property_account_receivable_id
                if not partner_acc:
                    raise UserError(_(
                        'Partner "%s" has no Accounts Receivable configured.',
                        check.partner_id.name,
                    ))
                collection_acc = check.deposit_journal_id.pdc_received_collection_account_id

                # Resolve user-selectable charges source
                charges_acc, charges_bank_acc = check._resolve_bounce_charges_accounts(
                    is_received=True,
                )

                label = _('PDC Bounced (Received): %s', check.check_number)
                lines = [
                    # Dr Partner-Receivable — restore the receivable
                    check._build_move_line(
                        partner_acc.id, check.partner_id.id,
                        amount_co, 0.0, label,
                        cur_id, amount_fx,
                    ),
                    # Cr PDC-Under-Collection — clear the collection account
                    check._build_move_line(
                        collection_acc.id, check.partner_id.id,
                        0.0, amount_co, label,
                        cur_id, -amount_fx if amount_fx is not None else None,
                    ),
                ]
                if charges:
                    charges_label = _('Bounce Charges: %s', check.check_number)
                    lines += [
                        check._build_move_line(
                            charges_acc.id, check.partner_id.id,
                            charges_co, 0.0, charges_label,
                            cur_id, charges if cur_id else None,
                        ),
                        check._build_move_line(
                            charges_bank_acc.id, False,
                            0.0, charges_co, charges_label,
                            cur_id, -charges if cur_id else None,
                        ),
                    ]
                move = check._post_move(
                    check.deposit_journal_id.id,
                    _('%s - Bounced', check.name),
                    lines,
                    date=bounce_date,
                )

            else:
                # ── Issued check bounce (from delivered) ───────────────────
                check._validate_journal_accounts(
                    check.journal_id, 'pdc_issued_delivered_account_id',
                )
                if not check.journal_id.default_account_id:
                    raise UserError(_(
                        'Journal "%s" has no default bank account set.',
                        check.journal_id.name,
                    ))
                partner_acc = check.partner_id.property_account_payable_id
                if not partner_acc:
                    raise UserError(_(
                        'Partner "%s" has no Accounts Payable configured.',
                        check.partner_id.name,
                    ))
                delivered_acc = check.journal_id.pdc_issued_delivered_account_id

                # Resolve user-selectable charges source
                charges_acc, charges_bank_acc = check._resolve_bounce_charges_accounts(
                    is_received=False,
                )

                label = _('PDC Bounced (Issued): %s', check.check_number)
                lines = [
                    # Dr PDC-Issued-Delivered — reverse the delivery
                    check._build_move_line(
                        delivered_acc.id, check.partner_id.id,
                        amount_co, 0.0, label,
                        cur_id, amount_fx,
                    ),
                    # Cr Partner-Payable — restore the payable
                    check._build_move_line(
                        partner_acc.id, check.partner_id.id,
                        0.0, amount_co, label,
                        cur_id, -amount_fx if amount_fx is not None else None,
                    ),
                ]
                if charges:
                    charges_label = _('Bounce Charges: %s', check.check_number)
                    lines += [
                        check._build_move_line(
                            charges_acc.id, check.partner_id.id,
                            charges_co, 0.0, charges_label,
                            cur_id, charges if cur_id else None,
                        ),
                        check._build_move_line(
                            charges_bank_acc.id, False,
                            0.0, charges_co, charges_label,
                            cur_id, -charges if cur_id else None,
                        ),
                    ]
                move = check._post_move(
                    check.journal_id.id,
                    _('%s - Bounced', check.name),
                    lines,
                    date=bounce_date,
                )

            check._create_operation(
                'bounce', to_state='bounced', move_id=move,
                notes=_(
                    'Reason: %s. Bank charges: %s. Charges source: %s.',
                    check.bounce_reason_id.name if check.bounce_reason_id else _('—'),
                    formatLang(self.env, charges, currency_obj=check.currency_id),
                    dict(check._fields['bounce_charges_source'].selection).get(
                        check.bounce_charges_source, check.bounce_charges_source
                    ),
                ),
            )
            check.write({
                'state': 'bounced',
                'bounce_date': bounce_date,
            })
            check.message_post(body=_(
                'Check bounced. Reason: %(reason)s. Bank charges: %(charges)s.',
                reason=check.bounce_reason_id.name if check.bounce_reason_id else _('Not specified'),
                charges=formatLang(self.env, charges, currency_obj=check.currency_id),
            ))
        return True

    def action_settle(self):
        """Mark a bounced check as settled. No accounting entry — settlement recorded separately."""
        for check in self:
            check._check_state_transition('settled')
            check._create_operation('settle', to_state='settled')
            check.write({
                'state': 'settled',
                'settled_date': fields.Date.today(),
            })
            check.message_post(body=_('Bounce settled. Settlement payment recorded separately.'))
        return True

    def action_cancel(self):
        """Cancel a check and reverse ALL posted journal entries.

        Uses account.move._reverse_moves(cancel=True) — entries are NEVER deleted.
        Reversal moves are also linked to check.move_ids for a complete audit trail.
        """
        for check in self:
            check._check_state_transition('cancelled')
            posted_count = len(check.move_ids.filtered(lambda m: m.state == 'posted'))
            reversals = check._reverse_all_moves(
                reason=_('PDC Cancelled: %s', check.name),
            )
            check._create_operation(
                'cancel', to_state='cancelled',
                notes=_('%d journal entr(ies) reversed.', posted_count),
            )
            check.write({'state': 'cancelled'})
            check.message_post(body=_(
                'Check cancelled. %d journal entr(ies) reversed.',
                len(reversals),
            ))
        return True

    def action_print_check(self):
        """Mark the check as printed.

        This is a state-only operation — no journal entry.
        The actual print layout / report is produced by the Phase 5 wizard.
        """
        self.ensure_one()
        self._check_state_transition('printed')
        self._create_operation('print', to_state='printed')
        self.write({'state': 'printed'})
        self.message_post(body=_(
            'Check printed. Physical check number: %s.', self.check_number
        ))
        return True

    def action_deliver(self):
        """Deliver an issued check to the beneficiary.

        Journal entry:
          Dr PDC-Issued  /  Cr PDC-Issued-Delivered
        """
        for check in self:
            check._check_state_transition('delivered')
            check._validate_journal_accounts(
                check.journal_id,
                'pdc_issued_account_id',
                'pdc_issued_delivered_account_id',
            )

            issued_acc = check.journal_id.pdc_issued_account_id
            delivered_acc = check.journal_id.pdc_issued_delivered_account_id

            amount_co, amount_fx, fx_cur = check._get_amounts(date=fields.Date.today())
            cur_id = fx_cur.id if fx_cur else False
            label = _('PDC Delivered: %s', check.check_number)
            lines = [
                check._build_move_line(
                    issued_acc.id, check.partner_id.id,
                    amount_co, 0.0, label,
                    cur_id, amount_fx,
                ),
                check._build_move_line(
                    delivered_acc.id, check.partner_id.id,
                    0.0, amount_co, label,
                    cur_id, -amount_fx if amount_fx is not None else None,
                ),
            ]
            move = check._post_move(
                check.journal_id.id,
                _('%s - Delivered to Beneficiary', check.name),
                lines,
            )
            check._create_operation('deliver', to_state='delivered', move_id=move)
            check.write({'state': 'delivered'})
            check.message_post(body=_('Check delivered to beneficiary.'))
        return True

    def action_pay(self):
        """Record final payment of a delivered issued check by the bank.

        Journal entry:
          Dr PDC-Issued-Delivered  /  Cr Bank
        """
        for check in self:
            check._check_state_transition('paid')
            check._validate_journal_accounts(
                check.journal_id, 'pdc_issued_delivered_account_id',
            )
            if not check.journal_id.default_account_id:
                raise UserError(_(
                    'Journal "%s" has no default bank account set.',
                    check.journal_id.name,
                ))

            delivered_acc = check.journal_id.pdc_issued_delivered_account_id
            bank_acc = check.journal_id.default_account_id

            amount_co, amount_fx, fx_cur = check._get_amounts(date=fields.Date.today())
            cur_id = fx_cur.id if fx_cur else False
            label = _('PDC Paid: %s', check.check_number)
            lines = [
                check._build_move_line(
                    delivered_acc.id, check.partner_id.id,
                    amount_co, 0.0, label,
                    cur_id, amount_fx,
                ),
                check._build_move_line(
                    bank_acc.id, check.partner_id.id,
                    0.0, amount_co, label,
                    cur_id, -amount_fx if amount_fx is not None else None,
                ),
            ]
            move = check._post_move(
                check.journal_id.id,
                _('%s - Paid by Bank', check.name),
                lines,
            )
            check._create_operation('pay', to_state='paid', move_id=move)
            check.write({'state': 'paid'})
            check.message_post(body=_('Check marked as paid by bank.'))
        return True

    def action_return_guarantee(self):
        """Return a guarantee check to the issuer — state change only, no accounting entry."""
        for check in self:
            check._check_state_transition('returned')
            check._create_operation('return_guarantee', to_state='returned')
            check.write({'state': 'returned'})
            check.message_post(body=_('Guarantee check returned — no accounting impact.'))
        return True

    def action_activate_guarantee(self):
        """Convert a guarantee check into a regular received/issued check.

        This is a type-conversion, not a state transition:
          - check_type changes from guarantee_* to received/issued
          - state stays at 'registered' (the normal starting point for accounting)
          - was_guarantee is set to True for historical reference
          - Opening journal entry is created (same as action_register for received/issued)
        """
        for check in self:
            check._check_guarantee_activate()
            new_type = 'received' if check.check_type == 'guarantee_received' else 'issued'

            # Record the operation BEFORE changing type, so from_state is accurate.
            check._create_operation(
                'activate_guarantee',
                to_state='registered',
                notes=_('Guarantee converted to %s check.', new_type),
            )

            # check_type is in _PROTECTED_FIELDS but current state is 'registered'
            # (not terminal), so the write override allows this change.
            check.write({
                'check_type': new_type,
                'was_guarantee': True,
                'state': 'registered',  # already registered, but explicit
            })

            # Now check_type is 'received'/'issued' — create the opening journal entry.
            # _post_move() (called inside _create_registration_move) already links the
            # move to check.move_ids, so no additional write is needed here.
            check._create_registration_move()

            check.message_post(body=_(
                'Guarantee check activated and converted to a regular %(type)s check. '
                'Opening journal entry created.',
                type=dict(self._fields['check_type'].selection).get(new_type),
            ))
        return True

    # ── Smart button actions ──────────────────────────────────────────────────

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.move_ids.ids)],
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
        }

    def action_view_operations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Operations'),
            'res_model': 'pdc.check.operation',
            'view_mode': 'list,form',
            'domain': [('check_id', '=', self.id)],
        }

    # =========================================================================
    # HELPER / INTERNAL METHODS
    # =========================================================================

    # ── Accounting helpers (Phase 3) ──────────────────────────────────────────

    def _get_amounts(self, date=None):
        """Return (company_amount, foreign_amount, check_currency) for multi-currency.

        Same currency:    returns (self.amount, None, None)
        Foreign currency: returns (converted_to_company, self.amount, self.currency_id)

        :param date: The economic date to use for FX rate lookup.  Callers must
            pass the date that is appropriate for the workflow step (issue_date,
            deposit_date, clear_date, bounce_date…) so that historical transactions
            use the rate that was active on the actual event date rather than
            today's rate.  Defaults to today if omitted.
        """
        self.ensure_one()
        company_currency = self.company_id.currency_id
        if self.currency_id == company_currency:
            return self.amount, None, None
        rate_date = date or fields.Date.today()
        amount_company = self.currency_id._convert(
            self.amount, company_currency, self.company_id, rate_date,
        )
        return amount_company, self.amount, self.currency_id

    def _build_move_line(self, account_id, partner_id, debit, credit, name,
                         currency_id=False, amount_currency=None):
        """Build a single account.move.line dict.

        :param currency_id:     int — set only when check currency ≠ company currency
        :param amount_currency: float — positive for debit lines, negative for credit lines
        """
        vals = {
            'name': name,
            'account_id': account_id,
            'partner_id': partner_id or False,
            'debit': debit,
            'credit': credit,
        }
        if currency_id and amount_currency is not None:
            vals['currency_id'] = currency_id
            vals['amount_currency'] = amount_currency
        return vals

    def _post_move(self, journal_id, ref, line_vals_tree, date=None):
        """Create, post, and link an account.move to this check.

        The move is always posted (action_post()) — never left in draft.
        The move is linked to self.move_ids for full audit traceability.

        :return: posted account.move record
        """
        self.ensure_one()
        move = self.env['account.move'].create({
            'journal_id': journal_id,
            'ref': ref,
            'date': date or fields.Date.today(),
            'line_ids': [(0, 0, lv) for lv in line_vals_tree],
            'company_id': self.company_id.id,
        })
        move.action_post()
        self.write({'move_ids': [(4, move.id)]})
        return move

    def _validate_journal_accounts(self, journal, *field_names):
        """Raise UserError if the journal is missing any required PDC account fields.

        :param journal:     account.journal record to validate
        :param field_names: field names on account.journal (e.g. 'pdc_received_account_id')
        """
        missing_labels = []
        for fname in field_names:
            if not journal[fname]:
                field_obj = self.env['account.journal']._fields.get(fname)
                label = field_obj.string if field_obj else fname
                missing_labels.append(label)
        if missing_labels:
            raise UserError(_(
                'Journal "%(j)s" is missing required PDC account(s): %(m)s.\n'
                'Configure them under: Accounting → Journals → %(j)s → PDC Configuration tab.',
                j=journal.name,
                m=', '.join(missing_labels),
            ))

    def _reverse_all_moves(self, reason=''):
        """Reverse every posted move linked to this check.

        Called exclusively by action_cancel(). Each reversal is also linked
        to check.move_ids so the full accounting history remains visible.
        Moves are NEVER deleted — only reversed with cancel=True.

        :param reason: reference string for the reversal moves
        :return: recordset of all created reversal account.move records
        """
        self.ensure_one()
        posted = self.move_ids.filtered(lambda m: m.state == 'posted')
        all_reversals = self.env['account.move']
        for move in posted:
            reversals = move._reverse_moves(
                default_values_list=[{
                    'date': fields.Date.today(),
                    'ref': reason or _('PDC Cancelled: %s', self.name),
                    'journal_id': move.journal_id.id,
                }],
                cancel=True,
            )
            all_reversals |= reversals
        if all_reversals:
            self.write({'move_ids': [(4, r.id) for r in all_reversals]})
        return all_reversals

    def _create_registration_move(self):
        """Create the opening journal entry for a received or issued check.

        Called by both action_register() and action_activate_guarantee().

        Received:  Dr PDC-Received  /  Cr Partner-Receivable
        Issued:    Dr Partner-Payable  /  Cr PDC-Issued
        Guarantee: No entry (off-balance sheet) — returns None

        :return: posted account.move record, or None for guarantee checks
        """
        self.ensure_one()
        if self.check_type == 'received':
            self._validate_journal_accounts(self.journal_id, 'pdc_received_account_id')
            pdc_acc = self.journal_id.pdc_received_account_id
            partner_acc = self.partner_id.property_account_receivable_id
            if not partner_acc:
                raise UserError(_(
                    'Partner "%s" has no Accounts Receivable configured.',
                    self.partner_id.name,
                ))
            amount_co, amount_fx, fx_cur = self._get_amounts(date=self.issue_date)
            cur_id = fx_cur.id if fx_cur else False
            label = _('PDC Check Received: %s', self.check_number)
            lines = [
                self._build_move_line(
                    pdc_acc.id, self.partner_id.id,
                    amount_co, 0.0, label,
                    cur_id, amount_fx,
                ),
                self._build_move_line(
                    partner_acc.id, self.partner_id.id,
                    0.0, amount_co, label,
                    cur_id, -amount_fx if amount_fx is not None else None,
                ),
            ]
            return self._post_move(
                self.journal_id.id,
                _('%s - Registration', self.name),
                lines,
                date=self.issue_date,
            )

        if self.check_type == 'issued':
            self._validate_journal_accounts(self.journal_id, 'pdc_issued_account_id')
            pdc_acc = self.journal_id.pdc_issued_account_id
            partner_acc = self.partner_id.property_account_payable_id
            if not partner_acc:
                raise UserError(_(
                    'Partner "%s" has no Accounts Payable configured.',
                    self.partner_id.name,
                ))
            amount_co, amount_fx, fx_cur = self._get_amounts(date=self.issue_date)
            cur_id = fx_cur.id if fx_cur else False
            label = _('PDC Check Issued: %s', self.check_number)
            lines = [
                self._build_move_line(
                    partner_acc.id, self.partner_id.id,
                    amount_co, 0.0, label,
                    cur_id, amount_fx,
                ),
                self._build_move_line(
                    pdc_acc.id, self.partner_id.id,
                    0.0, amount_co, label,
                    cur_id, -amount_fx if amount_fx is not None else None,
                ),
            ]
            return self._post_move(
                self.journal_id.id,
                _('%s - Registration', self.name),
                lines,
                date=self.issue_date,
            )

        # Guarantee checks: off-balance sheet — no journal entry
        return None

    def _resolve_bounce_charges_accounts(self, is_received=True):
        """Return (charges_account, bank_account) for a bounce charges entry.

        Respects check.bounce_charges_source:
          'deposit_journal'  → use pdc_bounce_charges_account_id from deposit_journal_id
          'original_journal' → use pdc_bounce_charges_account_id from journal_id
          'custom_account'   → use bounce_charges_account_id (user-specified)

        The bank_account is the account credited to record the bank's deduction:
          deposit_journal → deposit_journal.default_account_id
          original_journal → journal_id.default_account_id
          custom_account → deposit_journal (received) or journal (issued) default

        :param is_received: True for received bounces, False for issued
        :return: tuple (charges_account, bank_account) — account.account records
        :raises UserError: if source is misconfigured or account is missing when charges > 0
        """
        self.ensure_one()
        source = self.bounce_charges_source or 'deposit_journal'
        charges = self.bounce_charges or 0.0

        if source == 'deposit_journal':
            if not self.deposit_journal_id:
                raise UserError(_(
                    'Check "%s" has no Deposit Bank set. '
                    'Cannot use "Deposit Bank Journal" as bounce charges source.',
                    self.name,
                ))
            charges_acc = self.deposit_journal_id.pdc_bounce_charges_account_id
            bank_acc = self.deposit_journal_id.default_account_id
            src_journal_name = self.deposit_journal_id.name

        elif source == 'original_journal':
            charges_acc = self.journal_id.pdc_bounce_charges_account_id
            bank_acc = self.journal_id.default_account_id
            src_journal_name = self.journal_id.name

        else:  # custom_account
            if not self.bounce_charges_account_id:
                raise UserError(_(
                    'Please specify a "Custom Charges Account" on check "%s" '
                    'before recording the bounce.',
                    self.name,
                ))
            charges_acc = self.bounce_charges_account_id
            # For the bank Cr line: prefer deposit journal (received) or own journal (issued)
            bank_acc = (
                (self.deposit_journal_id.default_account_id
                 if is_received and self.deposit_journal_id else False)
                or self.journal_id.default_account_id
            )
            src_journal_name = self.journal_id.name

        # Validate: if there are charges, an account must exist
        if charges and not charges_acc:
            source_label = dict(self._fields['bounce_charges_source'].selection).get(
                source, source
            )
            raise UserError(_(
                'No bounce charges account configured for source "%(source)s".\n'
                'Please either:\n'
                '1. Configure "PDC Bounce Charges Account" on journal "%(journal)s", or\n'
                '2. Change "Bounce Charges Source" to "Custom Account" and select an account.',
                source=source_label,
                journal=src_journal_name,
            ))
        if charges and not bank_acc:
            raise UserError(_(
                'Journal "%s" has no default bank account set. '
                'Cannot post charges bank credit line.',
                src_journal_name,
            ))

        return charges_acc, bank_acc

    # ── State / validation helpers ────────────────────────────────────────────

    def _check_guarantee_activate(self):
        """Validate that this check can be activated from its guarantee state."""
        self.ensure_one()
        if self.check_type not in ('guarantee_received', 'guarantee_issued'):
            raise UserError(_(
                'Only guarantee checks can be activated. '
                'Check "%s" is of type "%s".',
                self.name, self.check_type,
            ))
        if self.state != 'registered':
            raise UserError(_(
                'Check "%s" must be in Registered state to activate. '
                'Current state: %s.',
                self.name, self.state,
            ))

    def _check_state_transition(self, target_state):
        """Validate that transitioning to target_state is allowed for this check."""
        self.ensure_one()
        allowed = _VALID_TRANSITIONS.get(self.check_type, {}).get(self.state, [])
        if target_state not in allowed:
            raise UserError(_(
                'Cannot move check "%(name)s" from state "%(from)s" to "%(to)s". '
                'Allowed next states: %(allowed)s.',
                name=self.name,
                **{'from': self.state},
                to=target_state,
                allowed=', '.join(allowed) if allowed else _('none (terminal state)'),
            ))

    def _create_operation(self, operation_type, to_state=None, move_id=None,
                          amount=None, journal_id=None, notes=None):
        """Create an immutable audit log entry for a state change or operation."""
        self.ensure_one()
        return self.env['pdc.check.operation'].create({
            'check_id': self.id,
            'operation_type': operation_type,
            'from_state': self.state,
            'to_state': to_state or self.state,
            'user_id': self.env.uid,
            'move_id': move_id.id if move_id else False,
            'amount': amount if amount is not None else self.amount,
            'journal_id': (journal_id or self.journal_id).id,
            'notes': notes,
            'company_id': self.company_id.id,
        })

    # ── Amount / display helpers ──────────────────────────────────────────────

    # Arabic currency names — ISO code → (main unit name, sub-unit name, sub-unit per main)
    # Format: (main_ar, sub_ar, sub_per_main)
    # sub_per_main: 100 for most currencies (piastres/halalas/fils); 1000 for KWD/BHD/JOD
    _ARABIC_CURRENCY_INFO = {
        'EGP': ('جنيه مصري',       'قرشاً',           100),
        'SAR': ('ريال سعودي',       'هللة',             100),
        'AED': ('درهم إماراتي',     'فلساً',            100),
        'KWD': ('دينار كويتي',      'فلساً',            1000),
        'BHD': ('دينار بحريني',     'فلساً',            1000),
        'QAR': ('ريال قطري',        'درهماً',           100),
        'OMR': ('ريال عُماني',      'بيسة',             1000),
        'JOD': ('دينار أردني',      'فلساً',            1000),
        'USD': ('دولار أمريكي',     'سنتاً',            100),
        'EUR': ('يورو',             'سنتاً',            100),
        'GBP': ('جنيه إسترليني',   'بنساً',            100),
        'LYD': ('دينار ليبي',       'درهماً',           1000),
        'TND': ('دينار تونسي',      'مليماً',           1000),
        'DZD': ('دينار جزائري',     'سنتيماً',          100),
        'MAD': ('درهم مغربي',       'سنتيماً',          100),
        'SDG': ('جنيه سوداني',      'قرشاً',            100),
        'IQD': ('دينار عراقي',      'فلساً',            1000),
        'SYP': ('ليرة سورية',       'قرشاً',            100),
        'LBP': ('ليرة لبنانية',     'قرشاً',            100),
        'YER': ('ريال يمني',        'فلساً',            100),
    }

    def _get_amount_in_words(self, language='en'):
        """Convert check amount to words in the specified language.

        Arabic output example: "خمسة آلاف ريال سعودي لا غير"
        English output example: "Five Thousand Saudi Arabian Riyal Only"
        """
        self.ensure_one()
        if not self.amount or not self.currency_id:
            return ''
        try:
            from num2words import num2words

            code = (self.currency_id.name or '').upper()
            integer_part = int(self.amount)

            if language == 'ar':
                ar_info = self._ARABIC_CURRENCY_INFO.get(code)
                cur_ar = ar_info[0] if ar_info else code
                sub_ar = ar_info[1] if ar_info else 'قرشاً'
                sub_per_main = ar_info[2] if ar_info else 100

                decimal_part = round((self.amount - integer_part) * sub_per_main)

                words = num2words(integer_part, lang='ar')
                result = f'{words} {cur_ar}'
                if decimal_part:
                    dec_words = num2words(decimal_part, lang='ar')
                    result += f' و{dec_words} {sub_ar}'
                return result + ' لا غير'
            else:
                decimal_part = round((self.amount - integer_part) * 100)
                currency_name = self.currency_id.name

                words = num2words(integer_part, lang='en').title()
                result = f'{words} {currency_name}'
                if decimal_part:
                    dec_words = num2words(decimal_part, lang='en').title()
                    result += f' and {dec_words} Cents'
                return result + ' Only'

        except ImportError:
            _logger.warning(
                'num2words package not installed. Amount-in-words unavailable. '
                'Install with: pip install num2words'
            )
            return f'{self.amount:.2f} {self.currency_id.name}'
        except Exception as e:
            _logger.error('Error converting amount to words: %s', e)
            return f'{self.amount:.2f} {self.currency_id.name}'

    def _send_due_reminder(self, days_ahead):
        """Send the configured due-date reminder email for this check."""
        self.ensure_one()
        template = self.env.ref(
            'pdc_management_v19.mail_template_pdc_due_soon',
            raise_if_not_found=False,
        )
        if not template:
            _logger.warning(
                'PDC due reminder skipped for %s: mail_template_pdc_due_soon not found.',
                self.name,
            )
            return False
        template.with_context(days_to_due=days_ahead).send_mail(
            self.id,
            force_send=False,
            raise_exception=False,
        )
        _logger.info(
            'PDC due reminder queued: check %s due in %d day(s)',
            self.name,
            days_ahead,
        )
        return True

    @staticmethod
    def _to_hijri(date):
        """Convert a Gregorian date to Hijri string.

        Returns an empty string when:
        - ``date`` is falsy
        - ``hijri_converter`` is not installed (``HIJRI_AVAILABLE = False``)
        - any conversion error occurs (e.g. date out of Hijri calendar range)
        """
        if not date or not HIJRI_AVAILABLE:
            return ''
        try:
            h = _hijri_convert.Gregorian(date.year, date.month, date.day).to_hijri()
            return f'{h.day:02d}/{h.month:02d}/{h.year}'
        except Exception:
            return ''
