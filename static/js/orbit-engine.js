/**
 * InSave Hub — Glass Orbit Visual Engine & Interactive Sky-Blue/White Particle System
 * Features multi-layer bokeh orbs, crystalline particles, constellation filaments,
 * and interactive pointer reactivity while respecting prefers-reduced-motion.
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
      { threshold: 0.12, rootMargin: "0px 0px -32px 0px" }
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

    const pointer = { x: -9999, y: -9999, active: false };

    window.addEventListener(
      "mousemove",
      (e) => {
        pointer.x = e.clientX;
        pointer.y = e.clientY;
        pointer.active = true;
      },
      { passive: true }
    );

    window.addEventListener(
      "mouseleave",
      () => {
        pointer.active = false;
      },
      { passive: true }
    );

    window.addEventListener(
      "touchmove",
      (e) => {
        if (e.touches && e.touches.length > 0) {
          pointer.x = e.touches[0].clientX;
          pointer.y = e.touches[0].clientY;
          pointer.active = true;
        }
      },
      { passive: true }
    );

    window.addEventListener(
      "resize",
      () => {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
      },
      { passive: true }
    );

    // Layer 1: Soft Sky-Blue & White Bokeh Light Orbs
    const bokehCount = Math.min(12, Math.max(5, Math.floor((width * height) / 140000)));
    const bokehOrbs = Array.from({ length: bokehCount }, (_, idx) => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: 45 + Math.random() * 75,
      vx: (Math.random() - 0.5) * 0.22,
      vy: (Math.random() - 0.5) * 0.22,
      isWhite: idx % 2 === 0,
    }));

    // Layer 2: Crystalline Sky-Blue & White Nodes with Constellation Filaments
    const nodeCount = Math.min(72, Math.max(28, Math.floor((width * height) / 22000)));
    const palette = [
      { fill: "rgba(2, 132, 199, 0.55)", glow: "rgba(14, 165, 233, 0.35)" },
      { fill: "rgba(14, 165, 233, 0.62)", glow: "rgba(56, 189, 248, 0.4)" },
      { fill: "rgba(56, 189, 248, 0.65)", glow: "rgba(186, 230, 253, 0.5)" },
      { fill: "rgba(255, 255, 255, 0.92)", glow: "rgba(14, 165, 233, 0.3)" },
    ];

    const nodes = Array.from({ length: nodeCount }, (_, idx) => {
      const style = palette[idx % palette.length];
      return {
        x: Math.random() * width,
        y: Math.random() * height,
        r: 1.6 + Math.random() * 2.6,
        vx: (Math.random() - 0.5) * 0.48,
        vy: (Math.random() - 0.5) * 0.48,
        phase: Math.random() * Math.PI * 2,
        fill: style.fill,
        glow: style.glow,
      };
    });

    function drawScene() {
      ctx.clearRect(0, 0, width, height);

      // 1. Render Soft Bokeh Gradient Orbs
      for (let i = 0; i < bokehOrbs.length; i++) {
        const orb = bokehOrbs[i];
        if (!reducedMotionQuery.matches) {
          orb.x += orb.vx;
          orb.y += orb.vy;
          if (orb.x < -orb.r) orb.x = width + orb.r;
          if (orb.x > width + orb.r) orb.x = -orb.r;
          if (orb.y < -orb.r) orb.y = height + orb.r;
          if (orb.y > height + orb.r) orb.y = -orb.r;
        }

        const grad = ctx.createRadialGradient(orb.x, orb.y, 0, orb.x, orb.y, orb.r);
        if (orb.isWhite) {
          grad.addColorStop(0, "rgba(255, 255, 255, 0.55)");
          grad.addColorStop(0.5, "rgba(224, 242, 254, 0.22)");
          grad.addColorStop(1, "rgba(255, 255, 255, 0)");
        } else {
          grad.addColorStop(0, "rgba(56, 189, 248, 0.24)");
          grad.addColorStop(0.55, "rgba(14, 165, 233, 0.09)");
          grad.addColorStop(1, "rgba(56, 189, 248, 0)");
        }
        ctx.beginPath();
        ctx.arc(orb.x, orb.y, orb.r, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();
      }

      // 2. Update & Render Crystalline Particles + Pointer Interaction
      for (let i = 0; i < nodes.length; i++) {
        const p = nodes[i];
        if (!reducedMotionQuery.matches) {
          p.x += p.vx;
          p.y += p.vy;
          p.phase += 0.025;

          if (pointer.active) {
            const dx = p.x - pointer.x;
            const dy = p.y - pointer.y;
            const distSq = dx * dx + dy * dy;
            const maxRadius = 150;
            if (distSq < maxRadius * maxRadius && distSq > 1) {
              const dist = Math.sqrt(distSq);
              const force = (maxRadius - dist) / maxRadius;
              p.x += (dx / dist) * force * 1.35;
              p.y += (dy / dist) * force * 1.35;
            }
          }

          if (p.x < 0) p.x = width;
          if (p.x > width) p.x = 0;
          if (p.y < 0) p.y = height;
          if (p.y > height) p.y = 0;
        }

        // Draw outer halo glow
        const pulseRadius = p.r + Math.sin(p.phase) * 0.6;
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(1, pulseRadius * 2.4), 0, Math.PI * 2);
        ctx.fillStyle = p.glow;
        ctx.fill();

        // Draw core particle
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(0.8, pulseRadius), 0, Math.PI * 2);
        ctx.fillStyle = p.fill;
        ctx.fill();
      }

      // 3. Draw Sky-Blue & White Constellation Filaments Between Nearby Particles
      const maxLinkDistance = 128;
      ctx.lineWidth = 0.85;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distSq = dx * dx + dy * dy;
          if (distSq < maxLinkDistance * maxLinkDistance) {
            const alpha = (1 - Math.sqrt(distSq) / maxLinkDistance) * 0.26;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.strokeStyle = `rgba(2, 132, 199, ${alpha.toFixed(3)})`;
            ctx.stroke();
          }
        }

        // Connect nearby particles to active cursor
        if (pointer.active) {
          const pdx = a.x - pointer.x;
          const pdy = a.y - pointer.y;
          const pDistSq = pdx * pdx + pdy * pdy;
          if (pDistSq < 165 * 165) {
            const pAlpha = (1 - Math.sqrt(pDistSq) / 165) * 0.42;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(pointer.x, pointer.y);
            ctx.strokeStyle = `rgba(14, 165, 233, ${pAlpha.toFixed(3)})`;
            ctx.stroke();
          }
        }
      }

      if (!reducedMotionQuery.matches) {
        requestAnimationFrame(drawScene);
      }
    }

    drawScene();
  }

  function initOrbitInteractiveConsole() {
    const satellites = document.querySelectorAll("[data-orbit-tool]");
    const consoleTitle = document.getElementById("orbitConsoleTitle");
    const consoleCategory = document.getElementById("orbitConsoleCategory");
    const consoleFormat = document.getElementById("orbitConsoleFormat");
    const consoleUrl = document.getElementById("orbitConsoleUrl");

    if (!satellites.length || !consoleTitle) return;

    satellites.forEach((sat) => {
      sat.addEventListener("click", () => {
        satellites.forEach((s) => s.classList.remove("is-active"));
        sat.classList.add("is-active");
        if (consoleTitle) consoleTitle.textContent = sat.getAttribute("data-title") || "";
        if (consoleCategory) consoleCategory.textContent = sat.getAttribute("data-category") || "";
        if (consoleFormat) consoleFormat.textContent = sat.getAttribute("data-format") || "";
        if (consoleUrl) consoleUrl.textContent = sat.getAttribute("data-sample-url") || "";
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
  }

  function formatDurationHMS(totalSeconds) {
    const clamped = Math.max(0, Math.floor(totalSeconds));
    const hours = String(Math.floor(clamped / 3600)).padStart(2, "0");
    const minutes = String(Math.floor((clamped % 3600) / 60)).padStart(2, "0");
    const seconds = String(clamped % 60).padStart(2, "0");
    return `${hours}:${minutes}:${seconds}`;
  }

  function initFreeAccessTickers() {
    const tickers = document.querySelectorAll("[data-free-access-seconds]");
    if (!tickers.length) return;

    tickers.forEach((el) => {
      let remaining = parseInt(el.getAttribute("data-free-access-seconds") || "0", 10);
      if (isNaN(remaining) || remaining <= 0) return;

      setInterval(() => {
        remaining = Math.max(0, remaining - 1);
        el.textContent = formatDurationHMS(remaining);
      }, 1000);
    });
  }

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
        statusText.textContent = "InSave Hub App Installed on Device";
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
    initOrbitInteractiveConsole();
    initMobileDrawer();
    initFreeAccessTickers();
    initPwaAppInstaller();
  });
})();

