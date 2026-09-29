/**
 * INSTASAVE HUB — Server & Edge-Synchronized 30-Second Advertisement Countdown Controller
 * Watching the 30-second advertisement until 00:00 unlocks 24 hours of ad-free downloads.
 * Never allows skipping before the timer reaches 00:00 and persists countdown across refreshes.
 */
(function () {
  "use strict";

  const RING_RADIUS = 78;
  const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
  const STORAGE_KEY_24H = "instasave_24h_access";
  const STORAGE_KEY_AD_TIMER = "instasave_active_ad_timer";

  function getCsrfToken() {
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function formatMMSS(sec) {
    const clamped = Math.max(0, Math.floor(sec));
    const mins = String(Math.floor(clamped / 60)).padStart(2, "0");
    const secs = String(clamped % 60).padStart(2, "0");
    return `${mins}:${secs}`;
  }

  function grantClient24HourAccess(remainingSeconds = 86400) {
    const expiresAtMs = Date.now() + remainingSeconds * 1000;
    const expiresIso = new Date(expiresAtMs).toISOString();
    try {
      localStorage.setItem(
        STORAGE_KEY_24H,
        JSON.stringify({
          active: true,
          expires_at_ms: expiresAtMs,
          expires_at: expiresIso,
          remaining_seconds: remainingSeconds,
        })
      );
      sessionStorage.removeItem(STORAGE_KEY_AD_TIMER);
      document.cookie = `insave_free_until=${expiresAtMs}; path=/; max-age=${remainingSeconds}; SameSite=Lax`;
    } catch (_e) {
      // Ignore storage quota errors
    }
  }

  function initAdCountdownGate() {
    const stage = document.getElementById("adCountdownStage");
    if (!stage) return;

    const urlParams = new URLSearchParams(window.location.search);
    const queryMode = (urlParams.get("mode") || "").toLowerCase();
    const downloadIdParam = urlParams.get("download_id") || "";

    const sessionId = stage.getAttribute("data-session-id") || "";
    const adMode = queryMode === "5s" ? "5s" : stage.getAttribute("data-ad-mode") || "30s";
    const completeUrl = stage.getAttribute("data-complete-url") || "/ads/complete/";

    const totalDuration =
      adMode === "5s"
        ? 5
        : Math.max(1, parseInt(stage.getAttribute("data-total-seconds") || "30", 10));

    let remaining =
      adMode === "5s"
        ? Math.min(5, parseInt(stage.getAttribute("data-remaining-seconds") || "5", 10))
        : parseInt(stage.getAttribute("data-remaining-seconds") || String(totalDuration), 10);

    // Persist countdown across page refreshes on static/edge builds
    try {
      const savedTimerRaw = sessionStorage.getItem(STORAGE_KEY_AD_TIMER);
      if (savedTimerRaw) {
        const savedTimer = JSON.parse(savedTimerRaw);
        if (savedTimer && savedTimer.mode === adMode && savedTimer.targetMs > Date.now()) {
          const calcRem = Math.ceil((savedTimer.targetMs - Date.now()) / 1000);
          remaining = Math.min(remaining, Math.max(1, calcRem));
        }
      } else {
        sessionStorage.setItem(
          STORAGE_KEY_AD_TIMER,
          JSON.stringify({
            mode: adMode,
            targetMs: Date.now() + remaining * 1000,
          })
        );
      }
    } catch (_e) {}

    const formattedEl = document.getElementById("adCountdownFormatted");
    const numberEl = document.getElementById("adCountdownNumber");
    const unitEl = document.getElementById("adCountdownUnit");
    const progressEl = document.getElementById("adProgressBar");
    const ringEl = document.getElementById("adCircularProgress");
    const unlockBtn = document.getElementById("adUnlockSubmitBtn");
    const stateLabel = document.getElementById("adStateTelemetryLabel");
    const stateDot = document.getElementById("adTelemetryDot");
    const headlineEl = document.getElementById("adHeadlineText");
    const subheadlineEl = document.getElementById("adSubheadlineText");
    const nonceInput = document.getElementById("adNonceTokenInput");
    const formEl = document.getElementById("adCompleteForm");

    let isCompleting = false;
    let hasCompleted = false;

    if (ringEl) {
      ringEl.style.strokeDasharray = `${RING_CIRCUMFERENCE.toFixed(2)}`;
      ringEl.style.strokeDashoffset = `${RING_CIRCUMFERENCE.toFixed(2)}`;
    }

    function updateVisualState() {
      const clamped = Math.max(0, remaining);
      const mmss = formatMMSS(clamped);

      if (formattedEl) formattedEl.textContent = mmss;
      if (numberEl) numberEl.textContent = String(clamped).padStart(2, "0");

      const elapsed = Math.max(0, totalDuration - clamped);
      const ratio = Math.min(1, Math.max(0, elapsed / totalDuration));
      const pct = Math.round(ratio * 100);

      if (progressEl) {
        progressEl.style.width = `${pct}%`;
      }
      if (ringEl) {
        const offset = RING_CIRCUMFERENCE * (1 - ratio);
        ringEl.style.strokeDashoffset = `${offset.toFixed(2)}`;
      }

      if (clamped <= 0) {
        if (stateLabel) stateLabel.textContent = "Access unlocked";
        if (unitEl) unitEl.textContent = "ACCESS UNLOCKED";
        if (stateDot) {
          stateDot.classList.remove("status-dot-amber");
          stateDot.classList.add("status-dot-emerald");
        }
        if (headlineEl) {
          headlineEl.textContent =
            adMode === "5s"
              ? "Advertisement complete — starting your download..."
              : "Access unlocked — 24-hour ad-free downloads enabled!";
        }
        if (subheadlineEl) {
          subheadlineEl.textContent = "Redirecting automatically to your download...";
        }
        if (unlockBtn) {
          unlockBtn.disabled = false;
          unlockBtn.textContent = "Access unlocked — Continue to Download";
        }
        triggerAutoCompletion();
      } else {
        if (unlockBtn) {
          unlockBtn.disabled = true;
          unlockBtn.textContent =
            adMode === "5s"
              ? `Your download will begin shortly (${mmss})...`
              : `Watch until 00:00 to unlock 24-hour free access (${mmss})...`;
        }
      }
    }

    async function triggerAutoCompletion() {
      if (isCompleting || hasCompleted) return;
      isCompleting = true;

      const nonceToken = nonceInput ? nonceInput.value : "";
      const fallbackRedirect = downloadIdParam
        ? `/downloads/?download_id=${encodeURIComponent(downloadIdParam)}&auto_download=1&unlocked_24h=1`
        : "/downloads/?unlocked_24h=1";

      try {
        const resp = await fetch(completeUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-CSRFToken": getCsrfToken(),
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify({
            ad_session_id: sessionId,
            nonce_token: nonceToken,
          }),
        });

        let data = {};
        try {
          data = await resp.json();
        } catch (_jsonErr) {
          data = {};
        }

        if (resp.ok && data.status === "ok") {
          hasCompleted = true;
          if (adMode !== "5s" || data.free_access_granted) {
            grantClient24HourAccess(data.free_access_remaining_seconds || 86400);
          }

          let targetUrl = data.redirect_url || fallbackRedirect;
          if (downloadIdParam && !targetUrl.includes("download_id=")) {
            targetUrl = fallbackRedirect;
          }
          setTimeout(() => {
            window.location.href = targetUrl;
          }, 450);
          return;
        }

        if (resp.status === 403 && typeof data.remaining_seconds === "number") {
          remaining = Math.max(1, data.remaining_seconds);
          isCompleting = false;
          updateVisualState();
          startLocalTicker();
          return;
        }
      } catch (_err) {
        // Network or static fallback
      }

      // If running on static edge without backend DB session, unlock 24h after full 30s countdown
      hasCompleted = true;
      if (adMode !== "5s") {
        grantClient24HourAccess(86400);
      }
      setTimeout(() => {
        window.location.href = fallbackRedirect;
      }, 450);
    }

    if (formEl) {
      formEl.addEventListener("submit", (event) => {
        event.preventDefault();
        if (remaining <= 0) {
          triggerAutoCompletion();
        }
      });
    }

    let tickInterval = null;
    function startLocalTicker() {
      if (tickInterval) clearInterval(tickInterval);
      tickInterval = setInterval(() => {
        if (remaining > 0) {
          remaining -= 1;
          updateVisualState();
        } else {
          clearInterval(tickInterval);
          tickInterval = null;
        }
      }, 1000);
    }

    updateVisualState();
    if (remaining > 0) {
      startLocalTicker();
    }

    // Periodically synchronize with server clock when backed by Django AdSession
    if (sessionId && sessionId !== "00000000-0000-0000-0000-000000000001") {
      const syncInterval = setInterval(async () => {
        if (hasCompleted) {
          clearInterval(syncInterval);
          return;
        }
        try {
          const resp = await fetch(`/ads/status/${encodeURIComponent(sessionId)}/`, {
            headers: { Accept: "application/json" },
          });
          if (resp.ok) {
            const data = await resp.json();
            if (typeof data.remaining_seconds === "number") {
              remaining = data.remaining_seconds;
              updateVisualState();
            }
          }
        } catch (_err) {
          // Continue local tick until next server check
        }
      }, 3000);
    }
  }

  document.addEventListener("DOMContentLoaded", initAdCountdownGate);
})();
