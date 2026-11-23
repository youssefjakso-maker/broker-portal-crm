# إعداد مكتب Broker Portal

## 1. التثبيت
- ثبّت Python 3.10+ (فعّل "Add python.exe to PATH").
- فك ضغط `Broker_Portal_Release_YYYYMMDD.zip` في `C:\BrokerPortal`.
- شغّل `run_office.bat` مرة (ينشئ `.venv` ويحمّل الحزم).

## 2. أول دخول
- افتح `http://<IP-المكتب>:5000`
- سجّل دخول `admin@local` / `Admin123!` (سيُطلب تغيير كلمة المرور).
- أنشئ حسابات السماسرة من "Data Management → Create broker account".

## 3. البيانات
- ارفع ملف Excel من "Data Management → Upload as Draft"، ثم "Publish".
- يمكن إضافة مشاريع/وحدات يدوياً.

## 4. الشبكة
- امنح الجهاز IP ثابتاً (Static IP).
- افتح منفذ 5000 في Windows Firewall لشبكة Private فقط:
  `netsh advfirewall firewall add rule name="BrokerPortal" dir=in action=allow protocol=tcp localport=5000 profile=private`
- لا تفتح المنفذ على الإنترنت. للوصول عن بعد استخدم VPN.

## 5. منع السليب
- إعدادات الطاقة: "Never sleep" عند التوصيل بالكهرباء.

## 6. تشغيل تلقائي عند الإقلاع
```
schtasks /create /tn "BrokerPortal" /tr "C:\BrokerPortal\run_office.bat" /sc onlogon /rl highest /f
```

## 7. نسخ احتياطي يومي
```
schtasks /create /tn "BrokerPortalBackup" /tr "C:\BrokerPortal\backup_portal.bat" /sc daily /st 02:00 /rl highest /f
```
- النسخ في `data\backups\` (آخر 30 نسخة).
- استرجاع: أوقف التطبيق، انسخ `broker_portal.db` من مجلد النسخة إلى `data\`، شغّل again.

## 8. تحديث النسخة
- أوقف التطبيق، استبدل app.py/templates/static/ والملفات (لا تمس `data\`)، شغّل `run_office.bat`.

## 9. إعادة تعيين كلمة مرور الأدمن (على الجهاز المستضيف)
```
.venv\Scripts\python.exe reset_admin_password.py
```

## 10. تنبيهات أمان
- لا تفتح المنفذ 5000 على الإنترنت.
- استخدم VPN للوصول عن بعد.
- احتفظ بنسخ احتياطية خارج الجهاز (USB/سحابة).
