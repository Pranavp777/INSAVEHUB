/**
 * INSTASAVE HUB — Progressive Web App (PWA) Engine & Installation Controller
 * Handles native beforeinstallprompt, multi-platform installation guidance,
 * service worker registration, and strict standalone state hiding.
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
      if (document.referrer && document.referrer.includes("android-app://")) {
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
    // If already in standalone mode, suppress prompt
    if (syncInstallState()) return;

    event.preventDefault();
    deferredPrompt = event;

    // Notify any active buttons or modal elements
    const statusText = document.getElementById("nativeInstallStatusText");
    if (statusText) {
      statusText.textContent = "One-click native app installation ready for your browser.";
    }
    const nativeBtn = document.getElementById("triggerNativeInstallBtn");
    if (nativeBtn) {
      nativeBtn.hidden = false;
      nativeBtn.removeAttribute("disabled");
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
          // Check for service worker updates
          registration.addEventListener("updatefound", () => {
            const installingWorker = registration.installing;
            if (installingWorker) {
              installingWorker.addEventListener("statechange", () => {
                if (
                  installingWorker.state === "installed" &&
                  navigator.serviceWorker.controller
                ) {
                  // New version available
                }
              });
            }
          });
        })
        .catch(() => {
          // Fallback to /sw.js route
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
        // Set loading state
        buttonEl.classList.add("btn-install-loading");
        if (span) span.textContent = "Installing...";

        deferredPrompt.prompt();
        const choiceResult = await deferredPrompt.userChoice;

        if (choiceResult && choiceResult.outcome === "accepted") {
          // User accepted prompt; appinstalled event will hide buttons
          deferredPrompt = null;
          if (modalController) modalController.closeModal();
          applyInstalledState();
          return;
        } else {
          // User cancelled / dismissed the prompt
          // Requirement: Keep the button available; do NOT permanently hide it
          buttonEl.classList.remove("btn-install-loading");
          if (span) span.textContent = originalText;
          else buttonEl.innerHTML = originalHtml;
          return;
        }
      } catch (_err) {
        // Prompt error; restore button and fallback to modal
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
      // Remove any previously bound listeners
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
    getDeferredPrompt: () => deferredPrompt,
  };
})();
