"use client";

/**
 * Telegram Mini App — secure secret intake (bot token / GitHub PAT).
 * Validates nothing client-side beyond format; server verifies initData HMAC.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

type Kind = "bot" | "github";

function apiBase(): string {
  const raw =
    typeof process !== "undefined" ? process.env.NEXT_PUBLIC_LUMEN_API_URL : undefined;
  return (raw || "").replace(/\/$/, "") || "";
}

function readInitData(): string {
  try {
    const w = window as unknown as {
      Telegram?: { WebApp?: { initData?: string; ready?: () => void; expand?: () => void; close?: () => void; themeParams?: Record<string, string> } };
    };
    const tg = w.Telegram?.WebApp;
    tg?.ready?.();
    tg?.expand?.();
    return tg?.initData || "";
  } catch {
    return "";
  }
}

function kindFromQuery(): Kind {
  if (typeof window === "undefined") return "bot";
  const q = new URLSearchParams(window.location.search);
  const k = (q.get("kind") || "bot").toLowerCase();
  return k === "github" || k === "pat" ? "github" : "bot";
}

export default function SecretsPage() {
  const [kind, setKind] = useState<Kind>("bot");
  const [secret, setSecret] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");
  const [initData, setInitData] = useState("");

  useEffect(() => {
    setKind(kindFromQuery());
    // Load Telegram WebApp script if missing
    const existing = document.querySelector('script[data-telegram-web-app]');
    if (!existing) {
      const s = document.createElement("script");
      s.src = "https://telegram.org/js/telegram-web-app.js";
      s.async = true;
      s.dataset.telegramWebApp = "1";
      s.onload = () => setInitData(readInitData());
      document.head.appendChild(s);
    } else {
      setInitData(readInitData());
    }
    const t = window.setTimeout(() => setInitData(readInitData()), 400);
    return () => window.clearTimeout(t);
  }, []);

  const placeholder = useMemo(
    () =>
      kind === "bot"
        ? "1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        : "ghp_xxxxxxxx  أو  github_pat_xxxxxxxx",
    [kind]
  );

  const title = kind === "bot" ? "توكن بوت تيليجرام" : "توكن GitHub (PAT)";
  const help =
    kind === "bot"
      ? "من @BotFather → API Token. لن يُعرض السر في الدردشة."
      : "Classic: ghp_… بصلاحية repo — أو Fine-grained: github_pat_…";

  const submit = useCallback(async () => {
    const value = secret.trim();
    if (!value) {
      setStatus("err");
      setMessage("أدخل السر أولاً.");
      return;
    }
    const idata = initData || readInitData();
    if (!idata) {
      setStatus("err");
      setMessage("افتح هذه الصفحة من داخل تيليجرام (Mini App) حتى يتم التحقق من هويتك.");
      return;
    }
    const base = apiBase();
    if (!base) {
      setStatus("err");
      setMessage("NEXT_PUBLIC_LUMEN_API_URL غير مضبوط.");
      return;
    }
    setStatus("loading");
    setMessage("جاري التشفير والحفظ…");
    try {
      const res = await fetch(`${base}/v1/telegram/secrets`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          init_data: idata,
          kind,
          secret: value,
          purpose: kind === "bot" ? "host" : "clone",
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.ok) {
        setStatus("err");
        setMessage(
          body.detail || body.error || `فشل الحفظ (${res.status})`
        );
        return;
      }
      setStatus("ok");
      setMessage(body.hint_ar || "تم الحفظ مشفراً. ارجع للدردشة.");
      setSecret("");
      try {
        const w = window as unknown as { Telegram?: { WebApp?: { close?: () => void } } };
        window.setTimeout(() => w.Telegram?.WebApp?.close?.(), 1200);
      } catch {
        /* ignore */
      }
    } catch (e) {
      setStatus("err");
      setMessage(e instanceof Error ? e.message : "network_error");
    }
  }, [secret, kind, initData]);

  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "24px 16px",
        fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
        background: "var(--tg-theme-bg-color, #0f1115)",
        color: "var(--tg-theme-text-color, #f2f4f8)",
        direction: "rtl",
      }}
    >
      <div style={{ maxWidth: 420, margin: "0 auto" }}>
        <h1 style={{ fontSize: 22, marginBottom: 8 }}>{title}</h1>
        <p style={{ opacity: 0.8, fontSize: 14, lineHeight: 1.5, marginBottom: 20 }}>
          {help}
        </p>

        <label style={{ display: "block", fontSize: 13, marginBottom: 6, opacity: 0.9 }}>
          السر (لا يُخزَّن في الدردشة)
        </label>
        <input
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder={placeholder}
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "12px 14px",
            borderRadius: 10,
            border: "1px solid #333",
            background: "var(--tg-theme-secondary-bg-color, #1a1d24)",
            color: "inherit",
            fontSize: 15,
            marginBottom: 16,
            direction: "ltr",
            textAlign: "left",
          }}
        />

        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          <button
            type="button"
            onClick={() => setKind("bot")}
            style={chipStyle(kind === "bot")}
          >
            بوت تيليجرام
          </button>
          <button
            type="button"
            onClick={() => setKind("github")}
            style={chipStyle(kind === "github")}
          >
            GitHub PAT
          </button>
        </div>

        <button
          type="button"
          onClick={submit}
          disabled={status === "loading"}
          style={{
            width: "100%",
            padding: "14px 16px",
            borderRadius: 12,
            border: "none",
            background: "var(--tg-theme-button-color, #2aabee)",
            color: "var(--tg-theme-button-text-color, #fff)",
            fontSize: 16,
            fontWeight: 600,
            cursor: status === "loading" ? "wait" : "pointer",
          }}
        >
          {status === "loading" ? "…" : "حفظ مشفّر"}
        </button>

        {message ? (
          <p
            style={{
              marginTop: 16,
              padding: 12,
              borderRadius: 10,
              background:
                status === "ok"
                  ? "rgba(46, 160, 67, 0.2)"
                  : status === "err"
                  ? "rgba(248, 81, 73, 0.2)"
                  : "transparent",
              fontSize: 14,
              lineHeight: 1.45,
            }}
          >
            {message}
          </p>
        ) : null}

        <p style={{ marginTop: 24, fontSize: 12, opacity: 0.55, lineHeight: 1.4 }}>
          التحقق عبر توقيع Telegram initData (HMAC). لا يُرسل السر إلى سجلات الدردشة.
        </p>
      </div>
    </main>
  );
}

function chipStyle(active: boolean): React.CSSProperties {
  return {
    flex: 1,
    padding: "10px 8px",
    borderRadius: 10,
    border: active ? "1px solid #2aabee" : "1px solid #333",
    background: active ? "rgba(42, 171, 238, 0.15)" : "transparent",
    color: "inherit",
    cursor: "pointer",
    fontSize: 13,
  };
}
