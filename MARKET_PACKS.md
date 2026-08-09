# Market packs — capabilities for **generated** bots (end-users)

These packs power bots your customers run. They are **not** billing for AI Agent 7h itself.

## Scale

- **291** executable capabilities across **40** categories
- Presets auto-detect Arabic + English keywords
- Samples under `telegram_bot_engine/spec_core/samples/`
- Integrity: `python -m telegram_bot_engine.spec_core.capability_integrity`

## Hardened zero-AI codegen (not just labels)

Real SQLite logic is emitted for: shop orders, points, subscriptions, contests, wallet, referrals, check-in, `/lang`.
Orders only move pending→paid via `mark_paid` (no fake paid flag).


## Launch presets

| Preset | Trigger examples | What the end-user bot gets |
|--------|------------------|----------------------------|
| `commerce_pro` | متجر متكامل، commerce pro، full ecommerce | Shop + cart + coupons + Telegram Payments + subs + points + wallet + growth + analytics |
| `shop` | متجر، payments، شراء | Catalog, invoice buy, orders, wishlist, refunds, digital delivery |
| `subscriptions` | اشتراك، VIP، subscribe | Plans, subscribe, grant/revoke, i18n |
| `points` | نقاط، leaderboard | Balance, ledger, redeem, streaks hooks |
| `contests` | مسابقة، giveaway | Join, draw winner, admin lifecycle |
| `growth` | إحالة، referral، check-in | Invite links, rewards, daily check-in |
| `creator` | منشئ، paid content، tip | Paid unlock, tips, membership gate |
| `saas` | saas، analytics، webhook | Plans + analytics + compliance + maintenance |
| `crm` | crm، leads، pipeline | Leads, deals, follow-ups |
| `support_pro` | قاعدة معرفة، CSAT | Tickets + KB + priority/assign |
| `education` | دورة، quiz، شهادة | Courses, lessons, homework, certificate |
| `restaurant` | مطعم، menu | Menu, order, table book |
| `jobs` | وظائف، hiring | Job board + applications |
| `marketplace` | سوق، إعلان | Listings, search, contact seller |
| `community` | مجتمع، feed | Profiles, posts, mod queue |
| `events` | فعالية، RSVP | Events + attendance |
| `wallet` | محفظة، topup | Credits wallet |
| `group_management` | إدارة مجموعات | Classic moderation + welcome |

## Global default

For `commerce_pro` and when the user says **global / عالمي**, plans prefer:

- `language: en` or `mixed`
- `tech.i18n: true`
- `/lang` for end-users of the generated bot

## Payments rule

Generated bots that charge money **must** use Telegram Payments (`sendInvoice` → pre-checkout → `successful_payment`). No fake “paid” flags.


## New verticals

| Preset | Keywords | Core features |
|--------|----------|---------------|
| `fitness` | جيم، gym، fitness | schedule, book, check-in, membership |
| `realestate` | عقار، property | list, search, inquiry |
| `clinic` | عيادة، doctor | slots, book, cancel |
| `auction` | مزاد، bid | list, bid, create |
| `delivery` | شحنة، track | track, status |
