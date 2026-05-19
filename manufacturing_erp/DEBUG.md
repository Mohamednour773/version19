# 🔧 Debug Guide | دليل حل المشاكل

## كيفية الحصول على رسالة الخطأ بدقة | Get the Exact Error

### الطريقة الأولى: Command Line (الأفضل)

```bash
# توقف عن خدمة Odoo
sudo systemctl stop odoo

# شغّله يدوياً مع verbose log
sudo -u odoo /opt/odoo/odoo-bin \
    -d YOUR_DATABASE_NAME \
    -i factory_base \
    --stop-after-init \
    --log-level=info \
    --addons-path=/opt/odoo/addons,/opt/odoo/custom-addons 2>&1 | tee /tmp/install.log

# شوف آخر 100 سطر
tail -100 /tmp/install.log
```

### الطريقة الثانية: Docker

```bash
docker-compose logs --tail=200 odoo
# أو
docker logs YOUR_ODOO_CONTAINER_NAME --tail 200
```

### الطريقة الثالثة: Odoo Logs File

```bash
sudo tail -200 /var/log/odoo/odoo-server.log
```

---

## ⚠️ ابعتلي اللوج

ابعتلي آخر **50 سطر** من اللوج وأنا هحدد المشكلة بالظبط. غالباً الـ error بيكون في شكل:

```
ERROR ... odoo.modules.loading: Failed to initialize database ...
... (traceback) ...
ParseError: ... (ده اللي مهم!)
```

---

## 🐛 المشاكل المعتادة وحلولها

### 1. `KeyError: 'External ID not found: ...'`
**السبب:** dependency module مش متاح أو الـ ID مش موجود.  
**الحل:** اتأكد إن كل modules المطلوبة (project, sale_management, account, mrp, etc.) متثبتة.

### 2. `Field "type" doesn't exist in model "product.product"`
**السبب:** في Odoo 19 الـ product structure تغيرت.  
**الحل:** أنا شيلت كل الـ domains اللي بتستخدم `type` في النسخة الجديدة.

### 3. `View "project.edit_project" not found`
**السبب:** الـ project module ما تثبتش.  
**الحل:** `./odoo-bin -d db -i project`

### 4. `Module 'maintenance' not found`
**السبب:** Maintenance module مش متاح في الإصدار ده.  
**الحل:** اتشال من dependencies في النسخة المُحدّثة.

### 5. `IntegrityError: violates check constraint`
**السبب:** بيانات قديمة في الـ database.  
**الحل:** اعمل database جديدة فاضية للتجربة.

---

## 🎯 خطوات التثبيت الموصى بها

```bash
# 1. اعمل database جديدة فاضية
createdb -U odoo factory_test_db

# 2. ثبّت بـ verbose mode موديول واحد بس الأول
sudo -u odoo /opt/odoo/odoo-bin \
    -d factory_test_db \
    -i base,project,sale_management,account,stock,hr \
    --stop-after-init \
    --without-demo=all

# 3. لو نجح، ثبّت factory_base
sudo -u odoo /opt/odoo/odoo-bin \
    -d factory_test_db \
    -i factory_base \
    --stop-after-init

# 4. ثبّت الباقي مع بعض
sudo -u odoo /opt/odoo/odoo-bin \
    -d factory_test_db \
    -i factory_molds,factory_mix_design,factory_project,factory_production,factory_site_installation,factory_costing,factory_reports \
    --stop-after-init

# 5. شغّل Odoo عادي
sudo systemctl start odoo
```

---

## 📋 Pre-Install Checklist

قبل ما تثبّت اتأكد إن:

- [ ] Odoo 19 متثبت ومشغّل بنجاح
- [ ] الموديولات الأساسية متاحة: `project`, `sale_management`, `account`, `stock`, `hr`
- [ ] User عنده صلاحيات Administrator
- [ ] الـ database فاضية أو على الأقل ما فيهاش versions قديمة من نفس الموديولات
- [ ] الـ addons-path في odoo.conf بيشمل الفولدر اللي حاطط فيه الموديولات

---

## 🔄 لو احتجت تشيل الموديولات

```bash
# uninstall بالترتيب العكسي
sudo -u odoo /opt/odoo/odoo-bin \
    -d YOUR_DB \
    -u all \
    --stop-after-init
```

من واجهة Odoo: Apps → Show → Installed → اضغط Uninstall على كل موديول واحد واحد بدءاً من factory_reports.
