# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date


class HrPettyCash(models.Model):
    _name = 'hr.petty.cash'
    _description = 'Employee Petty Cash Custody | عهدة موظف'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']
    _order = 'requested_date desc, id desc'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    custody_type = fields.Selection(
        [('temporary', 'Temporary / مؤقتة'), ('permanent', 'Permanent / دائمة')],
        string='Custody Type',
        required=True,
        default='temporary',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
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

    # ── Employee ───────────────────────────────────────────────────────────────
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee / الموظف',
        required=True,
        tracking=True,
    )
    job_title = fields.Char(related='employee_id.job_title', store=True)
    department_id = fields.Many2one(
        'hr.department',
        related='employee_id.department_id',
        store=True,
        string='Department / القسم',
    )
    manager_id = fields.Many2one(
        'hr.employee',
        related='employee_id.parent_id',
        store=True,
        string='Direct Manager',
    )

    # ── Fund ───────────────────────────────────────────────────────────────────
    petty_fund_id = fields.Many2one(
        'petty.cash.fund',
        string='Petty Cash Fund / الصندوق',
        required=True,
        domain="[('state', '=', 'active'), ('company_id', '=', company_id)]",
        tracking=True,
    )

    # ── Amounts ────────────────────────────────────────────────────────────────
    requested_amount = fields.Monetary(
        string='Requested Amount / المبلغ المطلوب',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    approved_amount = fields.Monetary(
        string='Approved Amount / المبلغ المعتمد',
        currency_field='currency_id',
        tracking=True,
    )
    paid_amount = fields.Monetary(
        string='Paid Amount / المبلغ المصروف',
        currency_field='currency_id',
        tracking=True,
    )
    # Permanent custody specific
    permanent_amount = fields.Monetary(
        string='Permanent Float Amount / المبلغ الثابت',
        currency_field='currency_id',
        tracking=True,
    )
    replenishment_threshold = fields.Monetary(
        string='Replenishment Threshold',
        currency_field='currency_id',
    )

    # ── Reason & Dates ─────────────────────────────────────────────────────────
    reason_en = fields.Char(string='Reason (English)', tracking=True)
    reason_ar = fields.Char(string='السبب (عربي)', tracking=True)
    requested_date = fields.Date(
        string='Request Date',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    expected_return_date = fields.Date(string='Expected Return Date', tracking=True)
    actual_return_date = fields.Date(string='Actual Return Date', tracking=True)

    # ── State ──────────────────────────────────────────────────────────────────
    state = fields.Selection(
        [
            ('draft', 'Draft / مسودة'),
            ('waiting_approval', 'Waiting Approval / في انتظار الموافقة'),
            ('approved', 'Approved / معتمدة'),
            ('paid', 'Paid / مصروفة'),
            ('settlement_in_progress', 'Settlement In Progress / جاري التسوية'),
            ('settled', 'Settled / مسوّاة'),
            ('returned', 'Returned / مردودة'),
            ('closed', 'Closed / مغلقة'),
            ('refused', 'Refused / مرفوضة'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    refuse_reason = fields.Text(string='Refuse Reason', tracking=True)

    # ── Accounting ─────────────────────────────────────────────────────────────
    move_id = fields.Many2one(
        'account.move',
        string='Disbursement Journal Entry',
        copy=False,
        readonly=True,
    )


    # ── Settlement ─────────────────────────────────────────────────────────────
    settlement_ids = fields.One2many(
        'petty.cash.settlement',
        'custody_id',
        string='Settlements',
    )
    settlement_count = fields.Integer(compute='_compute_settlement_count')

    # ── Replenishment (permanent) ───────────────────────────────────────────────
    replenishment_ids = fields.One2many(
        'petty.cash.fund.transfer',
        'custody_id',
        string='Replenishments',
    )

    # ── Misc ───────────────────────────────────────────────────────────────────
    notes = fields.Html(string='Notes / ملاحظات')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Attachments / المرفقات',
    )
    is_overdue = fields.Boolean(compute='_compute_is_overdue', store=False)

    # ── Computed ───────────────────────────────────────────────────────────────
    @api.depends('settlement_ids')
    def _compute_settlement_count(self):
        for rec in self:
            rec.settlement_count = len(rec.settlement_ids)

    def _compute_is_overdue(self):
        today = date.today()
        for rec in self:
            rec.is_overdue = (
                rec.state == 'paid'
                and rec.expected_return_date
                and rec.expected_return_date < today
            )

    # ── ORM ────────────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.petty.cash') or _('New')
        return super().create(vals_list)

    # ── State Machine Actions ──────────────────────────────────────────────────
    def action_submit(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft custodies can be submitted.'))
        if not self.requested_amount or self.requested_amount <= 0:
            raise UserError(_('Please enter a valid requested amount.'))
        self.write({'state': 'waiting_approval'})
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('Custody Request Pending Approval'),
            user_id=self.manager_id.user_id.id or self.env.user.id,
        )

    def action_approve(self):
        self.ensure_one()
        if self.state != 'waiting_approval':
            raise UserError(_('Only custodies waiting approval can be approved.'))
        if not self.approved_amount:
            self.approved_amount = self.requested_amount
        self.write({'state': 'approved'})
        # Send approval email
        template = self.env.ref(
            'petty_cash_management.email_template_custody_approved', raise_if_not_found=False
        )
        if template:
            template.send_mail(self.id, force_send=True)

    def action_refuse(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Refuse Reason'),
            'res_model': 'petty.cash.refuse.wizard',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_custody_id': self.id},
        }

    def action_pay(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved custodies can be paid.'))
        if not self.petty_fund_id.account_id:
            raise UserError(_('Petty cash fund has no account configured.'))

        config = self.env['petty.cash.config.settings']._get_values()
        custody_account = config.get('custody_account_id')
        if not custody_account:
            raise UserError(_('Employee Custody Account is not configured in Petty Cash Settings.'))

        amount = self.approved_amount or self.requested_amount

        # Warn or block if balance insufficient
        self.petty_fund_id._check_balance_warning(amount)

        move_vals = {
            'journal_id': self.petty_fund_id.journal_id.id,
            'date': fields.Date.today(),
            'ref': self.name,
            'company_id': self.company_id.id,
            'line_ids': [
                (0, 0, {
                    'name': _('Custody Disbursement: %(name)s', name=self.name),
                    'account_id': custody_account,
                    'debit': amount,
                    'credit': 0.0,
                    'partner_id': self.employee_id.work_contact_id.id if self.employee_id.work_contact_id else False,
                    # Odoo 17+/19: analytic_distribution replaces deprecated analytic_account_id
                    'analytic_distribution': self.analytic_distribution if self.analytic_distribution else {},
                }),
                (0, 0, {
                    'name': _('Custody Disbursement: %(name)s', name=self.name),
                    'account_id': self.petty_fund_id.account_id.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.write({
            'state': 'paid',
            'paid_amount': amount,
            'move_id': move.id,
        })

    def action_create_settlement(self):
        self.ensure_one()
        if self.state != 'paid':
            raise UserError(_('Can only create settlement for paid custodies.'))
        settlement = self.env['petty.cash.settlement'].create({
            'custody_id': self.id,
            'company_id': self.company_id.id,
        })
        self.write({'state': 'settlement_in_progress'})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement'),
            'res_model': 'petty.cash.settlement',
            'res_id': settlement.id,
            'views': [(False, 'form')],
            'view_mode': 'form',
        }

    def action_return_amount(self):
        self.ensure_one()
        if self.state not in ('paid', 'settlement_in_progress'):
            raise UserError(_('Can only return amount for paid custodies.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return Amount'),
            'res_model': 'petty.cash.return.wizard',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_custody_id': self.id},
        }

    def action_close(self):
        self.ensure_one()
        if self.state not in ('settled', 'returned'):
            raise UserError(_('Can only close settled or returned custodies.'))
        self.write({'state': 'closed'})

    def action_reset_to_draft(self):
        self.ensure_one()
        if self.state != 'refused':
            raise UserError(_('Only refused custodies can be reset to draft.'))
        self.write({'state': 'draft'})

    def action_view_settlements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlements'),
            'res_model': 'petty.cash.settlement',
            'views': [(False, 'list'), (False, 'form')],
            'view_mode': 'list,form',
            'domain': [('custody_id', '=', self.id)],
            'context': {'default_custody_id': self.id},
        }

    def action_view_journal_entry(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'views': [(False, 'form')],
            'view_mode': 'form',
        }

    # ── Cron Methods ───────────────────────────────────────────────────────────
    @api.model
    def _cron_check_overdue_custodies(self):
        today = date.today()
        overdue = self.search([
            ('state', '=', 'paid'),
            ('expected_return_date', '<', today),
        ])
        template = self.env.ref(
            'petty_cash_management.email_template_custody_overdue', raise_if_not_found=False
        )
        for custody in overdue:
            if template:
                template.send_mail(custody.id, force_send=True)
            # Post internal note
            custody.message_post(
                body=_('⚠️ This custody is overdue. Expected return: %s') % custody.expected_return_date,
                subtype_xmlid='mail.mt_note',
            )
