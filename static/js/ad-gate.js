/**
 * InSave Hub — Server-Synchronized 30-Second Advertisement Countdown Controller
 * Never trusts client-only manipulation: verifies remaining seconds against
 * the server clock and submits cryptographic nonce upon completion.
 */
(function () {
  "use strict";

  function initAdCountdownGate() {
    const stage = document.getElementById("adCountdownStage");
    if (!stage) return;

    const sessionId = stage.getAttribute("data-session-id") || "";
    const totalDuration = parseInt(stage.getAttribute("data-total-seconds") || "30", 10);
    let remaining = parseInt(stage.getAttribute("data-remaining-seconds") || "30", 10);

    const numberEl = document.getElementById("adCountdownNumber");
    const progressEl = document.getElementById("adProgressBar");
    const unlockBtn = document.getElementById("adUnlockSubmitBtn");
    const stateLabel = document.getElementById("adStateTelemetryLabel");

    function updateVisualState() {
      if (numberEl) {
        numberEl.textContent = String(Math.max(0, remaining)).padStart(2, "0");
      }
      if (progressEl && totalDuration > 0) {
        const elapsed = Math.max(0, totalDuration - remaining);
        const pct = Math.min(100, Math.round((elapsed / totalDuration) * 100));
        progressEl.style.width = `${pct}%`;
      }
      if (remaining <= 0) {
        if (unlockBtn) {
          unlockBtn.disabled = false;
          unlockBtn.textContent = "Unlock Download & Activate 24-Hour Free Access";
        }
        if (stateLabel) {
          stateLabel.textContent = "SERVER TIMER VERIFIED — READY TO UNLOCK";
        }
      } else {
        if (unlockBtn) {
          unlockBtn.disabled = true;
          unlockBtn.textContent = `Verification In Progress (${remaining}s)`;
        }
      }
    }

    updateVisualState();

    const tickInterval = setInterval(() => {
      if (remaining > 0) {
        remaining -= 1;
        updateVisualState();
      } else {
        clearInterval(tickInterval);
      }
    }, 1000);

    // Periodically synchronize with server clock to prevent drift
    if (sessionId) {
      const syncInterval = setInterval(async () => {
        if (remaining <= 0) {
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
      }, 5000);
    }
  }

  document.addEventListener("DOMContentLoaded", initAdCountdownGate);
})();
