/**
 * InSave Hub — Production Asynchronous Instagram Video, Reel & Post Downloader Controller
 * Supports interactive downloader mode tabs, one-click clipboard paste,
 * Fetch API URL analysis, and server-validated download execution.
 */
(function () {
  "use strict";

  function getCsrfToken() {
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function initUrlAnalyzer() {
    const form = document.getElementById("instagramAnalyzerForm");
    if (!form) return;

    const urlInput = document.getElementById("instagramUrlInput");
    const toolInput = document.getElementById("instagramToolSlug");
    const urlLabel = document.getElementById("instagramUrlLabel");
    const submitBtn = document.getElementById("analyzeSubmitBtn");
    const pasteBtn = document.getElementById("pasteClipboardBtn");
    const statusBox = document.getElementById("analyzerStatusBox");
    const resultPanel = document.getElementById("analyzerResultPanel");

    let activeButtonLabel = submitBtn ? submitBtn.textContent.trim() : "Analyze & Download";

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
        const btnText = tab.getAttribute("data-button-text") || "Analyze & Download";

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

    // 3. Form Submission -> Asynchronous Fetch API Analysis
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
            "Accept": "application/json",
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
      submitBtn.textContent = isLoading ? "Extracting Instagram Stream..." : activeButtonLabel;
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

    function populateResultPanel(dl, access) {
      if (!resultPanel) return;
      resultPanel.hidden = false;

      const setText = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val || "-";
      };

      setText("resMediaTitle", dl.media_title);
      setText("resContentType", dl.content_type_label);
      setText("resMediaFormat", dl.media_format);
      setText("resResolution", dl.resolution);
      setText("resFileSize", dl.file_size_label);
      setText("resShortcode", dl.shortcode);
      setText("resAuthorHandle", dl.author_handle);
      setText("resAccessStatus", access.label);

      const meta = dl.preview_metadata || {};
      setText("resPreviewCodec", meta.video_codec || dl.media_format);
      setText("resPreviewAspect", meta.aspect_ratio || dl.resolution);
      setText("resPreviewShortcode", dl.shortcode);

      const previewFrame = document.getElementById("resPreviewFrame");
      if (previewFrame) {
        if (meta.thumbnail_url) {
          previewFrame.style.backgroundImage = `linear-gradient(180deg, rgba(12, 45, 72, 0.35) 0%, rgba(12, 45, 72, 0.65) 100%), url("${meta.thumbnail_url}")`;
          previewFrame.style.backgroundSize = "cover";
          previewFrame.style.backgroundPosition = "center";
        } else {
          previewFrame.style.backgroundImage = "";
        }
      }

      const actionBtn = document.getElementById("resDownloadActionBtn");
      const adNotice = document.getElementById("resAdRequirementNotice");

      if (actionBtn) {
        if (access.ad_required) {
          actionBtn.href = dl.ad_gate_url;
          actionBtn.textContent = "Complete 30s Ad to Unlock Download & 24h Pass";
          actionBtn.removeAttribute("download");
          if (adNotice) adNotice.hidden = false;
        } else {
          actionBtn.href = dl.execute_url;
          const isVideo = meta.is_video || dl.content_type === "video" || dl.content_type === "reel";
          const isImage = meta.ext === "jpg" || dl.content_type === "image" || dl.content_type === "profile";
          if (dl.content_type === "metadata") {
            actionBtn.textContent = "Download JSON Manifest";
          } else if (isVideo) {
            actionBtn.textContent = "Download Video (MP4)";
          } else if (isImage) {
            actionBtn.textContent = "Download Photo (JPG)";
          } else {
            actionBtn.textContent = "Download Post Media";
          }
          if (adNotice) adNotice.hidden = true;
        }
      }

      resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  document.addEventListener("DOMContentLoaded", initUrlAnalyzer);
})();
