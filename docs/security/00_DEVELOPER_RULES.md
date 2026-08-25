# قواعد المطور — صارمة (Security & Scale)

هذه القواعد **إلزامية**. مخالفتها = رفض الـ PR.

---

## 0) مبادئ عامة

1. **فصل الاهتمامات:** كل مرحلة أمان لها workflow وملف توثيق مستقل. لا تدمج `security.yml` مع `dast-zap.yml`.
2. **محركات رسمية فقط** للمسح (ZAP, Bandit, CodeQL, Trivy, Grype, …). ممنوع سكربت بديل يدّعي أنه "ماسح ثغرات".
3. **منطق المنتج منفصل عن المحركات:** IDOR / credits / ownership = كود + pytest، ليس بديل ZAP.
4. **Fail-closed:** أي شك في الهوية أو الملكية = 401/403/404، ليس 200 مع بيانات ناقصة.
5. **قابلية التوسع:** وحدة جديدة = مجلد/حزمة واضحة + اختبارات حدودية، بدون الاعتماد على "معرفة ضمنية" في ملف عملاق.

---

## 1) الهوية و Multi-tenant (IDOR)

| القاعدة | التفاصيل |
|---------|-----------|
| **R1** | المصدر الوحيد لهوية الـ tenant هو `require_tenant(request)` / مفتاح API، **ليس** body/query. |
| **R2** | بعد أي `safe_json_body` على مسار مصادق: استدعِ `reject_identity_spoof(body, tenant_id=tenant.tenant_id)`. |
| **R3** | مسارات admin: `require_admin` فقط + `normalize_tenant_id` على path params. |
| **R4** | الوظائف المشتركة: `lumen/api/ownership.py` فقط — لا تنسخ فحوصات الملكية داخل كل route. |
| **R5** | Job/host: 404 موحّد إذا المورد غير موجود **أو** غير مملوك (لا تكشف الوجود لمستأجر آخر). |
| **R6** | كل مسار tenant جديد **يجب** أن يضيف اختبار في `tests/test_security_idor_dast.py` (أو ملف IDOR مخصص لنفس المجال). |

### ممنوع

```python
# ممنوع
tid = body.get("tenant_id") or request["tenant"].tenant_id
svc.do_something(tid)

# مطلوب
tenant = require_tenant(request)
reject_identity_spoof(body, tenant_id=tenant.tenant_id)
svc.do_something(tenant.tenant_id)
```

---

## 2) Credits و المال

| القاعدة | التفاصيل |
|---------|-----------|
| **R7** | كل حركة رصيد عبر `CreditService` (دفتر مزدوج) — ممنوع تعديل رصيد مباشر في الـ store من الـ routes. |
| **R8** | `promotional=True` يتطلب `promo_expires_at > 0` و reason من القائمة المسموحة. |
| **R9** | welcome grant: idempotency `welcome-grant-*` فقط. |
| **R10** | خصم/reserve يمر بـ `ensure_fresh_wallet` (انتهاء promo). |
| **R11** | أي تغيير في التسعير أو الرصيد الابتدائي = تحديث اختبارات welcome + توثيق `docs/20_*`. |

---

## 3) CI و المحركات

| القاعدة | التفاصيل |
|---------|-----------|
| **R12** | لا تضع `continue-on-error: true` على خطوة محرك أمني يفترض أن يفشل البناء (إلا رفع SARIF). |
| **R13** | لا تخفّض عتبة محرك (مثلاً ZAP من fail-on-warning إلى ignore) بدون موافقة أمنية مكتوبة في الـ PR. |
| **R14** | إضافة محرك = workflow المرحلة المناسبة فقط + صف في `docs/26_SECURITY_ENGINES.md` + تحديث الـ gate. |
| **R15** | أدوات المسح تُثبَّت من مصادرها الرسمية (Actions / صور ghcr) عبر `requirements-security.txt` عند الحاجة. |

---

## 4) هيكل المشروع للتوسع

| القاعدة | التفاصيل |
|---------|-----------|
| **R16** | حزمة بايثون واحدة ≈ مجال واحد (`lumen.platform/credits/`, `lumen/api/routes/`, `lumen.engine/security/`). |
| **R17** | ممنوع استيراد دائري بين `api` ↔ `lumen.engine` إلا عبر واجهات ضيقة موثّقة. |
| **R18** | ملفات > ~500 سطر تُقسَّم عند إضافة مسؤولية جديدة (إلا generated/vendor). |
| **R19** | الأسرار: env فقط، ممنوع في الصورة أو المستودع. Dockerfile = non-root. |
| **R20** | كل PR يلمس أمان/فوترة/عزل يجب أن يمر بوابات Phase 1–4 (status checks). |

---

## 5) قائمة تحقق قبل طلب المراجعة

- [ ] لا `tenant_id` من body يتحكم في التفويض  
- [ ] `reject_identity_spoof` على المسارات الجديدة المصادقة  
- [ ] اختبار IDOR أو attack-surface للمسار الجديد  
- [ ] لا أسرار في الفرق  
- [ ] لم يُعطَّل gate أو محرك  
- [ ] التوثيق المحدّث في `docs/security/` إن تغيّرت حدود مرحلة  

---

## 6) عقوبة المخالفة (عملية)

PR مخالف لـ R1–R6 أو R12–R13: **يُرفض** حتى الإصلاح.  
لا يُدمَج بـ "نصلح لاحقاً" على مسارات المال أو العزل.
