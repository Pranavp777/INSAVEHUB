/**
 * INSTASAVE HUB — Production Asynchronous Instagram Video, Reel & Post Downloader Controller
 * Flow:
 * 1. User analyzes URL and clicks Download -> Download starts with progress bar.
 * 2. Right after download completes (if 24-hour free access is not active),
 *    displays the "Unlock 24 Hours Free" popup prompting the user to watch a 30-second ad.
 * 3. If the user watches the 30-second ad until 00:00, grants 24 hours of unlimited ad-free access.
 * 4. If the user dismissed the popup ("Not now") and tries a subsequent download without 24h access,
 *    shows the "Unlock 24 Hours Free" popup before downloading.
 */
(function () {
  "use strict";

  const STORAGE_KEY_24H = "instasave_24h_access";
  const STORAGE_KEY_FIRST_DL = "instasave_first_dl_done";
  const STORAGE_KEY_LAST_DL = "instasave_last_download";

  function getCsrfToken() {
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function formatHMS(totalSeconds) {
    const clamped = Math.max(0, Math.floor(totalSeconds));
    const h = String(Math.floor(clamped / 3600)).padStart(2, "0");
    const m = String(Math.floor((clamped % 3600) / 60)).padStart(2, "0");
    const s = String(clamped % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  function getClient24hState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY_24H);
      if (raw) {
        const parsed = JSON.parse(raw);
        const expiresAtMs = Number(parsed.expires_at_ms || Date.parse(parsed.expires_at || ""));
        if (!isNaN(expiresAtMs) && expiresAtMs > Date.now()) {
          const remainingSec = Math.max(1, Math.floor((expiresAtMs - Date.now()) / 1000));
          return {
            active: true,
            expiresAtMs,
            remainingSeconds: remainingSec,
            formatted: formatHMS(remainingSec),
          };
        }
        localStorage.removeItem(STORAGE_KEY_24H);
      }
    } catch (_e) {
      // Ignore storage errors
    }
    return { active: false, expiresAtMs: 0, remainingSeconds: 0, formatted: "00:00:00" };
  }

  function reconcileAccessWithLocalState(serverAccess) {
    const base = Object.assign(
      {
        state: "STATE_1_FIRST_DOWNLOAD",
        mode: "initial_free",
        label: "Free Download Ready",
        ad_required: false,
        initial_5s_ad_required: false,
        first_download_completed: false,
        has_free_24h: false,
        free_24h_remaining_seconds: 0,
        free_24h_formatted: "00:00:00",
      },
      serverAccess || {}
    );

    const local24h = getClient24hState();
    if (base.has_free_24h && base.free_24h_remaining_seconds > 0) {
      try {
        const expiresAtMs = Date.now() + base.free_24h_remaining_seconds * 1000;
        localStorage.setItem(
          STORAGE_KEY_24H,
          JSON.stringify({
            active: true,
            expires_at_ms: expiresAtMs,
            expires_at: new Date(expiresAtMs).toISOString(),
            remaining_seconds: base.free_24h_remaining_seconds,
          })
        );
      } catch (_e) {}
      return base;
    }

    if (local24h.active) {
      base.state = "STATE_3_FREE_24H_ACTIVE";
      base.mode = "free_24h_pass";
      base.label = "24-HOUR FREE ACCESS";
      base.has_free_24h = true;
      base.ad_required = false;
      base.initial_5s_ad_required = false;
      base.free_24h_remaining_seconds = local24h.remainingSeconds;
      base.free_24h_formatted = local24h.formatted;
      return base;
    }

    let firstDlDone = Boolean(base.first_download_completed || base.ad_required);
    try {
      if (localStorage.getItem(STORAGE_KEY_FIRST_DL) === "1") {
        firstDlDone = true;
      }
    } catch (_e) {}

    if (firstDlDone) {
      base.first_download_completed = true;
      base.ad_required = true;
      base.state = "STATE_2_AD_REQUIRED";
      base.label = "Unlock 24 Hours Free";
    }
    return base;
  }

  function syncGlobalFreeAccessBanner(access) {
    if (!access) return;
    const card = document.getElementById("freeAccessStatusCard");
    const timerEl = document.getElementById("globalFreeAccessTimer");
    if (!card) return;

    if (access.has_free_24h && access.free_24h_remaining_seconds > 0) {
      card.hidden = false;
      card.setAttribute("data-access-state", "STATE_3_FREE_24H_ACTIVE");
      if (timerEl) {
        timerEl.setAttribute(
          "data-free-access-seconds",
          String(access.free_24h_remaining_seconds)
        );
        timerEl.textContent =
          access.free_24h_formatted || formatHMS(access.free_24h_remaining_seconds);
      }
      if (window.InstaSaveAccessEngine && window.InstaSaveAccessEngine.refreshTickers) {
        window.InstaSaveAccessEngine.refreshTickers();
      }
    } else {
      card.hidden = true;
      card.setAttribute("data-access-state", access.state || "STATE_1_FIRST_DOWNLOAD");
    }
  }

  function initUnlock24hModal() {
    return { open: () => {}, close: () => {} };
  }

  function initUrlAnalyzer() {
    const unlockModalCtrl = initUnlock24hModal();
    const form = document.getElementById("instagramAnalyzerForm");
    if (!form) return;

    const urlInput = document.getElementById("instagramUrlInput");
    const toolInput = document.getElementById("instagramToolSlug");
    const urlLabel = document.getElementById("instagramUrlLabel");
    const submitBtn = document.getElementById("analyzeSubmitBtn");
    const pasteBtn = document.getElementById("pasteClipboardBtn");
    const statusBox = document.getElementById("analyzerStatusBox");
    const resultPanel = document.getElementById("analyzerResultPanel");

    const previewContainer = document.getElementById("resPreviewContainer");
    const videoPlayer = document.getElementById("resVideoPlayer");
    const imagePreview = document.getElementById("resImagePreview");
    const playOverlayBtn = document.getElementById("resPreviewPlayOverlay");
    const previewToggleBtn = document.getElementById("resPreviewToggleBtn");
    const fullscreenBtn = document.getElementById("resFullscreenPreviewBtn");
    const actionBtn = document.getElementById("resDownloadActionBtn");

    const progressWrap = document.getElementById("resDownloadProgressWrap");
    const progressBar = document.getElementById("resDownloadProgressBar");
    const progressPct = document.getElementById("resDownloadProgressPct");
    const progressLabel = document.getElementById("resDownloadProgressLabel");

    let activeButtonLabel = submitBtn ? submitBtn.textContent.trim() : "Preview & Download";
    let currentDownloadData = null;
    let currentAccessData = null;
    let isDownloading = false;

    let currentPreviewState = {
      isVideo: false,
      isImage: false,
      previewUrl: "",
      directMediaUrl: "",
      thumbnailUrl: "",
    };

    window.InstaSaveDownloader = {
      onFreeAccessExpired() {
        if (currentAccessData) {
          currentAccessData.has_free_24h = false;
          currentAccessData.free_24h_remaining_seconds = 0;
          currentAccessData.ad_required = true;
          currentAccessData.state = "STATE_4_EXPIRED";
          currentAccessData.label = "24-Hour Access Expired — Ad Required";
          updateActionButtonsForAccess();
        }
      },
    };

    // 1. Interactive Downloader Mode Tabs (Video, Reel, Post, Photo, Profile)
    const modeTabs = document.querySelectorAll("[data-downloader-tab]");
    modeTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        modeTabs.forEach((t) => {
          t.classList.remove("is-active");
          t.setAttribute("aria-selected", "false");
        });
        tab.classList.add("is-active");
        tab.setAttribute("aria-selected", "true");

        const slug = tab.getAttribute("data-downloader-tab") || "";
        const placeholder = tab.getAttribute("data-placeholder") || "";
        const labelText = tab.getAttribute("data-label") || "";
        const btnText = tab.getAttribute("data-button-text") || "Preview & Download";

        activeButtonLabel = btnText;
        if (toolInput) toolInput.value = slug;
        if (urlInput && placeholder) urlInput.placeholder = placeholder;
        if (urlLabel && labelText) urlLabel.textContent = labelText;
        if (submitBtn && !submitBtn.disabled) submitBtn.textContent = btnText;
      });
    });

    // 2. One-Click Clipboard Paste Button
    if (pasteBtn && urlInput) {
      pasteBtn.addEventListener("click", async () => {
        if (navigator.clipboard && navigator.clipboard.readText) {
          try {
            const clipText = await navigator.clipboard.readText();
            if (clipText && clipText.trim()) {
              urlInput.value = clipText.trim();
              urlInput.focus();
              hideError();
            }
          } catch (_err) {
            urlInput.focus();
          }
        } else {
          urlInput.focus();
        }
      });
    }

    // 3. Video Preview Player Controls & Event Binding
    function toggleVideoPlayback() {
      if (!currentPreviewState.isVideo || !videoPlayer) {
        if (currentPreviewState.previewUrl) {
          window.open(currentPreviewState.previewUrl, "_blank", "noopener");
        }
        return;
      }

      if (videoPlayer.paused || videoPlayer.ended) {
        videoPlayer.play().catch(() => {
          if (
            currentPreviewState.directMediaUrl &&
            videoPlayer.src !== currentPreviewState.directMediaUrl
          ) {
            videoPlayer.src = currentPreviewState.directMediaUrl;
            videoPlayer.play().catch(() => {});
          }
        });
      } else {
        videoPlayer.pause();
      }
    }

    if (playOverlayBtn) {
      playOverlayBtn.addEventListener("click", (e) => {
        e.preventDefault();
        toggleVideoPlayback();
      });
    }

    if (previewToggleBtn) {
      previewToggleBtn.addEventListener("click", (e) => {
        e.preventDefault();
        if (currentPreviewState.isVideo) {
          toggleVideoPlayback();
        } else if (currentPreviewState.previewUrl) {
          window.open(currentPreviewState.previewUrl, "_blank", "noopener");
        }
      });
    }

    if (fullscreenBtn) {
      fullscreenBtn.addEventListener("click", (e) => {
        e.preventDefault();
        const targetEl =
          currentPreviewState.isVideo && videoPlayer && !videoPlayer.hidden
            ? videoPlayer
            : previewContainer;
        if (!targetEl) return;

        if (targetEl.requestFullscreen) {
          targetEl.requestFullscreen().catch(() => {});
        } else if (targetEl.webkitEnterFullscreen) {
          targetEl.webkitEnterFullscreen();
        } else if (targetEl.webkitRequestFullscreen) {
          targetEl.webkitRequestFullscreen();
        }
      });
    }

    if (videoPlayer) {
      videoPlayer.addEventListener("play", () => {
        if (previewContainer) previewContainer.classList.add("is-playing");
        if (previewToggleBtn) previewToggleBtn.textContent = "Pause Preview";
        const badge = document.getElementById("resPreviewStatusBadge");
        if (badge) badge.textContent = "PLAYING";
      });

      videoPlayer.addEventListener("pause", () => {
        if (previewContainer) previewContainer.classList.remove("is-playing");
        if (previewToggleBtn && currentPreviewState.isVideo) {
          previewToggleBtn.textContent = "Preview Video";
        }
        const badge = document.getElementById("resPreviewStatusBadge");
        if (badge) badge.textContent = "PAUSED";
      });

      videoPlayer.addEventListener("ended", () => {
        if (previewContainer) previewContainer.classList.remove("is-playing");
        if (previewToggleBtn && currentPreviewState.isVideo) {
          previewToggleBtn.textContent = "Replay Preview";
        }
        const badge = document.getElementById("resPreviewStatusBadge");
        if (badge) badge.textContent = "LIVE PREVIEW";
      });

      videoPlayer.addEventListener("error", () => {
        if (
          currentPreviewState.directMediaUrl &&
          videoPlayer.getAttribute("src") !== currentPreviewState.directMediaUrl
        ) {
          videoPlayer.src = currentPreviewState.directMediaUrl;
        }
      });
    }

    if (imagePreview) {
      imagePreview.addEventListener("error", () => {
        if (
          currentPreviewState.thumbnailUrl &&
          imagePreview.getAttribute("src") !== currentPreviewState.thumbnailUrl
        ) {
          imagePreview.src = currentPreviewState.thumbnailUrl;
        }
      });
    }

    // 4. Clean Direct Download Execution
    function startDirectDownloadWithProgress(executeUrl) {
      if (!executeUrl || isDownloading) return;
      isDownloading = true;

      if (progressWrap) progressWrap.hidden = false;
      if (progressBar) progressBar.style.width = "15%";
      if (progressPct) progressPct.textContent = "15%";
      if (progressLabel) progressLabel.textContent = "CONNECTING TO STREAM...";

      let pct = 15;
      const timer = setInterval(() => {
        pct = Math.min(92, pct + Math.floor(Math.random() * 18) + 12);
        if (progressBar) progressBar.style.width = `${pct}%`;
        if (progressPct) progressPct.textContent = `${pct}%`;
      }, 120);

      setTimeout(() => {
        clearInterval(timer);
        if (progressBar) progressBar.style.width = "100%";
        if (progressPct) progressPct.textContent = "100%";
        if (progressLabel) progressLabel.textContent = "DOWNLOAD COMPLETE";

        // Trigger the direct media attachment download
        const link = document.createElement("a");
        link.href = executeUrl;
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        setTimeout(() => {
          if (link.parentNode) link.parentNode.removeChild(link);
        }, 1000);

        setTimeout(() => {
          isDownloading = false;
        }, 900);
      }, 600);
    }

    if (actionBtn) {
      actionBtn.addEventListener("click", (event) => {
        if (!currentDownloadData) return;
        event.preventDefault();
        try {
          sessionStorage.setItem(
            STORAGE_KEY_LAST_DL,
            JSON.stringify(currentDownloadData)
          );
        } catch (_e) {}
        startDirectDownloadWithProgress(currentDownloadData.execute_url);
      });
    }

    // 5. Form Submission -> Asynchronous Fetch API Analysis
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!urlInput) return;

      const rawUrl = urlInput.value.trim();
      const toolSlug = toolInput ? toolInput.value.trim() : "";

      if (!rawUrl) {
        renderError("Please paste a public Instagram Post, Reel, or Video URL.");
        return;
      }

      setLoading(true);
      hideError();

      try {
        const response = await fetch(form.getAttribute("action") || "/api/downloads/analyze/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-CSRFToken": getCsrfToken(),
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify({
            url: rawUrl,
            tool_slug: toolSlug,
          }),
        });

        const data = await response.json();

        if (!response.ok || data.status !== "ok") {
          renderError(
            data.message || "Unable to analyze the provided Instagram URL. Please verify the link is public."
          );
          if (resultPanel) resultPanel.hidden = true;
          return;
        }

        const mergedAccess = reconcileAccessWithLocalState(data.access);
        populateResultPanel(data.download, mergedAccess);
      } catch (_err) {
        renderError("Network communication error while contacting the media extraction engine.");
      } finally {
        setLoading(false);
      }
    });

    function setLoading(isLoading) {
      if (!submitBtn) return;
      submitBtn.disabled = isLoading;
      submitBtn.textContent = isLoading ? "Extracting Stream..." : activeButtonLabel;
    }

    function renderError(msg) {
      if (!statusBox) return;
      statusBox.hidden = false;
      statusBox.className = "glass-alert glass-alert-error";
      statusBox.textContent = msg;
    }

    function hideError() {
      if (!statusBox) return;
      statusBox.hidden = true;
      statusBox.textContent = "";
    }

    function updateActionButtonsForAccess() {
      if (!currentDownloadData || !currentAccessData) return;
      const dl = currentDownloadData;
      const access = currentAccessData;

      const accessStatusEl = document.getElementById("resAccessStatus");
      if (accessStatusEl) {
        accessStatusEl.textContent = access.has_free_24h
          ? `24-HOUR FREE ACCESS (${access.free_24h_formatted || "Active"})`
          : access.label || "Ready";
      }

      syncGlobalFreeAccessBanner(access);

      const adNotice = document.getElementById("resAdRequirementNotice");
      if (!actionBtn) return;

      const isMetadata = dl.content_type === "metadata";
      const isVideo = currentPreviewState.isVideo;
      const isImage = currentPreviewState.isImage;

      let baseDownloadLabel = "Download";
      if (isMetadata) {
        baseDownloadLabel = "Download JSON";
      } else if (isVideo) {
        baseDownloadLabel = "Download Video (MP4)";
      } else if (isImage) {
        baseDownloadLabel = "Download Photo (JPG)";
      }

      actionBtn.href = dl.execute_url;
      actionBtn.textContent = baseDownloadLabel;
      if (adNotice) adNotice.hidden = true;
    }

    function populateResultPanel(dl, access) {
      if (!resultPanel || !dl) return;
      currentDownloadData = dl;
      currentAccessData = reconcileAccessWithLocalState(access);

      try {
        sessionStorage.setItem(STORAGE_KEY_LAST_DL, JSON.stringify(dl));
      } catch (_e) {}

      resultPanel.hidden = false;
      if (progressWrap) progressWrap.hidden = true;

      const setText = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val || "-";
      };

      setText("resMediaTitle", dl.media_title);
      setText("resContentType", dl.content_type_label);
      setText("resMediaFormat", dl.media_format);
      setText("resResolution", dl.resolution);
      setText("resDuration", dl.duration_label || "00:15 (HD)");
      setText("resFileSize", dl.file_size_label);
      setText("resShortcode", dl.shortcode);
      setText("resAuthorHandle", dl.author_handle);

      const meta = dl.preview_metadata || {};
      setText("resPreviewCodec", meta.video_codec || dl.media_format);
      setText("resPreviewAspect", meta.aspect_ratio || dl.resolution);
      setText("resPreviewShortcode", dl.shortcode);

      const isVideo = Boolean(
        meta.is_video ||
          dl.content_type === "video" ||
          dl.content_type === "reel" ||
          meta.ext === "mp4"
      );
      const isMetadata = dl.content_type === "metadata";
      const isImage = !isVideo && !isMetadata;

      const previewStreamUrl =
        dl.preview_url ||
        (dl.execute_url
          ? `${dl.execute_url}${dl.execute_url.includes("?") ? "&" : "?"}preview=1`
          : meta.direct_media_url || "");

      currentPreviewState = {
        isVideo,
        isImage,
        previewUrl: previewStreamUrl,
        directMediaUrl: meta.direct_media_url || "",
        thumbnailUrl: meta.thumbnail_url || "",
      };

      if (previewContainer) {
        previewContainer.classList.remove("is-playing");
        if (meta.thumbnail_url) {
          previewContainer.style.backgroundImage = `linear-gradient(180deg, rgba(5, 12, 32, 0.35) 0%, rgba(5, 12, 32, 0.72) 100%), url("${meta.thumbnail_url}")`;
          previewContainer.style.backgroundSize = "cover";
          previewContainer.style.backgroundPosition = "center";
        } else {
          previewContainer.style.backgroundImage = "";
        }
      }

      if (isVideo) {
        if (imagePreview) {
          imagePreview.hidden = true;
          imagePreview.removeAttribute("src");
        }
        if (videoPlayer) {
          videoPlayer.pause();
          videoPlayer.hidden = false;
          if (meta.thumbnail_url) {
            videoPlayer.poster = meta.thumbnail_url;
          } else {
            videoPlayer.removeAttribute("poster");
          }
          videoPlayer.src = previewStreamUrl;
          videoPlayer.load();
        }
        if (playOverlayBtn) playOverlayBtn.hidden = false;
        if (previewToggleBtn) {
          previewToggleBtn.hidden = false;
          previewToggleBtn.textContent = "Preview Video";
        }
        if (fullscreenBtn) fullscreenBtn.hidden = false;
        setText("resPreviewStatusBadge", "LIVE PREVIEW");
      } else if (isImage) {
        if (videoPlayer) {
          videoPlayer.pause();
          videoPlayer.hidden = true;
          videoPlayer.removeAttribute("src");
        }
        if (imagePreview) {
          imagePreview.hidden = false;
          imagePreview.src = previewStreamUrl || meta.thumbnail_url || meta.direct_media_url || "";
        }
        if (playOverlayBtn) playOverlayBtn.hidden = true;
        if (previewToggleBtn) {
          previewToggleBtn.hidden = false;
          previewToggleBtn.textContent = "Preview Photo";
        }
        if (fullscreenBtn) fullscreenBtn.hidden = false;
        setText("resPreviewStatusBadge", "HD PHOTO");
      } else {
        if (videoPlayer) {
          videoPlayer.pause();
          videoPlayer.hidden = true;
          videoPlayer.removeAttribute("src");
        }
        if (imagePreview) {
          imagePreview.hidden = true;
          imagePreview.removeAttribute("src");
        }
        if (playOverlayBtn) playOverlayBtn.hidden = true;
        if (previewToggleBtn) {
          previewToggleBtn.hidden = false;
          previewToggleBtn.textContent = "Preview JSON";
        }
        if (fullscreenBtn) fullscreenBtn.hidden = true;
        setText("resPreviewStatusBadge", "JSON MANIFEST");
      }

      updateActionButtonsForAccess();
      resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // 6. Auto-hydrate Result Panel & Trigger Auto-Download when returning from 30s Ad Gate
    const bootstrapEl = document.getElementById("activeDownloadBootstrap");
    if (bootstrapEl && bootstrapEl.textContent) {
      try {
        const payload = JSON.parse(bootstrapEl.textContent);
        if (payload && payload.download) {
          const mergedAccess = reconcileAccessWithLocalState(payload.access);
          populateResultPanel(payload.download, mergedAccess);
          if (payload.auto_download && payload.download.execute_url) {
            setTimeout(() => {
              startDirectDownloadWithProgress(
                payload.download.execute_url,
                !mergedAccess.has_free_24h
              );
            }, 350);
          }
          return;
        }
      } catch (_err) {
        // Ignore malformed bootstrap JSON
      }
    }

    // Also support Cloudflare static edge return (?unlocked_24h=1 or ?auto_download=1)
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get("unlocked_24h") === "1" || params.get("auto_download") === "1") {
        const localAccess = reconcileAccessWithLocalState(null);
        syncGlobalFreeAccessBanner(localAccess);

        const savedDlRaw = sessionStorage.getItem(STORAGE_KEY_LAST_DL);
        if (savedDlRaw) {
          const savedDl = JSON.parse(savedDlRaw);
          if (savedDl && savedDl.execute_url) {
            if (urlInput && savedDl.source_url && !urlInput.value) {
              urlInput.value = savedDl.source_url;
            }
            populateResultPanel(savedDl, localAccess);
            if (params.get("auto_download") === "1") {
              setTimeout(() => {
                startDirectDownloadWithProgress(savedDl.execute_url, false);
              }, 350);
            }
          }
        }
      }
    } catch (_e) {}
  }

  document.addEventListener("DOMContentLoaded", initUrlAnalyzer);
})();
