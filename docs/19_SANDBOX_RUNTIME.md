# Sandbox Runtime — عزل البوتات المولَّدة

## المبدأ

كل بوت مولَّد يُشغَّل داخل **صندوق معزول** عن المضيف وعن بقية البوتات.
لا يوجد مسار نجاح صامت على LocalProcess من هذه الطبقة.

## الخلفيات (الأقوى أولاً)

| Backend | العزل | المتطلبات |
|---------|--------|-----------|
| `firecracker` | MicroVM + KVM | `TBE_FIRECRACKER_BIN`, `TBE_FC_KERNEL`, `TBE_FC_ROOTFS`, `/dev/kvm` |
| `dind` | Docker daemon منفصل | `TBE_DIND_HOST` (ليس `docker.sock` الافتراضي إلا بإذن صريح) |
| `docker` | حاوية مقواة على Docker المضيف | Docker + `TBE_DOCKER_NETWORK` + seccomp |

`TBE_SANDBOX_BACKEND=auto` يختار أقوى خلفية متاحة.

## المسار

```
host_start / token live-run
  → HostingService.start
    → sandbox_runtime.start_sandboxed_bot
      → firecracker | dind | docker
```

## ملفات

- `telegram_bot_engine/services/sandbox_runtime/`
- `telegram_bot_engine/data/sandbox/seccomp-bot.json`
- سياسة: `isolation_policy.select_process_driver` → نفس الطبقة

## فشل مغلق

إن لم تتوفر أي خلفية → `RuntimeError` / رسالة استضافة واضحة. لا تشغيل على المضيف.
