# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PettyCashConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Accounts ───────────────────────────────────────────────────────────────
    petty_cash_account_id = fields.Many2one(
        'account.account',
        string='Default Petty Cash Account',
        config_parameter='petty_cash.default_petty_cash_account_id',
        domain="[('account_type', 'like', 'asset')]",
    )
    custody_account_id = fields.Many2one(
        'account.account',
        string='Employee Custody Account',
        config_parameter='petty_cash.default_custody_account_id',
        domain="[('account_type', 'like', 'asset')]",
    )
    petty_journal_id = fields.Many2one(
        'account.journal',
        string='Default Petty Cash Journal',
        config_parameter='petty_cash.default_petty_journal_id',
        domain="[('type', 'in', ['cash', 'bank'])]",
    )

    # ── Approval ───────────────────────────────────────────────────────────────
    approval_mode = fields.Selection(
        [('single', 'Single Approval (Manager)'), ('double', 'Double Approval (Manager + Accountant)')],
        string='Approval Mode',
        default='single',
        config_parameter='petty_cash.approval_mode',
    )

    # ── Validation Rules ───────────────────────────────────────────────────────
    require_settlement_receipt = fields.Boolean(
        string='Require Receipt for Settlement',
        config_parameter='petty_cash.require_settlement_receipt',
        default=True,
    )
    max_days_without_settlement = fields.Integer(
        string='Max Days Without Settlement',
        config_parameter='petty_cash.max_days_without_settlement',
        default=30,
        help='Alert after this many days if custody is unpaid/unsettled.',
    )
    allow_exceed_fund_balance = fields.Boolean(
        string='Allow Payments Exceeding Fund Balance (warn only)',
        config_parameter='petty_cash.allow_exceed_fund_balance',
        default=True,
    )
    auto_replenishment_enabled = fields.Boolean(
        string='Enable Auto Replenishment Alerts',
        config_parameter='petty_cash.auto_replenishment_enabled',
        default=True,
    )

    @api.model
    def _get_values(self):
        """Helper to get petty cash config as a dict."""
        IrParam = self.env['ir.config_parameter'].sudo()

        def get_m2o(param):
            val = IrParam.get_param(param)
            try:
                return int(val) if val else False
            except (ValueError, TypeError):
                return False

        return {
            'custody_account_id': get_m2o('petty_cash.default_custody_account_id'),
            'petty_journal_id': get_m2o('petty_cash.default_petty_journal_id'),
            'approval_mode': IrParam.get_param('petty_cash.approval_mode', 'single'),
            'require_settlement_receipt': IrParam.get_param(
                'petty_cash.require_settlement_receipt', 'True') == 'True',
            'max_days_without_settlement': int(
                IrParam.get_param('petty_cash.max_days_without_settlement', '30')),
            'allow_exceed_fund_balance': IrParam.get_param(
                'petty_cash.allow_exceed_fund_balance', 'True') == 'True',
        }
