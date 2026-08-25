"""Complex Arabic commerce_pro detection tests."""
from __future__ import annotations

from lumen.engine.spec_core.presets import detect_preset, detect_preset_stack, score_presets

COMPLEX = """عايز بوت تيليجرام عالمي متكامل commerce pro كامل:
متجر + كتالوج + سلة + كوبونات + فواتير ومدفوعات تيليجرام + تتبع وإلغاء طلبات + استرجاع،
اشتراكات وخطط وتجربة مجانية وتجديد وإهداء اشتراك،
نقاط وولاء ولوحة متصدرين وتحويل نقاط ومستويات،
محفظة رصيد وشحن،
إحالات وروابط دعوة وتسجيل يومي وسلاسل،
مسابقات وسحب فائزين،
تحليلات وإيرادات ومستخدمين وإذاعة لشرائح،
دعم تذاكر وقاعدة معرفة،
ترجمة واجهة /lang عربي إنجليزي،
خصوصية وشروط وتصدير/حذف بياناتي،
أدمن: مخزون، كوبونات، منح نقاط، إدارة اشتراكات، حظر، وضع صيانة."""


def test_full_arabic_commerce_pro_is_primary():
    assert detect_preset(COMPLEX) == "commerce_pro"
    stack = detect_preset_stack(COMPLEX, limit=6)
    assert stack[0] == "commerce_pro"
    top = score_presets(COMPLEX)[0]
    assert top[0] == "commerce_pro"
    assert top[1] > score_presets(COMPLEX)[1][1]


def test_multi_pillar_without_phrase_still_commerce_pro():
    q = "متجر + كتالوج + سلة + كوبونات + اشتراكات + نقاط + محفظة + إحالات + مسابقات + تحليلات + تذاكر"
    assert detect_preset(q) == "commerce_pro"


def test_simple_shop_not_escalated():
    q = "بوت متجر بسيط فيه منتجات"
    assert detect_preset(q) == "shop"
    assert detect_preset_stack(q, limit=3)[0] == "shop"


def test_shop_cart_coupons_payments_escalates():
    q = "متجر + كتالوج + سلة + كوبونات + فواتير ومدفوعات تيليجرام"
    assert detect_preset(q) == "commerce_pro"
