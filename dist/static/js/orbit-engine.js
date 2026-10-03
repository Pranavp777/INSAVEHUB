/**
 * INSTASAVE HUB — Futuristic iOS-Inspired Visual Engine & Interactive UI Controller
 * Features subtle atmospheric blue/indigo light motes, smooth scroll reveal,
 * live 24-hour free access countdown ticker, and native PWA installation.
 */
(function () {
  "use strict";

  const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const STORAGE_KEY_24H = "instasave_24h_access";

  let globalDeferredInstallPrompt = null;
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    globalDeferredInstallPrompt = event;
    if (typeof window.syncInstallPromptState === "function") {
      window.syncInstallPromptState();
    }
  });

  function initScrollReveal() {
    const items = document.querySelectorAll(".reveal-item");
    if (!items.length) return;

    if (reducedMotionQuery.matches || !("IntersectionObserver" in window)) {
      items.forEach((el) => el.classList.add("is-visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -24px 0px" }
    );

    items.forEach((el) => observer.observe(el));
  }

  function initAmbientParticles() {
    const canvas = document.getElementById("ambientParticleCanvas");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    window.addEventListener(
      "resize",
      () => {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
      },
      { passive: true }
    );

    const count = Math.min(34, Math.max(16, Math.floor((width * height) / 48000)));
    const palette = [
      "rgba(96, 165, 250, 0.32)",
      "rgba(59, 130, 246, 0.25)",
      "rgba(129, 140, 248, 0.24)",
      "rgba(248, 250, 252, 0.28)",
    ];

    const motes = Array.from({ length: count }, (_, idx) => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: 0.9 + Math.random() * 1.6,
      vx: (Math.random() - 0.5) * 0.18,
      vy: (Math.random() - 0.5) * 0.18,
      phase: Math.random() * Math.PI * 2,
      color: palette[idx % palette.length],
    }));

    function drawScene() {
      ctx.clearRect(0, 0, width, height);

      for (let i = 0; i < motes.length; i++) {
        const m = motes[i];
        if (!reducedMotionQuery.matches) {
          m.x += m.vx;
          m.y += m.vy;
          m.phase += 0.015;

          if (m.x < 0) m.x = width;
          if (m.x > width) m.x = 0;
          if (m.y < 0) m.y = height;
          if (m.y > height) m.y = 0;
        }

        const radius = Math.max(0.6, m.r + Math.sin(m.phase) * 0.35);
        ctx.beginPath();
        ctx.arc(m.x, m.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = m.color;
        ctx.fill();
      }

      if (!reducedMotionQuery.matches) {
        requestAnimationFrame(drawScene);
      }
    }

    drawScene();
  }

  function initFeatureCardPreviews() {
    const navLinks = document.querySelectorAll(".nav-links .nav-link");
    navLinks.forEach((link) => {
      link.addEventListener("click", () => {
        navLinks.forEach((l) => l.classList.remove("is-current"));
        link.classList.add("is-current");
      });
    });
  }

  function initMobileDrawer() {
    const toggleBtn = document.getElementById("mobileMenuToggle");
    const drawer = document.getElementById("mobileDrawer");
    if (!toggleBtn || !drawer) return;

    toggleBtn.addEventListener("click", () => {
      const isOpen = drawer.classList.toggle("is-open");
      toggleBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });

    drawer.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        drawer.classList.remove("is-open");
        toggleBtn.setAttribute("aria-expanded", "false");
      });
    });
  }

  function formatDurationHMS(totalSeconds) {
    const clamped = Math.max(0, Math.floor(totalSeconds));
    const hours = String(Math.floor(clamped / 3600)).padStart(2, "0");
    const minutes = String(Math.floor((clamped % 3600) / 60)).padStart(2, "0");
    const seconds = String(clamped % 60).padStart(2, "0");
    return `${hours}:${minutes}:${seconds}`;
  }

  let freeAccessIntervalId = null;

  function handleFreeAccessExpired() {
    const statusCard = document.getElementById("freeAccessStatusCard");
    if (statusCard) {
      statusCard.hidden = true;
      statusCard.setAttribute("data-access-state", "STATE_4_EXPIRED");
    }
    try {
      localStorage.removeItem(STORAGE_KEY_24H);
      document.cookie = "insave_free_until=0; path=/; max-age=0; SameSite=Lax";
    } catch (_err) {
      // Ignore storage errors
    }
    if (
      window.InstaSaveDownloader &&
      typeof window.InstaSaveDownloader.onFreeAccessExpired === "function"
    ) {
      window.InstaSaveDownloader.onFreeAccessExpired();
    }
    fetch("/ads/access-status/", { headers: { Accept: "application/json" } }).catch(() => {});
  }

  function initFreeAccessTickers() {
    if (freeAccessIntervalId) {
      clearInterval(freeAccessIntervalId);
      freeAccessIntervalId = null;
    }

    const statusCard = document.getElementById("freeAccessStatusCard");
    const globalTimer = document.getElementById("globalFreeAccessTimer");

    // Hydrate from localStorage if 24h access was unlocked on edge/client
    try {
      const raw = localStorage.getItem(STORAGE_KEY_24H);
      if (raw) {
        const parsed = JSON.parse(raw);
        const expiresAtMs = Number(parsed.expires_at_ms || Date.parse(parsed.expires_at || ""));
        if (!isNaN(expiresAtMs) && expiresAtMs > Date.now()) {
          const remSec = Math.max(1, Math.floor((expiresAtMs - Date.now()) / 1000));
          if (statusCard) {
            statusCard.hidden = false;
            statusCard.setAttribute("data-access-state", "STATE_3_FREE_24H_ACTIVE");
          }
          if (globalTimer) {
            globalTimer.setAttribute("data-free-access-seconds", String(remSec));
            globalTimer.textContent = formatDurationHMS(remSec);
          }
        } else {
          localStorage.removeItem(STORAGE_KEY_24H);
        }
      }
    } catch (_e) {}

    const tickers = Array.from(document.querySelectorAll("[data-free-access-seconds]"));
    if (!tickers.length) return;

    let maxRemaining = 0;
    tickers.forEach((el) => {
      const val = parseInt(el.getAttribute("data-free-access-seconds") || "0", 10);
      if (!isNaN(val) && val > maxRemaining) {
        maxRemaining = val;
      }
    });

    if (maxRemaining <= 0) return;

    let remaining = maxRemaining;
    freeAccessIntervalId = setInterval(() => {
      remaining = Math.max(0, remaining - 1);
      const formatted = formatDurationHMS(remaining);
      tickers.forEach((el) => {
        el.setAttribute("data-free-access-seconds", String(remaining));
        el.textContent = formatted;
      });

      if (remaining <= 0) {
        clearInterval(freeAccessIntervalId);
        freeAccessIntervalId = null;
        handleFreeAccessExpired();
      }
    }, 1000);
  }

  window.InstaSaveAccessEngine = {
    refreshTickers: initFreeAccessTickers,
  };

  function initPwaAppInstaller() {
    if ("serviceWorker" in navigator) {
      if (document.readyState === "complete" || document.readyState === "interactive") {
        navigator.serviceWorker.register("/sw.js").catch(() => {});
      } else {
        window.addEventListener("load", () => {
          navigator.serviceWorker.register("/sw.js").catch(() => {});
        });
      }
    }

    const installTriggers = document.querySelectorAll(
      "#installAppNavBtn, #installAppMobileBtn, #installAppHeroBtn, [data-install-app-trigger]"
    );
    const modal = document.getElementById("appInstallModal");
    const closeBtn = document.getElementById("closeAppInstallModal");
    const nativeBtn = document.getElementById("triggerNativeInstallBtn");
    const statusText = document.getElementById("nativeInstallStatusText");
    const nativeWrap = document.getElementById("nativeInstallPromptWrap");
    const alreadyInstalledNotice = document.getElementById("alreadyInstalledNotice");
    const inAppAlert = document.getElementById("inAppBrowserAlert");
    const tabBtns = document.querySelectorAll("#installPlatformTabs .install-tab-btn");
    const panes = {
      ios: document.getElementById("installStepIos"),
      android: document.getElementById("installStepAndroid"),
      desktop: document.getElementById("installStepDesktop"),
      mac: document.getElementById("installStepMac"),
    };

    const isStandalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true ||
      document.referrer.includes("android-app://");

    const ua = navigator.userAgent || "";
    const isIos = /iphone|ipad|ipod/i.test(ua);
    const isAndroid = /android/i.test(ua);
    const isMac = /macintosh|mac os x/i.test(ua) && !isIos;
    const isInApp = /instagram|fbav|fban|line|micromessenger|tiktok|bytedance/i.test(ua);

    if (isInApp && inAppAlert) {
      inAppAlert.hidden = false;
    }

    function switchInstallTab(targetKey) {
      tabBtns.forEach((btn) => {
        const matches = btn.getAttribute("data-install-target") === targetKey;
        btn.classList.toggle("is-active", matches);
        btn.setAttribute("aria-selected", matches ? "true" : "false");
      });
      Object.entries(panes).forEach(([key, el]) => {
        if (el) el.hidden = key !== targetKey;
      });
    }

    tabBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = btn.getAttribute("data-install-target");
        if (target) switchInstallTab(target);
      });
    });

    let defaultPlatform = "desktop";
    if (isIos) defaultPlatform = "ios";
    else if (isAndroid) defaultPlatform = "android";
    else if (isMac) defaultPlatform = "mac";
    switchInstallTab(defaultPlatform);

    function updateInstallState() {
      if (isStandalone) {
        installTriggers.forEach((btn) => {
          const span = btn.querySelector("span");
          if (span) span.textContent = "App Installed";
          btn.classList.add("is-installed");
          btn.setAttribute("title", "INSTASAVE HUB is installed on this device");
        });
        if (statusText) statusText.textContent = "INSTASAVE HUB is running as an installed standalone app.";
        if (alreadyInstalledNotice) alreadyInstalledNotice.hidden = false;
        if (nativeWrap) nativeWrap.hidden = true;
        return;
      }

      if (globalDeferredInstallPrompt) {
        if (statusText) {
          statusText.textContent = "One-Click Native App Installation Ready";
        }
        if (nativeBtn) {
          nativeBtn.hidden = false;
          nativeBtn.removeAttribute("disabled");
        }
      } else {
        if (isIos) {
          if (statusText) {
            statusText.textContent = "iOS Setup: Tap Share then Add to Home Screen";
          }
          if (nativeBtn) nativeBtn.hidden = true;
        } else if (isAndroid) {
          if (statusText) {
            statusText.textContent = "Tap below or use browser menu (⋮) to install";
          }
        } else {
          if (statusText) {
            statusText.textContent = "Install via address bar icon or browser menu";
          }
        }
      }
    }

    window.syncInstallPromptState = updateInstallState;
    updateInstallState();

    window.addEventListener("appinstalled", () => {
      globalDeferredInstallPrompt = null;
      updateInstallState();
      if (modal) modal.hidden = true;
    });

    async function handleInstallTriggerClick(event) {
      if (event) event.preventDefault();

      if (isStandalone) {
        if (modal) {
          switchInstallTab(defaultPlatform);
          modal.hidden = false;
        }
        return;
      }

      if (globalDeferredInstallPrompt) {
        try {
          globalDeferredInstallPrompt.prompt();
          const choice = await globalDeferredInstallPrompt.userChoice;
          if (choice && choice.outcome === "accepted") {
            globalDeferredInstallPrompt = null;
            if (modal) modal.hidden = true;
            updateInstallState();
            return;
          }
        } catch (_err) {
          // Fall through to modal
        }
      }

      if (modal) {
        switchInstallTab(defaultPlatform);
        modal.hidden = false;
      }
    }

    installTriggers.forEach((btn) => {
      btn.addEventListener("click", handleInstallTriggerClick);
    });

    if (nativeBtn) {
      nativeBtn.addEventListener("click", async () => {
        if (globalDeferredInstallPrompt) {
          try {
            globalDeferredInstallPrompt.prompt();
            const choice = await globalDeferredInstallPrompt.userChoice;
            if (choice && choice.outcome === "accepted") {
              globalDeferredInstallPrompt = null;
              if (modal) modal.hidden = true;
              updateInstallState();
            }
          } catch (_err) {}
        } else {
          switchInstallTab(defaultPlatform);
        }
      });
    }

    if (closeBtn && modal) {
      closeBtn.addEventListener("click", () => {
        modal.hidden = true;
      });
    }

    if (modal) {
      modal.addEventListener("click", (event) => {
        if (event.target === modal) {
          modal.hidden = true;
        }
      });
    }

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && modal && !modal.hidden) {
        modal.hidden = true;
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initScrollReveal();
    initAmbientParticles();
    initFeatureCardPreviews();
    initMobileDrawer();
    initFreeAccessTickers();
    initPwaAppInstaller();
  });
})();
