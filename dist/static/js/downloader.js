/**
 * INSTASAVE HUB — Production Asynchronous Instagram Video, Reel & Post Downloader Controller
 * Implements:
 * - Interactive downloader mode tabs & one-click clipboard paste
 * - Live 1080p HD Video & Photo stream preview player with fullscreen
 * - 4-State Smart Advertisement & 24-Hour Ad-Free Access Lifecycle:
 *   State 1 (First Download): 5-second advertisement page -> auto-redirect & start download
 *   State 2 (Second+ Download): "Unlock 24 Hours Free" glass popup -> 30-second ad page
 *   State 3 (24h Free Access Active): Instant ad-free downloads + live 24h status card
 *   State 4 (24h Expired): Auto-reset to advertisement flow
 */
(function () {
  "use strict";

  function getCsrfToken() {
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function syncGlobalFreeAccessBanner(access) {
    if (!access) return;
    const card = document.getElementById("freeAccessStatusCard");
    const timerEl = document.getElementById("globalFreeAccessTimer");
    if (!card) return;

    if (access.has_free_24h && access.free_24h_remaining_seconds > 0) {
      card.hidden = false;
      card.setAttribute("data-access-state", "STATE_3");
      if (timerEl) {
        timerEl.setAttribute(
          "data-free-access-seconds",
          String(access.free_24h_remaining_seconds)
        );
        if (access.free_24h_formatted) {
          timerEl.textContent = access.free_24h_formatted;
        }
      }
      if (window.InstaSaveAccessEngine && window.InstaSaveAccessEngine.refreshTickers) {
        window.InstaSaveAccessEngine.refreshTickers();
      }
    } else {
      card.hidden = true;
      card.setAttribute("data-access-state", access.state || "STATE_1");
    }
  }

  function initUnlock24hModal() {
    const modal = document.getElementById("unlock24hModal");
    const dismissBtn = document.getElementById("unlock24hDismissBtn");
    if (!modal) return { open: () => {}, close: () => {} };

    function openModal(adGateUrl) {
      const watchBtn = document.getElementById("unlock24hWatchAdBtn");
      if (watchBtn && adGateUrl) {
        watchBtn.setAttribute("href", adGateUrl);
      }
      modal.hidden = false;
      requestAnimationFrame(() => {
        modal.classList.add("is-open");
      });
    }

    function closeModal() {
      modal.classList.remove("is-open");
      modal.hidden = true;
    }

    if (dismissBtn) {
      dismissBtn.addEventListener("click", closeModal);
    }

    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        closeModal();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.hidden) {
        closeModal();
      }
    });

    return { open: openModal, close: closeModal };
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

    // Expose a hook so orbit-engine.js can notify downloader when 24h access expires
    window.InstaSaveDownloader = {
      onFreeAccessExpired() {
        if (currentAccessData) {
          currentAccessData.has_free_24h = false;
          currentAccessData.free_24h_remaining_seconds = 0;
          currentAccessData.ad_required = Boolean(currentAccessData.first_download_completed);
          currentAccessData.initial_5s_ad_required = !currentAccessData.first_download_completed;
          currentAccessData.state = "STATE_4";
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

    // 4. Smart Download Button Click Handler (4-State Ad & 24h Access Flow)
    function startDirectDownloadWithProgress(executeUrl) {
      if (!executeUrl || isDownloading) return;
      isDownloading = true;

      if (progressWrap) progressWrap.hidden = false;
      if (progressBar) progressBar.style.width = "12%";
      if (progressPct) progressPct.textContent = "12%";
      if (progressLabel) progressLabel.textContent = "PREPARING HIGH-SPEED STREAM...";

      let pct = 12;
      const timer = setInterval(() => {
        pct = Math.min(92, pct + Math.floor(Math.random() * 18) + 10);
        if (progressBar) progressBar.style.width = `${pct}%`;
        if (progressPct) progressPct.textContent = `${pct}%`;
      }, 140);

      setTimeout(() => {
        clearInterval(timer);
        if (progressBar) progressBar.style.width = "100%";
        if (progressPct) progressPct.textContent = "100%";
        if (progressLabel) progressLabel.textContent = "DOWNLOAD STARTED";

        // Trigger the server-validated attachment download
        const link = document.createElement("a");
        link.href = executeUrl;
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        setTimeout(() => {
          if (link.parentNode) link.parentNode.removeChild(link);
        }, 1000);

        // Update local state after first download completes (if 24h pass is not active)
        if (currentAccessData && !currentAccessData.has_free_24h) {
          currentAccessData.first_download_completed = true;
          currentAccessData.initial_5s_ad_required = false;
          currentAccessData.ad_required = true;
          currentAccessData.state = "STATE_2";
          currentAccessData.label = "Unlock 24 Hours Free (30s Ad)";
          setTimeout(() => {
            updateActionButtonsForAccess();
          }, 1200);
        }

        setTimeout(() => {
          isDownloading = false;
        }, 900);
      }, 650);
    }

    if (actionBtn) {
      actionBtn.addEventListener("click", (event) => {
        if (!currentDownloadData || !currentAccessData) return;

        // State 3: 24-Hour Free Access Active -> Immediate download, no ads or popups
        if (currentAccessData.has_free_24h) {
          event.preventDefault();
          startDirectDownloadWithProgress(currentDownloadData.execute_url);
          return;
        }

        // State 2 / State 4: Second+ download without active 24h pass -> Show "Unlock 24 Hours Free" popup
        if (currentAccessData.ad_required) {
          event.preventDefault();
          unlockModalCtrl.open(
            currentDownloadData.ad_gate_url ||
              `/ads/gate/?download_id=${encodeURIComponent(currentDownloadData.id)}&mode=30s`
          );
          return;
        }

        // State 1: First download -> Show 5-second advertisement page before starting download
        if (currentAccessData.initial_5s_ad_required) {
          event.preventDefault();
          const gate5sUrl =
            currentDownloadData.initial_ad_gate_url ||
            `/ads/gate/?download_id=${encodeURIComponent(currentDownloadData.id)}&mode=5s`;
          window.location.href = gate5sUrl;
          return;
        }

        // Fallback (e.g. returning from 5s ad): start download directly
        event.preventDefault();
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

        populateResultPanel(data.download, data.access);
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

      if (access.has_free_24h) {
        actionBtn.href = dl.execute_url;
        actionBtn.textContent = `${baseDownloadLabel} • Ad-Free`;
        if (adNotice) adNotice.hidden = true;
      } else if (access.ad_required) {
        actionBtn.href = dl.ad_gate_url || `/ads/gate/?download_id=${encodeURIComponent(dl.id)}&mode=30s`;
        actionBtn.textContent = baseDownloadLabel;
        if (adNotice) adNotice.hidden = false;
      } else if (access.initial_5s_ad_required) {
        actionBtn.href = dl.initial_ad_gate_url || `/ads/gate/?download_id=${encodeURIComponent(dl.id)}&mode=5s`;
        actionBtn.textContent = baseDownloadLabel;
        if (adNotice) adNotice.hidden = true;
      } else {
        actionBtn.href = dl.execute_url;
        actionBtn.textContent = baseDownloadLabel;
        if (adNotice) adNotice.hidden = true;
      }
    }

    function populateResultPanel(dl, access) {
      if (!resultPanel || !dl) return;
      currentDownloadData = dl;
      currentAccessData = access || {
        state: "STATE_1",
        has_free_24h: false,
        ad_required: false,
        initial_5s_ad_required: true,
      };

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

    // 6. Auto-hydrate Result Panel & Trigger Auto-Download when returning from 5s or 30s Ad Gate
    const bootstrapEl = document.getElementById("activeDownloadBootstrap");
    if (bootstrapEl && bootstrapEl.textContent) {
      try {
        const payload = JSON.parse(bootstrapEl.textContent);
        if (payload && payload.download) {
          populateResultPanel(payload.download, payload.access);
          if (payload.auto_download && payload.download.execute_url) {
            setTimeout(() => {
              startDirectDownloadWithProgress(payload.download.execute_url);
            }, 350);
          }
        }
      } catch (_err) {
        // Ignore malformed bootstrap JSON
      }
    }
  }

  document.addEventListener("DOMContentLoaded", initUrlAnalyzer);
})();
