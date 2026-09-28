"""
Production Instagram public media extractor and CDN stream fetcher.

Implements a multi-stage extraction pipeline for public Instagram Posts (/p/),
Reels (/reel/), Videos (/tv/), Carousels, Images, and Public Profiles:
1. yt-dlp Python extractor (supports progressive MP4, carousels, cookies, sessionid, and proxy).
2. Instagram Public GraphQL API (PolarisPostActionLoadPostQueryQuery) for video, image, and carousel posts.
3. Instagram Public Embed parser (/p/<shortcode>/embed/captioned/) with contextJSON and srcset image extraction.
4. OpenGraph & Web Profile API fallback for public posts and HD profile avatars.
"""
import html
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ALLOWED_CDN_HOST_SUFFIXES = (
    "cdninstagram.com",
    "fbcdn.net",
    "instagram.com",
)


def is_running_tests() -> bool:
    """Return True when executing inside Django's automated test runner."""
    return "test" in sys.argv or "pytest" in sys.modules


def _get_user_agent() -> str:
    return getattr(
        settings,
        "INSTAGRAM_USER_AGENT",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )


def _get_requests_kwargs(timeout: Optional[int] = None) -> Dict[str, Any]:
    """Build common requests kwargs including timeout, cookies, and proxy if configured."""
    eff_timeout = timeout or getattr(settings, "INSTAGRAM_EXTRACTOR_TIMEOUT", 18)
    kwargs: Dict[str, Any] = {"timeout": eff_timeout}

    proxy_url = getattr(settings, "INSTAGRAM_PROXY_URL", "").strip()
    if proxy_url:
        kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}

    session_id = getattr(settings, "INSTAGRAM_SESSIONID", "").strip()
    if session_id:
        kwargs["cookies"] = {"sessionid": session_id}

    return kwargs


def is_safe_cdn_url(url: str) -> bool:
    """Verify that a direct media URL points to an authentic Instagram/Meta CDN host."""
    if not url or not url.startswith(("https://", "http://")):
        return False
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return any(
            host == suffix or host.endswith(f".{suffix}")
            for suffix in ALLOWED_CDN_HOST_SUFFIXES
        )
    except ValueError:
        return False


def _unescape_ig_url(raw: str) -> str:
    """Clean escaped JSON/HTML URLs returned by Instagram endpoints."""
    if not raw:
        return ""
    cleaned = (
        raw.replace("\\/", "/")
        .replace("\\u0026", "&")
        .replace("\\u0025", "%")
        .replace("&amp;", "&")
    )
    return html.unescape(cleaned).strip()


def _resolve_entry_media(entry: Dict[str, Any]) -> Tuple[str, str, int, int, bool]:
    """
    Resolve the best direct CDN URL, extension, width, height, and is_video flag
    from a yt-dlp info/entry dictionary (supports both progressive MP4 video and HD JPEG photo).
    """
    formats = entry.get("formats") or []
    # 1. Prefer progressive MP4 with both video and audio (non-DASH video_versions)
    progressive_mp4 = [
        f
        for f in formats
        if f.get("url")
        and f.get("ext") == "mp4"
        and f.get("vcodec") != "none"
        and f.get("acodec") != "none"
        and not str(f.get("format_id") or "").startswith("dash")
    ]
    if progressive_mp4:
        best_fmt = progressive_mp4[-1]
        w = int(best_fmt.get("width") or entry.get("width") or 1080)
        h = int(best_fmt.get("height") or entry.get("height") or 1920)
        return str(best_fmt["url"]), "mp4", w, h, True

    # 2. Any MP4 format with video
    mp4_formats = [
        f
        for f in formats
        if f.get("url") and f.get("ext") == "mp4" and f.get("vcodec") != "none"
    ]
    if mp4_formats:
        best_fmt = mp4_formats[-1]
        w = int(best_fmt.get("width") or entry.get("width") or 1080)
        h = int(best_fmt.get("height") or entry.get("height") or 1920)
        return str(best_fmt["url"]), "mp4", w, h, True

    # 3. Direct URL on entry if video
    if entry.get("url") and (entry.get("ext") == "mp4" or entry.get("duration")):
        w = int(entry.get("width") or 1080)
        h = int(entry.get("height") or 1920)
        return str(entry["url"]), "mp4", w, h, True

    # 4. Photo / Image post via thumbnails (image_versions2 candidates)
    thumbnails = [t for t in (entry.get("thumbnails") or []) if isinstance(t, dict) and t.get("url")]
    if thumbnails:
        best_thumb = max(
            thumbnails,
            key=lambda t: int(t.get("width") or 0) * int(t.get("height") or 0),
        )
        w = int(best_thumb.get("width") or 1080)
        h = int(best_thumb.get("height") or 1350)
        return str(best_thumb["url"]), "jpg", w, h, False

    if entry.get("thumbnail"):
        return str(entry["thumbnail"]), "jpg", int(entry.get("width") or 1080), int(entry.get("height") or 1350), False

    return "", "mp4", 1080, 1920, True


def _extract_via_ytdlp(url: str, shortcode: str) -> Optional[Dict[str, Any]]:
    """
    Stage 1: Extract real direct video/image stream URL and metadata via yt-dlp.
    Supports single videos, Reels, single photos, and multi-item post carousels.
    """
    try:
        import yt_dlp
    except ImportError:
        return None

    headers: Dict[str, str] = {
        "User-Agent": _get_user_agent(),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
    }
    session_id = getattr(settings, "INSTAGRAM_SESSIONID", "").strip()
    if session_id:
        headers["Cookie"] = f"sessionid={session_id}"

    ydl_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": False,
        "ignore_no_formats_error": True,
        "socket_timeout": getattr(settings, "INSTAGRAM_EXTRACTOR_TIMEOUT", 18),
        "format": "best[ext=mp4][vcodec!=none][acodec!=none]/best[ext=mp4]/best",
        "http_headers": headers,
    }

    cookies_file = getattr(settings, "INSTAGRAM_COOKIES_FILE", "").strip()
    if cookies_file and os.path.isfile(cookies_file):
        ydl_opts["cookiefile"] = cookies_file

    proxy_url = getattr(settings, "INSTAGRAM_PROXY_URL", "").strip()
    if proxy_url:
        ydl_opts["proxy"] = proxy_url

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            parent_channel = info.get("channel") or info.get("uploader") or info.get("uploader_id")
            parent_desc = info.get("description") or info.get("title")

            carousel_items: List[Dict[str, Any]] = []
            if "entries" in info and info["entries"]:
                entries = [e for e in info["entries"] if e]
                for idx, entry in enumerate(entries, start=1):
                    e_url, e_ext, e_w, e_h, _ = _resolve_entry_media(entry)
                    if e_url:
                        carousel_items.append(
                            {
                                "index": idx,
                                "url": e_url,
                                "ext": e_ext,
                                "width": e_w,
                                "height": e_h,
                            }
                        )
                if entries:
                    info = entries[0]

            direct_url, ext, width, height, is_video = _resolve_entry_media(info)
            if not direct_url:
                return None

            duration = round(float(info.get("duration") or 0), 1)
            filesize = info.get("filesize") or info.get("filesize_approx") or 0
            uploader = (
                info.get("channel")
                or parent_channel
                or info.get("uploader")
                or info.get("uploader_id")
                or "instagram_creator"
            )
            title = (
                info.get("description")
                or parent_desc
                or info.get("title")
                or f"Instagram {'Video' if is_video else 'Post'} [{shortcode}]"
            )
            title = re.sub(r"[^\x20-\x7E]+", " ", str(title))
            title = re.sub(r"\s+", " ", title).strip()[:110]
            if not title:
                title = f"Instagram {'Video' if is_video else 'Post'} by @{str(uploader).lstrip('@')[:30]}"

            thumbnails = [t for t in (info.get("thumbnails") or []) if isinstance(t, dict) and t.get("url")]
            thumbnail = (
                thumbnails[-1]["url"]
                if thumbnails
                else (info.get("thumbnail") or (direct_url if not is_video else ""))
            )

            return {
                "direct_media_url": direct_url,
                "thumbnail_url": thumbnail,
                "width": width,
                "height": height,
                "duration_seconds": duration,
                "file_size_bytes": int(filesize) if filesize else 0,
                "author_handle": f"@{str(uploader).lstrip('@')[:30]}",
                "media_title": title,
                "ext": ext,
                "is_video": is_video,
                "carousel_count": len(carousel_items) if carousel_items else 1,
                "carousel_items": carousel_items[:10],
                "extractor_source": "yt-dlp",
            }
    except Exception as exc:
        logger.debug("yt-dlp extraction skipped for %s: %s", shortcode, exc)
        return None


_IG_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _shortcode_to_media_id(shortcode: str) -> Optional[str]:
    """Convert an 11-character Instagram shortcode into its numeric media_id (pk)."""
    clean = (shortcode or "").strip()[:11]
    if not clean or any(ch not in _IG_ALPHABET for ch in clean):
        return None
    pk = 0
    for ch in clean:
        pk = (pk * 64) + _IG_ALPHABET.index(ch)
    return str(pk)


def _extract_via_graphql(shortcode: str) -> Optional[Dict[str, Any]]:
    """
    Stage 2: Extract real direct video, high-res photo, or carousel items from
    Instagram's public GraphQL endpoint (PolarisLoggedOutDesktopWWWPostRootContentQuery
    and PolarisPostActionLoadPostQueryQuery).
    """
    req_kwargs = _get_requests_kwargs()
    media_id = _shortcode_to_media_id(shortcode)

    if media_id:
        try:
            polaris_resp = requests.post(
                "https://www.instagram.com/api/graphql",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-IG-App-ID": "936619743392459",
                    "X-FB-Friendly-Name": "PolarisLoggedOutDesktopWWWPostRootContentQuery",
                    "X-FB-LSD": "AVqbxe3J_YA",
                    "X-ASBD-ID": "129477",
                    "Referer": f"https://www.instagram.com/p/{shortcode}/",
                },
                data={
                    "lsd": "AVqbxe3J_YA",
                    "fb_api_caller_class": "RelayModern",
                    "fb_api_req_friendly_name": "PolarisLoggedOutDesktopWWWPostRootContentQuery",
                    "server_timestamps": "true",
                    "variables": json.dumps({"media_id": media_id}, separators=(",", ":")),
                    "doc_id": "27130156389949648",
                },
                **req_kwargs,
            )
            if polaris_resp.status_code == 200:
                p_data = polaris_resp.json()
                raw_product = (
                    (p_data.get("data") or {})
                    .get("xig_polaris_media", {})
                    .get("if_not_gated_logged_out")
                )
                product = raw_product[0] if isinstance(raw_product, list) and raw_product else raw_product
                if isinstance(product, dict):
                    video_versions = product.get("video_versions") or []
                    img_candidates = (product.get("image_versions2") or {}).get("candidates") or []
                    carousel_raw = product.get("carousel_media") or []

                    carousel_items: List[Dict[str, Any]] = []
                    for idx, slide in enumerate(carousel_raw, start=1):
                        if not isinstance(slide, dict):
                            continue
                        s_vids = slide.get("video_versions") or []
                        s_imgs = (slide.get("image_versions2") or {}).get("candidates") or []
                        if s_vids and s_vids[0].get("url"):
                            carousel_items.append(
                                {
                                    "index": idx,
                                    "url": s_vids[0]["url"],
                                    "ext": "mp4",
                                    "width": int(s_vids[0].get("width") or slide.get("original_width") or 1080),
                                    "height": int(s_vids[0].get("height") or slide.get("original_height") or 1920),
                                }
                            )
                        elif s_imgs and s_imgs[0].get("url"):
                            carousel_items.append(
                                {
                                    "index": idx,
                                    "url": s_imgs[0]["url"],
                                    "ext": "jpg",
                                    "width": int(s_imgs[0].get("width") or slide.get("original_width") or 1080),
                                    "height": int(s_imgs[0].get("height") or slide.get("original_height") or 1350),
                                }
                            )

                    is_video = bool(video_versions)
                    direct_url = ""
                    if video_versions and video_versions[0].get("url"):
                        direct_url = str(video_versions[0]["url"])
                    elif carousel_items:
                        direct_url = str(carousel_items[0]["url"])
                        is_video = carousel_items[0]["ext"] == "mp4"
                    elif img_candidates and img_candidates[0].get("url"):
                        direct_url = str(img_candidates[0]["url"])
                        is_video = False

                    if direct_url:
                        width = int(product.get("original_width") or 1080)
                        height = int(product.get("original_height") or (1920 if is_video else 1350))
                        owner = (product.get("user") or {}).get("username") or "instagram_creator"
                        thumb_url = (
                            img_candidates[0]["url"]
                            if img_candidates and img_candidates[0].get("url")
                            else (direct_url if not is_video else "")
                        )
                        caption_obj = product.get("caption") or {}
                        caption_text = caption_obj.get("text") if isinstance(caption_obj, dict) else ""
                        clean_title = re.sub(r"[^\x20-\x7E]+", " ", str(caption_text or ""))
                        clean_title = re.sub(r"\s+", " ", clean_title).strip()[:100]
                        if not clean_title:
                            clean_title = f"Instagram {'Video' if is_video else 'Post'} by @{owner.lstrip('@')}"

                        return {
                            "direct_media_url": direct_url,
                            "thumbnail_url": thumb_url,
                            "width": width,
                            "height": height,
                            "duration_seconds": round(float(product.get("video_duration") or 0), 1),
                            "file_size_bytes": 0,
                            "author_handle": f"@{owner.lstrip('@')[:30]}",
                            "media_title": clean_title,
                            "ext": "mp4" if is_video else "jpg",
                            "is_video": is_video,
                            "carousel_count": len(carousel_items) if carousel_items else 1,
                            "carousel_items": carousel_items[:10],
                            "extractor_source": "instagram-polaris-graphql",
                        }
        except Exception as exc:
            logger.debug("Polaris GraphQL extraction skipped for %s: %s", shortcode, exc)

    graphql_url = "https://www.instagram.com/graphql/query"
    headers = {
        "User-Agent": _get_user_agent(),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-IG-App-ID": "936619743392459",
        "X-FB-Friendly-Name": "PolarisPostActionLoadPostQueryQuery",
        "X-ASBD-ID": "129477",
        "Origin": "https://www.instagram.com",
        "Referer": f"https://www.instagram.com/p/{shortcode}/",
    }

    for doc_id in ("8845758582119845", "10015901848480474"):
        try:
            resp = requests.post(
                graphql_url,
                headers=headers,
                data={
                    "av": "0",
                    "variables": json.dumps({"shortcode": shortcode}),
                    "doc_id": doc_id,
                },
                **req_kwargs,
            )
            if resp.status_code != 200:
                continue
            payload = resp.json()
            media = (
                payload.get("data", {}).get("xdt_shortcode_media")
                or payload.get("data", {}).get("shortcode_media")
            )
            if not media:
                continue

            is_video = bool(media.get("is_video"))
            display_resources = media.get("display_resources") or []
            best_display_url = (
                display_resources[-1].get("src")
                if display_resources
                else media.get("display_url")
            )
            direct_url = media.get("video_url") if is_video else best_display_url

            carousel_items = []
            if media.get("edge_sidecar_to_children"):
                edges = media["edge_sidecar_to_children"].get("edges") or []
                for idx, edge in enumerate(edges, start=1):
                    node = edge.get("node") or {}
                    node_is_video = bool(node.get("is_video"))
                    node_resources = node.get("display_resources") or []
                    node_img = (
                        node_resources[-1].get("src")
                        if node_resources
                        else node.get("display_url")
                    )
                    node_url = node.get("video_url") if node_is_video else node_img
                    node_dims = node.get("dimensions") or {}
                    if node_url:
                        carousel_items.append(
                            {
                                "index": idx,
                                "url": node_url,
                                "ext": "mp4" if node_is_video else "jpg",
                                "width": int(node_dims.get("width") or 1080),
                                "height": int(node_dims.get("height") or 1080),
                            }
                        )
                        if not direct_url or (node_is_video and not is_video):
                            direct_url = node_url
                            is_video = node_is_video

            if not direct_url:
                continue

            dimensions = media.get("dimensions") or {}
            width = int(dimensions.get("width") or 1080)
            height = int(dimensions.get("height") or (1920 if is_video else 1350))
            duration = round(float(media.get("video_duration") or 0), 1)
            owner = (media.get("owner") or {}).get("username") or "instagram_creator"
            thumbnail = best_display_url or ""

            caption_edges = (media.get("edge_media_to_caption") or {}).get("edges") or []
            caption_text = ""
            if caption_edges:
                caption_text = (caption_edges[0].get("node") or {}).get("text") or ""
            title = (
                re.sub(r"[^\x20-\x7E]+", " ", str(caption_text)).strip()[:100]
                or f"Instagram {'Video' if is_video else 'Post'} [{shortcode}]"
            )

            return {
                "direct_media_url": direct_url,
                "thumbnail_url": thumbnail,
                "width": width,
                "height": height,
                "duration_seconds": duration,
                "file_size_bytes": 0,
                "author_handle": f"@{owner.lstrip('@')}",
                "media_title": title,
                "ext": "mp4" if is_video else "jpg",
                "is_video": is_video,
                "carousel_count": len(carousel_items) if carousel_items else 1,
                "carousel_items": carousel_items[:10],
                "extractor_source": "instagram-graphql",
            }
        except Exception as exc:
            logger.debug("GraphQL extraction skipped for %s (doc_id=%s): %s", shortcode, doc_id, exc)

    return None


def _extract_via_embed_page(shortcode: str) -> Optional[Dict[str, Any]]:
    """
    Stage 3: Parse Instagram's public embed page (/p/<shortcode>/embed/captioned/)
    for both video posts (video_url) and photo/carousel posts (display_url / EmbeddedMediaImage).
    """
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    headers = {
        "User-Agent": _get_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
    }
    req_kwargs = _get_requests_kwargs()

    try:
        resp = requests.get(embed_url, headers=headers, **req_kwargs)
        if resp.status_code != 200 or not resp.text:
            return None

        page_html = resp.text

        # Check for video_url in embedded contextJSON or script blocks
        video_match = (
            re.search(r'\\"video_url\\":\\"(https:[^"\\]+)\\"', page_html)
            or re.search(r'"video_url"\s*:\s*"(https:[^"]+)"', page_html)
        )

        # Check for highest-res display_url in embedded JSON
        display_matches = re.findall(r'\\"display_url\\":\\"(https:[^"\\]+)\\"', page_html)
        if not display_matches:
            display_matches = re.findall(r'"display_url"\s*:\s*"(https:[^"]+)"', page_html)

        # Also check for <img class="EmbeddedMediaImage" ... src="..."> for photo posts
        img_tag_match = re.search(
            r'class="[^"]*EmbeddedMediaImage[^"]*"[^>]*src="([^"]+)"',
            page_html,
        )
        if not img_tag_match:
            img_tag_match = re.search(
                r'src="([^"]+)"[^>]*class="[^"]*EmbeddedMediaImage[^"]*"',
                page_html,
            )

        username_match = (
            re.search(r'\\"username\\":\\"([A-Za-z0-9._]+)\\"', page_html)
            or re.search(
                r'class="[^"]*UsernameText[^"]*"[^>]*>([A-Za-z0-9._]+)<',
                page_html,
            )
            or re.search(
                r'href="https://www\.instagram\.com/([A-Za-z0-9._]+)/\?',
                page_html,
            )
        )

        caption_match = re.search(
            r'class="[^"]*Caption[^"]*"[^>]*>.*?<br\s*/?>\s*([^<]+)',
            page_html,
            re.DOTALL,
        )

        direct_url = ""
        is_video = False
        thumbnail_url = ""

        if video_match:
            direct_url = _unescape_ig_url(video_match.group(1))
            is_video = True
            if display_matches:
                thumbnail_url = _unescape_ig_url(display_matches[-1])
        elif display_matches:
            direct_url = _unescape_ig_url(display_matches[-1])
            thumbnail_url = direct_url
            is_video = False
        elif img_tag_match:
            direct_url = _unescape_ig_url(img_tag_match.group(1))
            thumbnail_url = direct_url
            is_video = False

        if not direct_url or not is_safe_cdn_url(direct_url):
            return None

        username = "instagram_creator"
        if username_match:
            candidate = username_match.group(1).strip()
            if candidate.lower() not in ("p", "reel", "reels", "tv", "explore"):
                username = candidate

        ext = "mp4" if is_video else "jpg"
        title = f"Instagram {'Video' if is_video else 'Post'} [{shortcode}]"
        if caption_match:
            cleaned_cap = re.sub(r"\s+", " ", html.unescape(caption_match.group(1))).strip()
            if cleaned_cap:
                title = cleaned_cap[:100]

        carousel_items = []
        for idx, d_url in enumerate(display_matches[:10], start=1):
            clean_d = _unescape_ig_url(d_url)
            if is_safe_cdn_url(clean_d):
                carousel_items.append(
                    {
                        "index": idx,
                        "url": clean_d,
                        "ext": "jpg",
                        "width": 1080,
                        "height": 1350,
                    }
                )

        return {
            "direct_media_url": direct_url,
            "thumbnail_url": thumbnail_url,
            "width": 1080,
            "height": 1920 if is_video else 1350,
            "duration_seconds": 15.0 if is_video else 0.0,
            "file_size_bytes": 0,
            "author_handle": f"@{username.lstrip('@')}",
            "media_title": title,
            "ext": ext,
            "is_video": is_video,
            "carousel_count": max(1, len(carousel_items)),
            "carousel_items": carousel_items,
            "extractor_source": "instagram-embed",
        }
    except Exception as exc:
        logger.debug("Embed extraction skipped for %s: %s", shortcode, exc)
        return None


def _extract_via_opengraph(normalized_url: str, shortcode: str, content_type: str) -> Optional[Dict[str, Any]]:
    """
    Stage 4: Extract public OpenGraph video/image streams or public Profile HD avatars.
    """
    headers = {
        "User-Agent": _get_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
    }
    req_kwargs = _get_requests_kwargs()

    # For profile URLs, first try web_profile_info API for HD avatar
    if content_type == "profile":
        api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={shortcode}"
        api_headers = {
            **headers,
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "129477",
        }
        try:
            api_resp = requests.get(api_url, headers=api_headers, **req_kwargs)
            if api_resp.status_code == 200:
                user_data = (api_resp.json().get("data") or {}).get("user") or {}
                hd_avatar = user_data.get("profile_pic_url_hd") or user_data.get("profile_pic_url")
                if hd_avatar and is_safe_cdn_url(hd_avatar):
                    full_name = user_data.get("full_name") or shortcode
                    return {
                        "direct_media_url": hd_avatar,
                        "thumbnail_url": hd_avatar,
                        "width": 1080,
                        "height": 1080,
                        "duration_seconds": 0.0,
                        "file_size_bytes": 0,
                        "author_handle": f"@{shortcode.lstrip('@')}",
                        "media_title": f"{full_name} (@{shortcode.lstrip('@')}) HD Profile Avatar",
                        "ext": "jpg",
                        "is_video": False,
                        "carousel_count": 1,
                        "carousel_items": [],
                        "extractor_source": "instagram-profile-api",
                    }
        except Exception as exc:
            logger.debug("Profile API lookup skipped for %s: %s", shortcode, exc)

    try:
        resp = requests.get(normalized_url, headers=headers, **req_kwargs)
        if resp.status_code != 200 or not resp.text:
            return None

        page_html = resp.text
        og_video = re.search(
            r'<meta\s+property="og:video(?::secure_url)?"\s+content="([^"]+)"',
            page_html,
            re.IGNORECASE,
        )
        og_image = re.search(
            r'<meta\s+property="og:image"\s+content="([^"]+)"',
            page_html,
            re.IGNORECASE,
        )
        og_title = re.search(
            r'<meta\s+property="og:title"\s+content="([^"]+)"',
            page_html,
            re.IGNORECASE,
        )

        direct_url = ""
        is_video = False
        thumbnail_url = ""

        if og_video:
            direct_url = _unescape_ig_url(og_video.group(1))
            is_video = True
            if og_image:
                thumbnail_url = _unescape_ig_url(og_image.group(1))
        elif og_image:
            direct_url = _unescape_ig_url(og_image.group(1))
            thumbnail_url = direct_url
            is_video = False

        if not direct_url or not is_safe_cdn_url(direct_url):
            return None

        title = f"Instagram Media [{shortcode}]"
        if og_title:
            title = re.sub(r"\s+", " ", html.unescape(og_title.group(1))).strip()[:100]

        return {
            "direct_media_url": direct_url,
            "thumbnail_url": thumbnail_url,
            "width": 1080,
            "height": 1920 if is_video else 1080,
            "duration_seconds": 0.0,
            "file_size_bytes": 0,
            "author_handle": f"@{shortcode.lstrip('@')}" if content_type == "profile" else "@instagram_creator",
            "media_title": title,
            "ext": "mp4" if is_video else "jpg",
            "is_video": is_video,
            "carousel_count": 1,
            "carousel_items": [],
            "extractor_source": "instagram-opengraph",
        }
    except Exception as exc:
        logger.debug("OpenGraph extraction skipped for %s: %s", shortcode, exc)
        return None


def extract_real_instagram_media(
    normalized_url: str,
    shortcode: str,
    content_type: str,
) -> Optional[Dict[str, Any]]:
    """
    Execute the multi-stage extraction pipeline to resolve real Instagram CDN stream metadata.
    Skips external network calls only when running inside the unit test suite.
    """
    if is_running_tests():
        return None

    if content_type == "profile":
        extractors = (
            lambda: _extract_via_opengraph(normalized_url, shortcode, content_type),
        )
    else:
        extractors = (
            lambda: _extract_via_ytdlp(normalized_url, shortcode),
            lambda: _extract_via_graphql(shortcode),
            lambda: _extract_via_embed_page(shortcode),
            lambda: _extract_via_opengraph(normalized_url, shortcode, content_type),
        )

    for extractor_fn in extractors:
        result = extractor_fn()
        if result and result.get("direct_media_url"):
            if not result.get("file_size_bytes") and is_safe_cdn_url(result["direct_media_url"]):
                try:
                    req_kwargs = _get_requests_kwargs(timeout=6)
                    head_resp = requests.head(
                        result["direct_media_url"],
                        headers={
                            "User-Agent": _get_user_agent(),
                            "Referer": "https://www.instagram.com/",
                        },
                        allow_redirects=True,
                        **req_kwargs,
                    )
                    cl = head_resp.headers.get("Content-Length")
                    if cl and cl.isdigit():
                        result["file_size_bytes"] = int(cl)
                except Exception:
                    pass
            return result

    return None


def fetch_remote_media_bytes(direct_url: str) -> Optional[Tuple[bytes, str]]:
    """
    Download the actual binary media file (.mp4 or .jpg) from Instagram's CDN.
    Enforces INSTAGRAM_MAX_DOWNLOAD_SIZE_MB and INSTAGRAM_DOWNLOAD_STREAM_TIMEOUT.
    """
    if not is_safe_cdn_url(direct_url):
        return None

    stream_timeout = getattr(settings, "INSTAGRAM_DOWNLOAD_STREAM_TIMEOUT", 45)
    max_mb = getattr(settings, "INSTAGRAM_MAX_DOWNLOAD_SIZE_MB", 150)
    max_bytes = max(5, int(max_mb)) * 1024 * 1024

    headers = {
        "User-Agent": _get_user_agent(),
        "Accept": "*/*",
        "Referer": "https://www.instagram.com/",
    }
    req_kwargs = _get_requests_kwargs(timeout=stream_timeout)

    try:
        resp = requests.get(direct_url, headers=headers, stream=True, **req_kwargs)
        if resp.status_code != 200:
            return None

        content_type = resp.headers.get("Content-Type", "video/mp4").split(";")[0].strip()
        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    break
        if not chunks:
            return None
        return b"".join(chunks), content_type
    except Exception as exc:
        logger.warning("Failed to fetch remote CDN media: %s", exc)
        return None
