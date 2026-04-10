# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ─── API Keys ────────────────────────────────────────────────
    smart_openai_api_key = fields.Char(
        string='OpenAI API Key',
        config_parameter='smart_task_hub_test.openai_api_key',
    )
    smart_anthropic_api_key = fields.Char(
        string='Anthropic (Claude) API Key',
        config_parameter='smart_task_hub_test.anthropic_api_key',
    )
    smart_claude_model = fields.Char(
        string='Claude Model',
        config_parameter='smart_task_hub_test.claude_model',
        default='claude-opus-4-5-20251001',
    )

    # ─── Behavior ────────────────────────────────────────────────
    smart_auto_analyze = fields.Boolean(
        string='Auto-Analyze on Create',
        config_parameter='smart_task_hub_test.auto_analyze',
        default=True,
    )
    smart_odoo_version = fields.Selection([
        ('Odoo 19', 'Odoo 19 (Saas)'),
        ('Odoo 18', 'Odoo 18'),
        ('Odoo 17', 'Odoo 17'),
        ('Odoo 16', 'Odoo 16'),
        ('Odoo 15', 'Odoo 15'),
        ('Odoo 14', 'Odoo 14'),
    ], string='Odoo Version',
        config_parameter='smart_task_hub_test.odoo_version',
        default='Odoo 19',
    )
    smart_openai_model = fields.Selection([
        ('o4-mini', 'o4-mini (Recommended — Deep Thinking)'),
        ('o3', 'o3 (Most Powerful)'),
        ('gpt-4o', 'GPT-4o (Fast)'),
        ('gpt-4o-mini', 'GPT-4o Mini (Budget)'),
    ], string='OpenAI Model',
        config_parameter='smart_task_hub_test.openai_model',
        default='o4-mini',
    )

    # ─── Default Assignments ────────────────────────────────────
    smart_default_functional_user = fields.Many2one(
        'res.users', string='Default Functional Consultant',
        compute='_compute_default_users', inverse='_inverse_functional_user',
    )
    smart_default_developer_user = fields.Many2one(
        'res.users', string='Default Developer',
        compute='_compute_default_users', inverse='_inverse_developer_user',
    )
    smart_default_support_user = fields.Many2one(
        'res.users', string='Default Support Agent',
        compute='_compute_default_users', inverse='_inverse_support_user',
    )

    def _compute_default_users(self):
        get = self.env['ir.config_parameter'].sudo().get_param
        for rec in self:
            try:
                rec.smart_default_functional_user = int(get('smart_task_hub_test.default_functional_user', 0)) or False
                rec.smart_default_developer_user  = int(get('smart_task_hub_test.default_developer_user', 0)) or False
                rec.smart_default_support_user    = int(get('smart_task_hub_test.default_support_user', 0)) or False
            except (ValueError, TypeError):
                rec.smart_default_functional_user = False
                rec.smart_default_developer_user  = False
                rec.smart_default_support_user    = False

    def _inverse_functional_user(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'smart_task_hub_test.default_functional_user',
            str(self.smart_default_functional_user.id or ''))

    def _inverse_developer_user(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'smart_task_hub_test.default_developer_user',
            str(self.smart_default_developer_user.id or ''))

    def _inverse_support_user(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'smart_task_hub_test.default_support_user',
            str(self.smart_default_support_user.id or ''))

    # ─── Voice & Vision Models ────────────────────────────────────
    smart_whisper_model = fields.Char(
        string='Whisper Model',
        config_parameter='smart_task_hub_test.whisper_model',
        default='whisper-1',
        help='OpenAI Whisper model for voice transcription. Default: whisper-1',
    )
    smart_whisper_language = fields.Char(
        string='Voice Language Code',
        config_parameter='smart_task_hub_test.whisper_language',
        default='ar',
        help='ISO language code for Whisper transcription (e.g. ar, en, fr). Leave empty for auto-detect.',
    )
    smart_vision_model = fields.Char(
        string='Vision Model (GPT-4V)',
        config_parameter='smart_task_hub_test.vision_model',
        default='gpt-4o',
        help='OpenAI model for screenshot analysis. Default: gpt-4o (supports vision)',
    )
