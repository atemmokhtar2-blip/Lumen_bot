# Sandbox Runtime — عزل بمستوى منصات عالمية

## طبقات العزل (الأقوى → الأضعف)

| Backend | التقنية | يقارب |
|---------|---------|--------|
| `firecracker` | MicroVM + KVM | AWS Lambda / Fly Machines |
| `gvisor` | runsc (userspace kernel) | Google gVisor / GKE sandbox |
| `dind` | Docker daemon منفصل | معزول عن socket المضيف |
| `docker` | runc + seccomp + AppArmor + egress | حد أدنى إنتاجي |

`TBE_SANDBOX_BACKEND=auto` يختار الأقوى المتاح. **لا يوجد مسار host process.**

## ضمانات السياسة (`policy.py`)

- ممنوع `docker.sock` داخل حاوية البوت
- ممنوع شبكة `bridge` / `host` الافتراضية
- Egress: baseline iptables (حجب metadata `169.254.169.254` و loopback)
- Drop ALL capabilities + no-new-privileges + read-only rootfs
- Seccomp profile + AppArmor `tbe-bot` عند التحميل على المضيف
- Supervisor: reap exited + max lifetime

## المسار

```
host_start
  → harden_network / egress
  → select_sandbox_backend (fc|gvisor|dind|docker)
  → start
  → supervisor_tick (خلفية/cron)
```

## تفعيل gVisor على المضيف

```bash
# تثبيت runsc وتسجيله runtime في dockerd ثم:
TBE_SANDBOX_BACKEND=gvisor
# أو auto سيلتقطه تلقائياً
```

## تفعيل AppArmor

```bash
sudo apparmor_parser -r telegram_bot_engine/data/sandbox/apparmor-bot.profile
# يُطبَّق تلقائياً إذا ظهر الاسم في /sys/kernel/security/apparmor/profiles
```
