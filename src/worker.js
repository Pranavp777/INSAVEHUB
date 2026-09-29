/**
 * Cloudflare Worker & Edge API Engine for InSave Hub.
 * Serves static assets from ./dist and executes live Instagram Video, Reel,
 * Photo, and Carousel extraction via Instagram's Polaris GraphQL & CDN streams.
 */

const IG_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36";

function shortcodeToMediaId(shortcode) {
  const clean = (shortcode || "").trim().slice(0, 11);
  if (!clean) return null;
  let pk = 0n;
  for (let i = 0; i < clean.length; i++) {
    const idx = IG_ALPHABET.indexOf(clean[i]);
    if (idx === -1) return null;
    pk = pk * 64n + BigInt(idx);
  }
  return pk.toString();
}

function isSafeCdnUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    const host = parsed.hostname.toLowerCase();
    return (
      host.endsWith(".fbcdn.net") ||
      host.endsWith(".cdninstagram.com") ||
      host === "fbcdn.net" ||
      host === "cdninstagram.com"
    );
  } catch (_e) {
    return false;
  }
}

function encodeToken(payloadObj) {
  const jsonStr = JSON.stringify(payloadObj);
  const b64 = btoa(unescape(encodeURIComponent(jsonStr)));
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function decodeToken(token) {
  try {
    let b64 = (token || "").replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4 !== 0) b64 += "=";
    const jsonStr = decodeURIComponent(escape(atob(b64)));
    return JSON.parse(jsonStr);
  } catch (_e) {
    return null;
  }
}

export async function extractInstagramMediaEdge(shortcode) {
  const mediaId = shortcodeToMediaId(shortcode);
  if (mediaId) {
    try {
      const body = new URLSearchParams({
        lsd: "AVqbxe3J_YA",
        fb_api_caller_class: "RelayModern",
        fb_api_req_friendly_name: "PolarisLoggedOutDesktopWWWPostRootContentQuery",
        server_timestamps: "true",
        variables: JSON.stringify({ media_id: mediaId }),
        doc_id: "27130156389949648",
      });

      const resp = await fetch("https://www.instagram.com/api/graphql", {
        method: "POST",
        headers: {
          "User-Agent": USER_AGENT,
          Accept: "*/*",
          "Accept-Language": "en-US,en;q=0.9",
          "Content-Type": "application/x-www-form-urlencoded",
          "X-IG-App-ID": "936619743392459",
          "X-FB-Friendly-Name": "PolarisLoggedOutDesktopWWWPostRootContentQuery",
          "X-FB-LSD": "AVqbxe3J_YA",
          "X-ASBD-ID": "129477",
          Referer: `https://www.instagram.com/p/${shortcode}/`,
        },
        body: body.toString(),
      });

      if (resp.ok) {
        const data = await resp.json();
        const rawProduct =
          data?.data?.xig_polaris_media?.if_not_gated_logged_out;
        const product = Array.isArray(rawProduct) ? rawProduct[0] : rawProduct;
        if (product && typeof product === "object") {
          const videoVersions = product.video_versions || [];
          const imgCandidates = product.image_versions2?.candidates || [];
          const carouselRaw = product.carousel_media || [];

          let isVideo = videoVersions.length > 0;
          let directUrl = "";
          if (videoVersions.length > 0 && videoVersions[0].url) {
            directUrl = videoVersions[0].url;
          } else if (carouselRaw.length > 0) {
            const firstSlide = carouselRaw[0];
            if (firstSlide.video_versions?.length > 0) {
              directUrl = firstSlide.video_versions[0].url;
              isVideo = true;
            } else if (firstSlide.image_versions2?.candidates?.length > 0) {
              directUrl = firstSlide.image_versions2.candidates[0].url;
              isVideo = false;
            }
          } else if (imgCandidates.length > 0 && imgCandidates[0].url) {
            directUrl = imgCandidates[0].url;
            isVideo = false;
          }

          if (directUrl) {
            const width = Number(product.original_width || 1080);
            const height = Number(product.original_height || (isVideo ? 1920 : 1350));
            const owner = product.user?.username || "instagram_creator";
            const thumbUrl =
              imgCandidates[0]?.url || (!isVideo ? directUrl : "");
            const rawCaption = product.caption?.text || "";
            const cleanTitle =
              rawCaption
                .replace(/[^\x20-\x7E]+/g, " ")
                .replace(/\s+/g, " ")
                .trim()
                .slice(0, 100) ||
              `Instagram ${isVideo ? "Video" : "Post"} by @${owner}`;

            return {
              direct_media_url: directUrl,
              thumbnail_url: thumbUrl,
              width,
              height,
              author_handle: `@${owner.replace(/^@/, "")}`,
              media_title: cleanTitle,
              ext: isVideo ? "mp4" : "jpg",
              is_video: isVideo,
              carousel_count: carouselRaw.length || 1,
            };
          }
        }
      }
    } catch (_e) {
      // Fall through to legacy GraphQL
    }
  }

  // Fallback 1: PolarisPostActionLoadPostQueryQuery
  for (const docId of ["8845758582119845", "10015901848480474"]) {
    try {
      const body = new URLSearchParams({
        av: "0",
        variables: JSON.stringify({ shortcode }),
        doc_id: docId,
      });
      const resp = await fetch("https://www.instagram.com/graphql/query", {
        method: "POST",
        headers: {
          "User-Agent": USER_AGENT,
          "Content-Type": "application/x-www-form-urlencoded",
          "X-IG-App-ID": "936619743392459",
          "X-FB-Friendly-Name": "PolarisPostActionLoadPostQueryQuery",
          "X-ASBD-ID": "129477",
          Referer: `https://www.instagram.com/p/${shortcode}/`,
        },
        body: body.toString(),
      });
      if (!resp.ok) continue;
      const payload = await resp.json();
      const media =
        payload?.data?.xdt_shortcode_media || payload?.data?.shortcode_media;
      if (!media) continue;
      const isVideo = Boolean(media.is_video);
      const directUrl = isVideo ? media.video_url : media.display_url;
      if (!directUrl) continue;
      const owner = media.owner?.username || "instagram_creator";
      return {
        direct_media_url: directUrl,
        thumbnail_url: media.display_url || "",
        width: Number(media.dimensions?.width || 1080),
        height: Number(media.dimensions?.height || (isVideo ? 1920 : 1350)),
        author_handle: `@${owner.replace(/^@/, "")}`,
        media_title: `Instagram ${isVideo ? "Video" : "Post"} [${shortcode}]`,
        ext: isVideo ? "mp4" : "jpg",
        is_video: isVideo,
        carousel_count: 1,
      };
    } catch (_e) {
      // Continue
    }
  }

  // Fallback 2: Embed & OpenGraph parser
  try {
    const embedResp = await fetch(`https://www.instagram.com/p/${shortcode}/embed/captioned/`, {
      headers: {
        "User-Agent": USER_AGENT,
        Accept: "text/html,application/xhtml+xml",
        Referer: "https://www.instagram.com/",
      },
    });
    if (embedResp.ok) {
      const html = await embedResp.text();
      const unescapeUrl = (s) =>
        s
          .replace(/\\\//g, "/")
          .replace(/\\u0026/g, "&")
          .replace(/&amp;/g, "&");
      const vidMatch =
        html.match(/\\"video_url\\":\\"(https:[^"\\]+)\\"/) ||
        html.match(/"video_url"\s*:\s*"(https:[^"]+)"/);
      const imgMatch =
        html.match(/\\"display_url\\":\\"(https:[^"\\]+)\\"/) ||
        html.match(/class="[^"]*EmbeddedMediaImage[^"]*"[^>]*src="([^"]+)"/);

      if (vidMatch || imgMatch) {
        const isVideo = Boolean(vidMatch);
        const directUrl = unescapeUrl((vidMatch || imgMatch)[1]);
        if (isSafeCdnUrl(directUrl)) {
          return {
            direct_media_url: directUrl,
            thumbnail_url: imgMatch ? unescapeUrl(imgMatch[1]) : "",
            width: 1080,
            height: isVideo ? 1920 : 1350,
            author_handle: "@instagram_creator",
            media_title: `Instagram ${isVideo ? "Video" : "Post"} [${shortcode}]`,
            ext: isVideo ? "mp4" : "jpg",
            is_video: isVideo,
            carousel_count: 1,
          };
        }
      }
    }
  } catch (_e) {
    // Ignore
  }

  return null;
}

export async function handleAnalyzeRequest(request) {
  let rawUrl = "";
  try {
    const body = await request.json();
    rawUrl = (body.url || "").trim();
  } catch (_e) {
    return Response.json(
      { status: "error", code: "invalid_payload", message: "Please provide a valid Instagram URL." },
      { status: 400 }
    );
  }

  if (!rawUrl) {
    return Response.json(
      { status: "error", code: "empty_url", message: "Please paste a public Instagram URL." },
      { status: 400 }
    );
  }

  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch (_e) {
    return Response.json(
      { status: "error", code: "malformed_url", message: "The URL syntax could not be parsed." },
      { status: 400 }
    );
  }

  const host = parsed.hostname.toLowerCase();
  if (!["instagram.com", "www.instagram.com", "instagr.am", "m.instagram.com"].includes(host)) {
    return Response.json(
      { status: "error", code: "unsupported_domain", message: "Only public URLs from instagram.com are supported." },
      { status: 400 }
    );
  }

  const match = parsed.pathname.match(
    /^\/(?:([A-Za-z0-9._]{1,30})\/)?(p|reel|reels|tv)\/([A-Za-z0-9_-]{5,32})\/?/
  );
  if (!match) {
    return Response.json(
      {
        status: "error",
        code: "unrecognized_instagram_path",
        message: "Please paste a public Instagram Reel (/reel/...), Post (/p/...), or Video (/tv/...) link.",
      },
      { status: 400 }
    );
  }

  const kind = match[2].toLowerCase();
  const shortcode = match[3];
  const contentType = kind === "reel" || kind === "reels" ? "reel" : kind === "tv" ? "video" : "post";

  const extracted = await extractInstagramMediaEdge(shortcode);
  if (!extracted || !extracted.direct_media_url) {
    return Response.json(
      {
        status: "error",
        code: "media_unavailable",
        message: "Unable to retrieve public media from this Instagram URL. Please verify the post is public.",
      },
      { status: 400 }
    );
  }

  const token = encodeToken({
    u: extracted.direct_media_url,
    s: shortcode,
    e: extracted.ext,
    c: contentType,
  });

  const isVideo = extracted.is_video;
  const orientation =
    extracted.height > extracted.width
      ? "Vertical"
      : extracted.width > extracted.height
      ? "Landscape"
      : "Square";

  const access = getEdgeAccessState(request);

  return Response.json({
    status: "ok",
    download: {
      id: shortcode,
      shortcode,
      source_url: `https://www.instagram.com/${contentType === "reel" ? "reel" : "p"}/${shortcode}/`,
      media_title: extracted.media_title,
      author_handle: extracted.author_handle,
      content_type: isVideo ? (contentType === "reel" ? "reel" : "video") : "image",
      content_type_label: isVideo ? (contentType === "reel" ? "Instagram Reel" : "Instagram Video") : "Instagram Photo",
      media_format: isVideo ? "MP4 (H.264 / AAC Original Stream)" : "JPEG (Original Instagram CDN Asset)",
      resolution: `${extracted.width}x${extracted.height} (${orientation} HD)`,
      duration_label: isVideo ? "00:15 (HD Stream)" : "Static Image",
      file_size_label: isVideo ? "HD Stream" : "Original HD",
      file_size_bytes: 0,
      tool_name: "Instagram Downloader",
      preview_metadata: {
        stream_mode: "LIVE_INSTAGRAM_CDN",
        direct_media_url: extracted.direct_media_url,
        thumbnail_url: extracted.thumbnail_url,
        ext: extracted.ext,
        is_video: isVideo,
        video_codec: isVideo ? "AVC1 / H.264 + AAC" : "Original sRGB JPEG",
        aspect_ratio: `${extracted.width}x${extracted.height}`,
        shortcode,
      },
      status: "ready",
      execute_url: `/downloads/execute/${token}/`,
      preview_url: `/downloads/execute/${token}/?preview=1`,
      ad_gate_url: `/ads/gate/?download_id=${encodeURIComponent(shortcode)}&mode=30s`,
      initial_ad_gate_url: `/ads/gate/?download_id=${encodeURIComponent(shortcode)}&mode=5s`,
    },
    access,
  });
}

function parseCookies(request) {
  const cookies = {};
  const raw = (request && request.headers && request.headers.get("Cookie")) || "";
  raw.split(";").forEach((part) => {
    const idx = part.indexOf("=");
    if (idx > -1) {
      const k = part.slice(0, idx).trim();
      const v = part.slice(idx + 1).trim();
      if (k) cookies[k] = decodeURIComponent(v);
    }
  });
  return cookies;
}

function formatHMS(totalSeconds) {
  const clamped = Math.max(0, Math.floor(totalSeconds));
  const h = String(Math.floor(clamped / 3600)).padStart(2, "0");
  const m = String(Math.floor((clamped % 3600) / 60)).padStart(2, "0");
  const s = String(clamped % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

export function getEdgeAccessState(request) {
  const cookies = parseCookies(request);
  const freeUntilMs = parseInt(cookies.insave_free_until || "0", 10);
  const nowMs = Date.now();

  if (!isNaN(freeUntilMs) && freeUntilMs > nowMs) {
    const remainingSec = Math.max(1, Math.floor((freeUntilMs - nowMs) / 1000));
    return {
      state: "STATE_3_FREE_24H_ACTIVE",
      mode: "free_24h_pass",
      label: "24-HOUR FREE ACCESS",
      sublabel: "Ad-free downloads enabled",
      ad_required: false,
      initial_5s_ad_required: false,
      first_download_completed: true,
      has_free_24h: true,
      free_24h_expires_at: new Date(freeUntilMs).toISOString(),
      free_24h_formatted: formatHMS(remainingSec),
      free_24h_remaining_seconds: remainingSec,
    };
  }

  const firstDlDone = cookies.insave_first_dl === "1";
  return {
    state: firstDlDone ? "STATE_2_AD_REQUIRED" : "STATE_1_FIRST_DOWNLOAD",
    mode: firstDlDone ? "ad_required" : "initial_free",
    label: firstDlDone ? "Unlock 24 Hours Free" : "First Download Ready",
    sublabel: firstDlDone
      ? "Watch a 30-second advertisement to unlock 24 hours of free downloads"
      : "Free download ready",
    ad_required: firstDlDone,
    initial_5s_ad_required: false,
    first_download_completed: firstDlDone,
    has_free_24h: false,
    free_24h_expires_at: null,
    free_24h_formatted: "00:00:00",
    free_24h_remaining_seconds: 0,
  };
}

export async function handleAccessStatus(request) {
  return Response.json({
    status: "ok",
    access: getEdgeAccessState(request),
  });
}

export async function handleAdComplete(request) {
  const expiresAtMs = Date.now() + 24 * 3600 * 1000;
  const expiresIso = new Date(expiresAtMs).toISOString();
  return new Response(
    JSON.stringify({
      status: "ok",
      message: "Access unlocked — 24-hour ad-free downloads enabled!",
      ad_type: "unlock_30s",
      free_access_granted: true,
      free_access_expires_at: expiresIso,
      free_access_remaining_seconds: 86400,
      free_access_formatted: "24:00:00",
      redirect_url: "/downloads/?unlocked_24h=1",
    }),
    {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Set-Cookie": `insave_free_until=${expiresAtMs}; Path=/; Max-Age=86400; SameSite=Lax`,
      },
    }
  );
}

export async function handleExecuteDownload(token, request = null) {
  const decoded = decodeToken(token);
  if (!decoded || !decoded.s) {
    return new Response("Invalid download token.", { status: 400 });
  }

  let isPreview = false;
  let rangeHeader = null;
  if (request) {
    try {
      const reqUrl = new URL(request.url);
      isPreview = reqUrl.searchParams.get("preview") === "1";
      rangeHeader = request.headers.get("Range");
    } catch (_e) {
      isPreview = false;
    }
  }

  let directUrl = decoded.u || "";
  const shortcode = (decoded.s || "media").replace(/[^A-Za-z0-9_-]/g, "");
  let ext = decoded.e === "jpg" ? "jpg" : "mp4";
  const contentType = decoded.c || "reel";

  if (!isSafeCdnUrl(directUrl)) {
    const refreshed = await extractInstagramMediaEdge(shortcode);
    if (refreshed && refreshed.direct_media_url) {
      directUrl = refreshed.direct_media_url;
      ext = refreshed.ext;
    }
  }

  if (!isSafeCdnUrl(directUrl)) {
    return new Response("Unable to fetch remote media stream.", { status: 404 });
  }

  const upstreamHeaders = {
    "User-Agent": USER_AGENT,
    Referer: "https://www.instagram.com/",
  };
  if (rangeHeader) {
    upstreamHeaders["Range"] = rangeHeader;
  }

  let cdnResp = await fetch(directUrl, {
    headers: upstreamHeaders,
  });

  if (!cdnResp.ok && cdnResp.status !== 206) {
    const refreshed = await extractInstagramMediaEdge(shortcode);
    if (refreshed && refreshed.direct_media_url) {
      ext = refreshed.ext;
      cdnResp = await fetch(refreshed.direct_media_url, {
        headers: upstreamHeaders,
      });
    }
  }

  if (!cdnResp.ok && cdnResp.status !== 206) {
    return new Response("Instagram CDN stream expired. Please re-analyze the URL.", { status: 502 });
  }

  const mime = ext === "jpg" ? "image/jpeg" : "video/mp4";
  const filename = `insave-${contentType}-${shortcode}.${ext}`;
  const disposition = isPreview ? `inline; filename="${filename}"` : `attachment; filename="${filename}"`;

  const respHeaders = new Headers({
    "Content-Type": mime,
    "Content-Disposition": disposition,
    "Accept-Ranges": "bytes",
    "Cache-Control": "no-store",
  });
  if (!isPreview) {
    respHeaders.append("Set-Cookie", "insave_first_dl=1; Path=/; Max-Age=86400; SameSite=Lax");
  }
  const contentRange = cdnResp.headers.get("Content-Range");
  if (contentRange) {
    respHeaders.set("Content-Range", contentRange);
  }
  const contentLength = cdnResp.headers.get("Content-Length");
  if (contentLength) {
    respHeaders.set("Content-Length", contentLength);
  }

  return new Response(cdnResp.body, {
    status: cdnResp.status === 206 ? 206 : 200,
    headers: respHeaders,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/downloads/analyze/" && request.method === "POST") {
      return await handleAnalyzeRequest(request);
    }

    if (url.pathname === "/ads/access-status/" && request.method === "GET") {
      return await handleAccessStatus(request);
    }

    if (url.pathname === "/ads/complete/" && request.method === "POST") {
      return await handleAdComplete(request);
    }

    const execMatch = url.pathname.match(/^\/downloads\/execute\/([^/]+)\/?$/);
    if (execMatch) {
      return await handleExecuteDownload(execMatch[1], request);
    }

    if (url.pathname === "/auth/google/login/" || url.pathname === "/auth/google/login") {
      const clientId = env && env.GOOGLE_OAUTH_CLIENT_ID ? String(env.GOOGLE_OAUTH_CLIENT_ID).trim() : "";
      if (clientId) {
        const redirectUri =
          (env && env.GOOGLE_OAUTH_REDIRECT_URI) || `${url.origin}/auth/google/callback/`;
        const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
        authUrl.searchParams.set("client_id", clientId);
        authUrl.searchParams.set("redirect_uri", redirectUri);
        authUrl.searchParams.set("response_type", "code");
        authUrl.searchParams.set("scope", "openid email profile");
        authUrl.searchParams.set("prompt", "select_account");
        return Response.redirect(authUrl.toString(), 302);
      }
      return Response.redirect(`${url.origin}/auth/login/`, 302);
    }

    if (env && env.ASSETS) {
      const assetResp = await env.ASSETS.fetch(request);
      if (assetResp.status !== 404) {
        return assetResp;
      }
      if (!url.pathname.endsWith("/") && !url.pathname.includes(".")) {
        const slashUrl = new URL(request.url);
        slashUrl.pathname = `${url.pathname}/`;
        return await env.ASSETS.fetch(new Request(slashUrl.toString(), request));
      }
      return assetResp;
    }

    return new Response("Not Found", { status: 404 });
  },
};
