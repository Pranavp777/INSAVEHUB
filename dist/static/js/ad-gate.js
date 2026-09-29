/**
 * INSTASAVE HUB — Server-Synchronized 5-Second & 30-Second Advertisement Countdown Controller
 * Supports:
 * - State 1: 5-second initial download advertisement -> auto-redirect & start download
 * - State 2: 30-second 24-hour unlock advertisement -> "Access unlocked" -> grant 24h pass & start download
 * Never trusts client-only manipulation: verifies remaining seconds against the server clock.
 */
(function () {
  "use strict";

  const RING_RADIUS = 78;
  const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

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

  function initAdCountdownGate() {
    const stage = document.getElementById("adCountdownStage");
    if (!stage) return;

    const sessionId = stage.getAttribute("data-session-id") || "";
    const adMode = stage.getAttribute("data-ad-mode") || "30s";
    const completeUrl = stage.getAttribute("data-complete-url") || "/ads/complete/";
    const totalDuration = Math.max(
      1,
      parseInt(stage.getAttribute("data-total-seconds") || (adMode === "5s" ? "5" : "30"), 10)
    );
    let remaining = parseInt(
      stage.getAttribute("data-remaining-seconds") || String(totalDuration),
      10
    );

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
          unlockBtn.textContent = "Access unlocked — Starting Download...";
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
      if (!sessionId || !nonceToken) {
        if (formEl) formEl.submit();
        return;
      }

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

        const data = await resp.json();

        if (resp.ok && data.status === "ok") {
          hasCompleted = true;
          try {
            if (data.free_access_granted && data.free_access_expires_at) {
              localStorage.setItem(
                "instasave_24h_access",
                JSON.stringify({
                  active: true,
                  expires_at: data.free_access_expires_at,
                  remaining_seconds: data.free_access_remaining_seconds || 86400,
                })
              );
            }
          } catch (_storageErr) {
            // Ignore storage quota errors
          }

          const targetUrl = data.redirect_url || "/downloads/";
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
        // Fallback to standard form POST if fetch fails
        if (formEl) {
          formEl.submit();
          return;
        }
      }

      isCompleting = false;
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

    // Periodically synchronize with server clock to prevent client drift or tampering
    if (sessionId) {
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
