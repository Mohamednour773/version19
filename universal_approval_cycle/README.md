# Universal Approval Cycle — Odoo 19

## نظرة عامة

وحدة **Universal Approval Cycle** تتيح تعريف وتطبيق دورات موافقات متعددة المراحل على **أي نموذج (Model) موجود في Odoo 19**، دون الحاجة لتعديل النموذج الأصلي.

---

## الميزات

| الميزة | التفاصيل |
|---|---|
| دورات قابلة للتخصيص | أنشئ عدة دورات موافقات لأي نموذج |
| مراحل متعددة | ترتيب تسلسلي مع تحكم كامل في كل مرحلة |
| أنواع الموافقين | مستخدمون محددون / مجموعة / حقل ديناميكي |
| منطق الموافقة | موافق واحد يكفي أو الكل مطلوبون |
| تشغيل تلقائي | إطلاق الدورة عند إنشاء السجل بشروط قابلة للضبط |
| إشعارات | إيميل تلقائي للموافقين عند وصول طلب جديد |
| سجل مراجعة | تاريخ كامل لكل إجراء مع التعليقات |
| تحديث الحقول | تحديث حقل في السجل الأصلي عند الموافقة/الرفض |
| أمان متكامل | 3 مجموعات: User / Approver / Manager |

---

## طريقة الاستخدام

### 1. التثبيت
ضع المجلد في `addons/` وثبّت من `Apps`.

### 2. إنشاء دورة موافقة
**Approvals → Configuration → Approval Cycles → New**

```
الاسم: موافقة طلبات الشراء
النموذج المستهدف: Purchase Order
```

### 3. إضافة المراحل
في نفس النموذج، أضف المراحل:

| # | الاسم | النوع | الموافق |
|---|---|---|---|
| 1 | مدير القسم | مستخدم محدد | ahmed@company.com |
| 2 | المدير المالي | مجموعة | Finance / Manager |
| 3 | المدير العام | حقل ديناميكي | حقل `user_id` على السجل |

### 4. إطلاق طلب الموافقة من أي سجل

**الطريقة الأولى — عبر زر "Start Approval" (يتطلب إضافة Mixin)**

في نموذجك الخاص:
```python
class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'approval.mixin']
```

ثم في view الخاص بك:
```xml
<!-- Smart Button -->
<button name="action_view_approvals" type="object"
        class="oe_stat_button" icon="fa-check-circle">
    <field name="approval_count" widget="statinfo" string="Approvals"/>
</button>

<!-- Start Button -->
<button name="action_start_approval" type="object"
        string="Start Approval" class="btn-primary"
        invisible="approval_count > 0"/>
```

**الطريقة الثانية — من قائمة الموافقات مباشرة**

اذهب إلى **Approvals → Requests → New** واختر الدورة والسجل يدويًا.

**الطريقة الثالثة — تلقائي عند الإنشاء**

فعّل `Auto-trigger on Create` في تعريف الدورة.

---

## هيكل الملفات

```
universal_approval_cycle/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── approval_cycle.py      # تعريف دورة الموافقة
│   ├── approval_stage.py      # مراحل الدورة والموافقون
│   ├── approval_request.py    # طلب الموافقة (الحالة الفعلية)
│   ├── approval_log.py        # سجل العمليات (audit log)
│   └── approval_mixin.py      # Mixin للنماذج الخارجية
├── wizard/
│   ├── __init__.py
│   ├── approval_action_wizard.py         # Wizard الموافقة/الرفض
│   └── approval_action_wizard_views.xml
├── views/
│   ├── approval_cycle_views.xml
│   ├── approval_stage_views.xml
│   ├── approval_request_views.xml
│   ├── approval_log_views.xml
│   └── approval_menus.xml
├── security/
│   ├── approval_security.xml
│   └── ir.model.access.csv
├── data/
│   └── approval_mail_template.xml
└── static/description/
    └── icon.png
```

---

## نماذج البيانات

### `approval.cycle`
- `name`: اسم الدورة
- `model_id`: النموذج المستهدف
- `stage_ids`: المراحل
- `auto_trigger`: تشغيل تلقائي
- `trigger_domain`: شرط التشغيل (Domain)
- `approve_field_id / value`: تحديث حقل عند الموافقة

### `approval.stage`
- `cycle_id`: الدورة
- `sequence`: الترتيب
- `approval_type`: user / group / dynamic
- `require_all`: يلزم موافقة الجميع
- `allow_self_approval`: السماح بالموافقة الذاتية

### `approval.request`
- `cycle_id + res_id + model_name`: تحديد السجل
- `state`: draft → pending → approved/rejected
- `current_stage_id`: المرحلة الحالية
- `progress`: نسبة الإنجاز

### `approval.log`
- `action`: approve / reject / cancel
- `approver_id + date + comment`: تفاصيل الإجراء

---

## الصلاحيات

| المجموعة | الصلاحيات |
|---|---|
| Approval User | إنشاء طلبات + رؤية طلباته |
| Approval Approver | موافقة/رفض الطلبات المخصصة له |
| Approval Manager | إدارة كاملة + تكوين الدورات |
