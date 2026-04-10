# -*- coding: utf-8 -*-
import re
from odoo import api, fields, models


class SmartKnowledgeBase(models.Model):
    _name        = 'smart.knowledge.base'
    _description = 'Smart Knowledge Base'
    _order       = 'usage_count desc, create_date desc'

    name        = fields.Char('Article Title', required=True)
    odoo_module = fields.Selection([
        ('accounting',    'Accounting'),    ('inventory',  'Inventory'),
        ('manufacturing', 'Manufacturing'), ('sales',      'Sales'),
        ('purchase',      'Purchase'),      ('hr',         'HR'),
        ('project',       'Project'),       ('ecommerce',  'eCommerce'),
        ('pos',           'POS'),           ('fleet',      'Fleet'),
        ('maintenance',   'Maintenance'),   ('quality',    'Quality'),
        ('other',         'Other'),
    ], string='Module')

    task_type = fields.Selection([
        ('bug','Bug'), ('config','Configuration'), ('customization','Customization'),
        ('training','Training'), ('consulting','Consulting'),
        ('gap_analysis','Gap Analysis'), ('integration','Integration'), ('upgrade','Upgrade'),
    ], string='Task Type')

    root_cause = fields.Selection([
        ('configuration','Configuration'), ('user_error','User Error'),
        ('workflow','Workflow'),           ('code_bug','Code Bug'),
        ('data_issue','Data Issue'),       ('integration','Integration'),
        ('requirements','Requirements'),
    ], string='Root Cause')

    solution_type = fields.Selection([
        ('config_change','Config Change'), ('process_fix','Process Fix'),
        ('custom_dev','Custom Dev'),       ('training','Training'),
        ('standard_odoo','Standard Odoo'), ('third_party','Third Party'),
    ], string='Solution Type')

    complexity   = fields.Selection([('easy','Easy'), ('medium','Medium'), ('hard','Hard')], 'Complexity')
    risk_level   = fields.Selection([('low','Low'), ('medium','Medium'), ('high','High'), ('critical','Critical')], 'Risk')
    priority_score = fields.Integer('Priority Score (0-100)', default=50)

    problem_description = fields.Text('Problem Description')
    root_cause_detail   = fields.Html('Root Cause Detail')
    solution_content    = fields.Html('Solution')
    prevention_notes    = fields.Html('Prevention & Best Practices')
    tags                = fields.Char('Tags', help='Comma-separated: avco, negative_stock, cogs...')

    source_task_id = fields.Many2one('smart.task', 'Source Task')
    usage_count    = fields.Integer('Times Referenced', default=0)
    is_published   = fields.Boolean('Published', default=True)

    # ── Similarity search ──────────────────────────────────────
    def find_similar(self, description, limit=5):
        """Return KB articles similar to the given description."""
        plain = re.sub('<[^<]+?>', '', description or '').lower()
        words = set(w for w in plain.split() if len(w) > 4)
        if not words:
            return self.browse()

        articles = self.search([('is_published', '=', True)])
        scored = []
        for art in articles:
            art_text = (
                (art.problem_description or '') + ' ' +
                re.sub('<[^<]+?>', '', art.root_cause_detail or '') + ' ' +
                (art.tags or '')
            ).lower()
            art_words = set(w for w in art_text.split() if len(w) > 4)
            if art_words:
                overlap = len(words & art_words) / max(len(words), len(art_words))
                if overlap > 0.25:
                    scored.append((overlap, art))

        scored.sort(key=lambda x: x[0], reverse=True)
        return self.browse([a.id for _, a in scored[:limit]])

    def action_increment_usage(self):
        self.usage_count += 1
