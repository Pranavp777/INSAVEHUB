/**
 * INSTASAVE HUB — Progressive Web App (PWA) Engine & Installation Controller
 * Handles native beforeinstallprompt, multi-platform installation guidance,
 * direct web shortcut launcher downloads, service worker registration,
 * and strict standalone mode hiding.
 */
(function () {
  "use strict";

  let deferredPrompt = null;
  let isInstalled = false;

  /**
   * Determine whether the app is currently running in installed/standalone mode.
   * Checks W3C standard matchMedia and iOS Safari navigator.standalone.
   */
  function detectStandalone() {
    try {
      if (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) {
        return true;
      }
      if (window.navigator && window.navigator.standalone === true) {
        return true;
      }
      const search = window.location.search || "";
      if (search.includes("source=pwa") && window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) {
        return true;
      }
    } catch (_e) {}
    return false;
  }

  /**
   * Hide all PWA install triggers and modals across the application shell.
   */
  function applyInstalledState() {
    isInstalled = true;
    if (document.documentElement) {
      document.documentElement.classList.add("pwa-installed");
    }
    if (document.body) {
      document.body.classList.add("pwa-installed");
    }

    const triggers = document.querySelectorAll(
      ".pwa-install-trigger, [data-install-app-trigger], #installAppNavBtn, #installAppMobileBtn, #installAppHeroBtn"
    );
    triggers.forEach((el) => {
      el.style.setProperty("display", "none", "important");
      el.setAttribute("aria-hidden", "true");
    });

    const modal = document.getElementById("appInstallModal");
    if (modal) {
      modal.hidden = true;
      modal.style.setProperty("display", "none", "important");
    }
  }

  /**
   * Check installation state and synchronize UI.
   */
  function syncInstallState() {
    if (detectStandalone()) {
      applyInstalledState();
      return true;
    }
    return false;
  }

  // Run immediate anti-flicker check
  syncInstallState();

  // Watch for display mode changes (e.g. when app transitions to standalone window)
  try {
    const standaloneMedia = window.matchMedia("(display-mode: standalone)");
    if (standaloneMedia && standaloneMedia.addEventListener) {
      standaloneMedia.addEventListener("change", (e) => {
        if (e.matches) syncInstallState();
      });
    }
  } catch (_e) {}

  // Lifecycle state checks: navigation, visibility, return from app store / prompt
  window.addEventListener("pageshow", syncInstallState);
  window.addEventListener("popstate", syncInstallState);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      syncInstallState();
    }
  });
  window.addEventListener("focus", syncInstallState);

  // Native beforeinstallprompt capture (Chromium, Edge, Android)
  window.addEventListener("beforeinstallprompt", (event) => {
    if (detectStandalone()) return;

    event.preventDefault();
    deferredPrompt = event;

    // Reveal the 1-click install banner inside the modal
    const nativeWrap = document.getElementById("nativeInstallPromptWrap");
    if (nativeWrap) {
      nativeWrap.hidden = false;
      nativeWrap.style.removeProperty("display");
    }
    const nativeBtn = document.getElementById("triggerNativeInstallBtn");
    if (nativeBtn) {
      nativeBtn.removeAttribute("disabled");
    }
    const statusText = document.getElementById("nativeInstallStatusText");
    if (statusText) {
      statusText.textContent = "Direct 1-click installation is ready for your browser.";
    }
  });

  // App installed event: fired when installation completes
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    applyInstalledState();
  });

  /**
   * Register the root-scoped Service Worker for asset caching and offline support.
   */
  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;

    const swUrl = "/service-worker.js";
    const register = () => {
      navigator.serviceWorker
        .register(swUrl)
        .then((registration) => {
          registration.addEventListener("updatefound", () => {
            const installingWorker = registration.installing;
            if (installingWorker) {
              installingWorker.addEventListener("statechange", () => {
                if (
                  installingWorker.state === "installed" &&
                  navigator.serviceWorker.controller
                ) {
                  // Active service worker updated
                }
              });
            }
          });
        })
        .catch(() => {
          navigator.serviceWorker.register("/sw.js").catch(() => {});
        });
    };

    if (document.readyState === "complete" || document.readyState === "interactive") {
      register();
    } else {
      window.addEventListener("load", register);
    }
  }

  /**
   * Generate and trigger a direct file download for an Internet Shortcut (.url).
   * Works on Windows, macOS, and desktop environments so users can download
   * an app launcher file directly to their device.
   */
  function downloadAppShortcut() {
    const origin = window.location.origin || (window.location.protocol + "//" + window.location.host);
    const targetUrl = origin + "/?source=pwa";
    const iconUrl = origin + "/static/images/icon-512.png";

    const shortcutContent =
      "[InternetShortcut]\r\n" +
      "URL=" + targetUrl + "\r\n" +
      "IconFile=" + iconUrl + "\r\n" +
      "IconIndex=0\r\n" +
      "[{000214A0-0000-0000-C000-000000000046}]\r\n" +
      "Prop3=19,0\r\n";

    const blob = new Blob([shortcutContent], { type: "application/octet-stream" });
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = "INSTASAVE-HUB.url";
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();

    setTimeout(() => {
      if (link.parentNode) link.parentNode.removeChild(link);
      URL.revokeObjectURL(blobUrl);
    }, 1500);
  }

  /**
   * Launch native iOS Safari share sheet where 'Add to Home Screen' is located.
   */
  async function triggerIosShare() {
    const origin = window.location.origin || (window.location.protocol + "//" + window.location.host);
    if (navigator.share) {
      try {
        await navigator.share({
          title: "INSTASAVE HUB — 1080p Instagram Downloader",
          text: "Download Instagram Videos, Reels, and Photos in original 1080p HD",
          url: origin + "/?source=pwa",
        });
      } catch (_e) {
        // User dismissed share sheet
      }
    } else {
      // Fallback instruction highlight
      const shareIcon = document.querySelector("#installStepIos .install-step-icon");
      if (shareIcon) {
        shareIcon.style.outline = "2px solid #3B82F6";
        setTimeout(() => {
          shareIcon.style.outline = "none";
        }, 2000);
      }
    }
  }

  /**
   * Initialize platform-specific modal instruction tabs and detection.
   */
  function initInstallModal() {
    const modal = document.getElementById("appInstallModal");
    const closeBtn = document.getElementById("closeAppInstallModal");
    const tabBtns = document.querySelectorAll("#installPlatformTabs .install-tab-btn");
    const panes = {
      ios: document.getElementById("installStepIos"),
      android: document.getElementById("installStepAndroid"),
      desktop: document.getElementById("installStepDesktop"),
      mac: document.getElementById("installStepMac"),
    };
    const inAppAlert = document.getElementById("inAppBrowserAlert");

    const ua = navigator.userAgent || "";
    const isIos = /iphone|ipad|ipod/i.test(ua);
    const isAndroid = /android/i.test(ua);
    const isMac = /macintosh|mac os x/i.test(ua) && !isIos;
    const isInApp = /instagram|fbav|fban|line|micromessenger|tiktok|bytedance/i.test(ua);

    if (isInApp && inAppAlert) {
      inAppAlert.hidden = false;
    }

    function switchTab(targetKey) {
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
        if (target) switchTab(target);
      });
    });

    let defaultPlatform = "desktop";
    if (isIos) defaultPlatform = "ios";
    else if (isAndroid) defaultPlatform = "android";
    else if (isMac) defaultPlatform = "mac";
    switchTab(defaultPlatform);

    function openModal() {
      if (syncInstallState()) return;
      if (modal) {
        switchTab(defaultPlatform);
        modal.hidden = false;
        modal.style.removeProperty("display");
      }
    }

    function closeModal() {
      if (modal) modal.hidden = true;
    }

    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (modal) {
      modal.addEventListener("click", (e) => {
        if (e.target === modal) closeModal();
      });
    }
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal && !modal.hidden) closeModal();
    });

    // Bind iOS share button
    const iosShareBtn = document.getElementById("triggerIosShareBtn");
    if (iosShareBtn) {
      iosShareBtn.addEventListener("click", (e) => {
        e.preventDefault();
        triggerIosShare();
      });
    }

    // Bind shortcut download buttons
    const shortcutBtns = document.querySelectorAll(".download-shortcut-btn");
    shortcutBtns.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        downloadAppShortcut();
      });
    });

    return { openModal, closeModal, defaultPlatform, switchTab };
  }

  /**
   * Handle user clicking on an Install App button.
   */
  async function handleInstallClick(buttonEl, modalController) {
    if (syncInstallState()) return;

    // If native prompt is available, trigger it directly
    if (deferredPrompt) {
      const originalHtml = buttonEl.innerHTML;
      const span = buttonEl.querySelector("span");
      const originalText = span ? span.textContent : buttonEl.textContent;

      try {
        buttonEl.classList.add("btn-install-loading");
        if (span) span.textContent = "Installing...";

        const promptEvent = deferredPrompt;
        deferredPrompt = null; // Clear immediately so it cannot be double-called

        promptEvent.prompt();
        const choiceResult = await promptEvent.userChoice;

        if (choiceResult && choiceResult.outcome === "accepted") {
          if (modalController) modalController.closeModal();
          applyInstalledState();
          return;
        } else {
          // User dismissed prompt; keep button available
          buttonEl.classList.remove("btn-install-loading");
          if (span) span.textContent = originalText;
          else buttonEl.innerHTML = originalHtml;
          return;
        }
      } catch (err) {
        console.warn("[PWA Install] Prompt error:", err);
        buttonEl.classList.remove("btn-install-loading");
        if (span) span.textContent = originalText;
        else buttonEl.innerHTML = originalHtml;
      }
    }

    // If native prompt is unavailable (iOS Safari, Mac Safari, unsupported browser),
    // open the informative step-by-step modal guide
    if (modalController) {
      modalController.openModal();
    }
  }

  /**
   * Bind install triggers across the entire page.
   */
  function bindInstallTriggers(modalController) {
    if (syncInstallState()) return;

    const triggers = document.querySelectorAll(
      ".pwa-install-trigger, [data-install-app-trigger], #installAppNavBtn, #installAppMobileBtn, #installAppHeroBtn"
    );

    triggers.forEach((btn) => {
      btn.onclick = null;
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        handleInstallClick(btn, modalController);
      });
    });

    const nativeBtn = document.getElementById("triggerNativeInstallBtn");
    if (nativeBtn) {
      nativeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        handleInstallClick(nativeBtn, modalController);
      });
    }
  }

  // Initialize on DOM ready
  function init() {
    if (syncInstallState()) return;
    registerServiceWorker();
    const modalController = initInstallModal();
    bindInstallTriggers(modalController);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Export for testing & external controllers
  window.PwaInstallEngine = {
    detectStandalone,
    syncInstallState,
    applyInstalledState,
    downloadAppShortcut,
    triggerIosShare,
    getDeferredPrompt: () => deferredPrompt,
  };
})();
