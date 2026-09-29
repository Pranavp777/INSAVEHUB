/**
 * INSTASAVE HUB — Futuristic iOS-Inspired Visual Engine & Interactive UI Controller
 * Features subtle atmospheric blue/indigo light motes, smooth scroll reveal,
 * interactive feature card previews, and native PWA installation.
 */
(function () {
  "use strict";

  const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

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

    // Very subtle electric-blue and indigo atmospheric motes (non-noisy)
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
    // 1. Smart Tasks interactive toggle rows
    const taskRows = document.querySelectorAll("[data-task-toggle]");
    taskRows.forEach((row) => {
      row.addEventListener("click", () => {
        const isDone = row.getAttribute("data-task-done") === "true";
        const nextState = !isDone;
        row.setAttribute("data-task-done", nextState ? "true" : "false");
        const badge = row.querySelector("[data-task-status]");
        if (badge) {
          badge.textContent = nextState ? "DONE" : "QUEUED";
          badge.style.color = nextState ? "#60A5FA" : "#94A3B8";
        }
      });
    });

    // 2. Dark & Light Mode mini-preview card toggle
    const modeToggleBtn = document.getElementById("miniThemeToggleBtn");
    const modeSurface = document.getElementById("miniThemeSurface");
    const modeLabel = document.getElementById("miniThemeLabel");
    if (modeToggleBtn && modeSurface && modeLabel) {
      let isMidnight = true;
      modeToggleBtn.addEventListener("click", () => {
        isMidnight = !isMidnight;
        if (isMidnight) {
          modeSurface.style.background = "rgba(6, 12, 26, 0.78)";
          modeSurface.style.color = "#F8FAFC";
          modeSurface.style.borderColor = "rgba(96, 165, 250, 0.24)";
          modeLabel.textContent = "MIDNIGHT GLASS";
          modeToggleBtn.textContent = "Switch to Daylight";
        } else {
          modeSurface.style.background = "linear-gradient(135deg, rgba(241, 245, 249, 0.94), rgba(226, 232, 240, 0.9))";
          modeSurface.style.color = "#0F172A";
          modeSurface.style.borderColor = "rgba(59, 130, 246, 0.45)";
          modeLabel.textContent = "DAYLIGHT GLASS";
          modeToggleBtn.textContent = "Switch to Midnight";
        }
      });
    }

    // 3. Smooth active pill transition on navigation links
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
      statusCard.setAttribute("data-access-state", "STATE_4");
    }
    try {
      localStorage.removeItem("instasave_24h_access");
    } catch (_err) {
      // Ignore storage errors
    }
    if (window.InstaSaveDownloader && typeof window.InstaSaveDownloader.onFreeAccessExpired === "function") {
      window.InstaSaveDownloader.onFreeAccessExpired();
    }
    fetch("/ads/access-status/", { headers: { Accept: "application/json" } }).catch(() => {});
  }

  function initFreeAccessTickers() {
    if (freeAccessIntervalId) {
      clearInterval(freeAccessIntervalId);
      freeAccessIntervalId = null;
    }

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
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js").catch(() => {});
      });
    }

    let deferredInstallPrompt = null;
    const installTriggers = document.querySelectorAll(
      "#installAppNavBtn, #installAppMobileBtn, #installAppHeroBtn, [data-install-app-trigger]"
    );
    const modal = document.getElementById("appInstallModal");
    const closeBtn = document.getElementById("closeAppInstallModal");
    const nativeBtn = document.getElementById("triggerNativeInstallBtn");
    const statusText = document.getElementById("nativeInstallStatusText");

    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      deferredInstallPrompt = event;
      if (statusText) {
        statusText.textContent = "One-Click Native App Installation Ready";
      }
    });

    window.addEventListener("appinstalled", () => {
      deferredInstallPrompt = null;
      if (statusText) {
        statusText.textContent = "INSTASAVE HUB App Installed on Device";
      }
      if (modal) modal.hidden = true;
    });

    async function handleInstallAction() {
      if (deferredInstallPrompt) {
        try {
          deferredInstallPrompt.prompt();
          const choice = await deferredInstallPrompt.userChoice;
          if (choice && choice.outcome === "accepted") {
            deferredInstallPrompt = null;
            if (modal) modal.hidden = true;
            return;
          }
        } catch (_err) {
          // Fall through to modal instructions
        }
      }
      if (modal) {
        modal.hidden = false;
      }
    }

    installTriggers.forEach((btn) => {
      btn.addEventListener("click", handleInstallAction);
    });
    if (nativeBtn) {
      nativeBtn.addEventListener("click", async () => {
        if (deferredInstallPrompt) {
          deferredInstallPrompt.prompt();
          await deferredInstallPrompt.userChoice;
          deferredInstallPrompt = null;
          if (modal) modal.hidden = true;
        } else if (statusText) {
          statusText.textContent =
            "Use your browser address bar install icon or mobile menu below.";
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
