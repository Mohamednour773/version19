# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PettyCashSettlement(models.Model):
    _name = 'petty.cash.settlement'
    _description = 'Petty Cash Settlement | تسوية عهدة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'settlement_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    custody_id = fields.Many2one(
        'hr.petty.cash',
        string='Custody Reference / العهدة',
        required=True,
        tracking=True,
        ondelete='restrict',
    )
    employee_id = fields.Many2one(
        related='custody_id.employee_id',
        store=True,
        string='Employee',
    )
    petty_fund_id = fields.Many2one(
        related='custody_id.petty_fund_id',
        store=True,
        string='Fund',
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    state = fields.Selection(
        [
            ('draft', 'Draft / مسودة'),
            ('submitted', 'Submitted / مقدمة'),
            ('under_review', 'Under Review / تحت المراجعة'),
            ('approved', 'Approved / معتمدة'),
            ('posted', 'Posted / مرحّلة'),
            ('closed', 'Closed / مغلقة'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )

    settlement_date = fields.Date(
        string='Settlement Date',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    settlement_line_ids = fields.One2many(
        'petty.cash.settlement.line',
        'settlement_id',
        string='Expense Lines',
    )

    # ── Amounts ────────────────────────────────────────────────────────────────
    total_requested = fields.Monetary(
        string='Amount Paid / المبلغ المصروف',
        related='custody_id.paid_amount',
        currency_field='currency_id',
        store=True,
    )
    total_spent = fields.Monetary(
        string='Total Expenses / إجمالي المصروفات',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    total_approved = fields.Monetary(
        string='Total Approved',
        currency_field='currency_id',
        tracking=True,
    )
    remaining_amount = fields.Monetary(
        string='Remaining (To Return) / المبلغ المتبقي',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    extra_amount = fields.Monetary(
        string='Extra Needed / مبلغ إضافي',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )

    reviewed_by = fields.Many2one('res.users', string='Reviewed By', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)

    move_id = fields.Many2one(
        'account.move',
        string='Settlement Journal Entry',
        readonly=True,
        copy=False,
    )
    notes = fields.Html(string='Notes / ملاحظات')

    # ── Computed ───────────────────────────────────────────────────────────────
    @api.depends('settlement_line_ids.total_amount', 'total_requested')
    def _compute_amounts(self):
        for rec in self:
            total_spent = sum(rec.settlement_line_ids.mapped('total_amount'))
            rec.total_spent = total_spent
            diff = rec.total_requested - total_spent
            rec.remaining_amount = max(diff, 0.0)
            rec.extra_amount = max(-diff, 0.0)

    # ── ORM ────────────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('petty.cash.settlement') or _('New')
        return super().create(vals_list)

    # ── State Actions ──────────────────────────────────────────────────────────
    def action_submit(self):
        self.ensure_one()
        if not self.settlement_line_ids:
            raise UserError(_('Please add at least one expense line before submitting.'))
        self.write({'state': 'submitted'})

    def action_review(self):
        self.ensure_one()
        self.write({'state': 'under_review', 'reviewed_by': self.env.user.id})

    def action_approve(self):
        self.ensure_one()
        if not self.total_approved:
            self.total_approved = self.total_spent
        self.write({'state': 'approved', 'approved_by': self.env.user.id})

    def action_post(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved settlements can be posted.'))
        if not self.settlement_line_ids:
            raise UserError(_('Cannot post settlement without expense lines.'))

        config = self.env['petty.cash.config.settings']._get_values()
        custody_account = config.get('custody_account_id')
        if not custody_account:
            raise UserError(_('Employee Custody Account is not configured.'))

        lines = []
        for line in self.settlement_line_ids:
            lines.append((0, 0, {
                'name': line.description or line.description_en or 'Expense',
                'account_id': line.expense_account_id.id,
                'debit': line.total_amount,
                'credit': 0.0,
                'date': line.expense_date,
                'analytic_account_id': line.analytic_account_id.id if line.analytic_account_id else False,
            }))

        # Credit: Employee Custody Account (total)
        lines.append((0, 0, {
            'name': _('Settlement: %(name)s', name=self.name),
            'account_id': custody_account,
            'debit': 0.0,
            'credit': self.total_spent,
            'partner_id': (
                self.employee_id.work_contact_id.id
                if self.employee_id.work_contact_id else False
            ),
        }))

        move = self.env['account.move'].create({
            'journal_id': self.petty_fund_id.journal_id.id,
            'date': self.settlement_date,
            'ref': self.name,
            'company_id': self.company_id.id,
            'line_ids': lines,
        })
        move.action_post()
        self.write({'state': 'posted', 'move_id': move.id})
        # Update custody state
        self.custody_id.write({
            'state': 'settled',
            'actual_return_date': fields.Date.today(),
        })
        # Email notification
        template = self.env.ref(
            'petty_cash_management.email_template_settlement_approved', raise_if_not_found=False
        )
        if template:
            template.send_mail(self.id, force_send=True)

    def action_close(self):
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_('Only posted settlements can be closed.'))
        self.write({'state': 'closed'})
        if self.custody_id.state == 'settled':
            self.custody_id.action_close()

    def action_view_journal_entry(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }
