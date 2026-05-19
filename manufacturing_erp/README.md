# Manufacturing ERP for Odoo 19
# نظام إدارة المصنع لـ Odoo 19

نظام ERP متكامل للمصانع القائمة على المشاريع (GRC / Precast / GRP / Concrete)
يدعم العربية والإنجليزية في كل الواجهات.

---

## 📦 الموديولات (8 موديولات)

| # | الموديول | الوظيفة |
|---|---------|---------|
| 1 | **factory_base** | الأساس: القطاعات + مراحل التصنيع + الإعدادات + الصلاحيات |
| 2 | **factory_molds** | إدارة القوالب: تكلفة، عمر افتراضي، استخدامات، إهلاك |
| 3 | **factory_mix_design** | الخلطات: وصفات، استهلاك نظري vs فعلي، تتبع الهالك |
| 4 | **factory_project** | المقايسة والتسعير: تحويل لمشروع + قطاعات + SO تلقائياً |
| 5 | **factory_production** | الإنتاج: أوامر بمراحل، استخدام قوالب، استهلاك خلطات |
| 6 | **factory_site_installation** | الموقع: أذون تحميل/توريد، التركيب، الإكسسوارات، التشطيب، المصاريف |
| 7 | **factory_costing** | تجميع التكلفة الفعلية + ربحية المشاريع + الفروقات |
| 8 | **factory_reports** | تقارير: ربحية، استخدام قوالب، تحليل هالك + PDF templates |

---

## 🚀 خطوات التثبيت

### 1. نسخ الموديولات
انسخ كل المجلدات الـ 8 إلى مجلد addons في Odoo:
```bash
cp -r factory_* /path/to/odoo/addons/custom/
```

### 2. تحديث قائمة Apps
```bash
./odoo-bin -d your_db -u base --addons-path=/path/to/odoo/addons,/path/to/odoo/addons/custom
```
أو من واجهة Odoo: **Apps → Update Apps List**

### 3. تثبيت Application الرئيسي
في Apps، ابحث عن:
- **Factory Base | الأساس للمصنع**

اضغط Install. ده هيركّب الأساس وبيظهر قائمة "Factory | المصنع".

### 4. تثبيت الموديولات الفرعية (بالترتيب)
- Factory Molds
- Factory Mix Design  
- Factory Project & Estimation
- Factory Production
- Factory Site Delivery & Installation
- Factory Project Costing
- Factory Reports

> **مهم:** الترتيب ده ضروري لأن كل موديول معتمد على اللي قبله.

أو نصبهم كلهم مرة واحدة من خلال سطر الأوامر:
```bash
./odoo-bin -d your_db -i factory_reports,factory_costing,factory_site_installation,factory_production,factory_project,factory_mix_design,factory_molds,factory_base
```
(Odoo بيحل dependencies تلقائياً)

---

## 🌐 إعداد اللغة العربية

1. اذهب لـ **Settings → Translations → Languages**
2. فعّل **Arabic / العربية**
3. اذهب لـ **Settings → Translations → Load a Translation**
4. اختر Arabic واضغط Load
5. من ملف المستخدم: غيّر اللغة لـ Arabic

كل الـ Labels في الموديولات مكتوبة بالعربي والإنجليزي معاً، فالواجهة هتبقى ثنائية اللغة تلقائياً.

---

## 🔐 مجموعات الصلاحيات

| المجموعة | الصلاحية |
|---------|---------|
| **Factory User \| مستخدم المصنع** | عرض وتعديل سجلات الإنتاج والخلطات |
| **Production Manager \| مدير الإنتاج** | إدارة أوامر الإنتاج واعتماد الخلطات |
| **Factory Manager \| مدير المصنع** | كل الصلاحيات + التسعير + التقارير |

---

## 📊 الـ Workflow الكامل

```
1. مقايسة (Estimation)
   ↓ Approve + Convert
2. مشروع (Project) + قطاعات (Sectors) + SO + Analytic Account
   ↓
3. اختيار خلطة (Mix) + قوالب (Molds) لكل قطاع
   ↓
4. أمر إنتاج (Production Order)
   - تخطيط المراحل (Plan Stages)
   - بدء الإنتاج (Start) → إنشاء consumption record تلقائي
   - تنفيذ كل مرحلة (Start/Done) + تسجيل الهالك
   - إنهاء (Done) → تسجيل usage للقوالب + ترحيل الاستهلاك
   ↓
5. إذن تحميل (Loading Permit) → تحميل (Loaded)
   ↓
6. إذن توريد (Delivery Permit) → تأكيد (Confirmed)
   ↓
7. أمر تركيب (Installation Order)
   - استهلاك إكسسوارات
   - استهلاك خامات تشطيب
   - عمالة + مصاريف يومية
   ↓
8. تحديث تلقائي للكميات في القطاع
   ↓
9. ربحية المشروع (Profitability Report)
   - مقارنة المتوقع vs الفعلي
   - تحليل الفروقات
```

---

## 🧪 بيانات الاختبار

النظام بيحمّل تلقائياً:
- **8 مراحل تصنيع** (تجهيز قالب، صب، فك، معالجة، تشطيب، تخزين، توريد، تركيب)
- **5 فئات قوالب** (لوحات، أعمدة، عناصر زخرفية، أقواس، كمرات)

---

## ⚙️ الإعدادات المهمة

من **Factory → Configuration → Settings**:
- ✅ **Auto-Create Analytic Account** — إنشاء حساب تحليلي تلقائياً
- ✅ **Track Production Waste** — تتبع الهالك
- 📊 **Mold Amortization Method** — طريقة إهلاك القالب (linear / by quantity / by time)
- 💰 **Default Waste Account** — حساب الهالك الافتراضي

---

## 🐛 استكشاف الأخطاء

### مشكلة: View لـ project مش بيتحمل
**السبب:** بعض الـ views بتعتمد على وجود `<sheet>` و `<notebook>` في الـ project form الأصلي.  
**الحل:** فعّل debug mode وافحص الـ inheritance.

### مشكلة: الحسابات التحليلية مش بتتسجل
**السبب:** لازم يكون فيه `account.analytic.plan` واحد على الأقل.  
**الحل:** اعمل واحد من **Accounting → Configuration → Analytic Plans**

### مشكلة: لا يمكن إنشاء مشروع من المقايسة
**السبب:** الـ user مش عنده صلاحية analytic.  
**الحل:** أضف للـ user مجموعة "Analytic Accounting".

---

## 📝 ملاحظات على التخصيص

- كل موديول مستقل ويمكن إيقافه/إلغاء تثبيته
- الـ Workflow كله مبني على state machines بتظهر في الـ Statusbar
- كل الموديلات بتورث من `mail.thread` فعندك chatter كامل وtracking
- الحسابات التحليلية بتربط كل حركة بمركز التكلفة الخاص بالمشروع

---

## 📞 الدعم

للاستفسارات أو الإضافات، راجع كود كل موديول — الكود موثّق بالعربي والإنجليزي.

**Version:** 19.0.1.0.0  
**Compatible with:** Odoo 19 Community / Enterprise
