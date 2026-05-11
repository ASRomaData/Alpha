"""
ASRomaData Bot — Publishers
==============================
Instagram Graph API richiede un URL pubblico per l'immagine.
Upload chain gratuita, zero account:
  1. catbox.moe   — permanente, max 200MB
  2. tmpfiles.org — 24h retention
  3. 0x0.st       — permanente

Pubblica su: Instagram, X (thread), Bluesky, Threads (opzionale).
"""

import logging
import os
import time
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE HOSTING — chain gratuita
# ══════════════════════════════════════════════════════════════════════════════

def _upload_catbox(path: str) -> Optional[str]:
    """catbox.moe — permanente, anonimo."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        r = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (os.path.basename(path), data, "image/png")},
            timeout=30,
        )
        r.raise_for_status()
        url = r.text.strip()
        if url.startswith("https://files.catbox.moe/"):
            logger.info(f"catbox.moe OK: {url}")
            return url
    except Exception as e:
        logger.warning(f"catbox.moe: {e}")
    return None


def _upload_tmpfiles(path: str) -> Optional[str]:
    """tmpfiles.org — 24h, anonimo. Fallback 1."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        r = requests.post(
            "https://tmpfiles.org/api/v1/upload",
            files={"file": (os.path.basename(path), data, "image/png")},
            timeout=30,
        )
        r.raise_for_status()
        raw = r.json().get("data", {}).get("url", "")
        if raw:
            # tmpfiles.org serve direttamente come /dl/XXXXX/file.png
            dl  = raw.replace("tmpfiles.org/", "tmpfiles.org/dl/")
            logger.info(f"tmpfiles.org OK: {dl}")
            return dl
    except Exception as e:
        logger.warning(f"tmpfiles.org: {e}")
    return None


def _upload_0x0(path: str) -> Optional[str]:
    """0x0.st — permanente, anonimo. Fallback 2."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        r = requests.post(
            "https://0x0.st",
            files={"file": (os.path.basename(path), data, "image/png")},
            timeout=30,
        )
        r.raise_for_status()
        url = r.text.strip()
        if url.startswith("https://"):
            logger.info(f"0x0.st OK: {url}")
            return url
    except Exception as e:
        logger.warning(f"0x0.st: {e}")
    return None


def upload_image(image_path: str) -> Optional[str]:
    """
    Carica immagine e restituisce URL pubblico.
    Tenta: catbox.moe → tmpfiles.org → 0x0.st
    """
    if not image_path or not os.path.exists(image_path):
        logger.warning(f"upload_image: file non trovato: {image_path}")
        return None
    for fn in (_upload_catbox, _upload_tmpfiles, _upload_0x0):
        url = fn(image_path)
        if url:
            return url
        time.sleep(2)
    logger.error("Tutti gli image host falliti")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# INSTAGRAM GRAPH API
# ══════════════════════════════════════════════════════════════════════════════

class InstagramPublisher:

    BASE = "https://graph.facebook.com/v19.0"

    def __init__(self):
        self.user_id  = os.getenv("IG_USER_ID", "")
        self.token    = os.getenv("IG_ACCESS_TOKEN", "")
        self.enabled  = bool(self.user_id and self.token)
        if not self.enabled:
            logger.warning("Instagram: IG_USER_ID o IG_ACCESS_TOKEN mancanti")

    def _post(self, ep: str, data: dict) -> Optional[dict]:
        data["access_token"] = self.token
        try:
            r = requests.post(f"{self.BASE}/{ep}", data=data, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Instagram {ep}: {e}")
        return None

    def publish_photo(self, image_path: str, caption: str) -> Optional[str]:
        if not self.enabled:
            return None
        # 1. Carica immagine su host gratuito
        img_url = upload_image(image_path)
        if not img_url:
            logger.error("Instagram: nessun URL immagine disponibile")
            return None
        # 2. Crea container
        container = self._post(f"{self.user_id}/media", {
            "image_url": img_url,
            "caption":   caption[:2200],
        })
        if not container or "id" not in container:
            logger.error(f"Instagram container fallito: {container}")
            return None
        time.sleep(8)
        # 3. Pubblica
        result = self._post(f"{self.user_id}/media_publish",
                            {"creation_id": container["id"]})
        if result and "id" in result:
            logger.info(f"Instagram: pubblicato id={result['id']}")
            return result["id"]
        logger.error(f"Instagram publish fallito: {result}")
        return None

    def publish_carousel(self, image_paths: List[str], caption: str) -> Optional[str]:
        if not self.enabled or not image_paths:
            return None
        child_ids = []
        for path in image_paths[:10]:
            url = upload_image(path)
            if not url:
                continue
            c = self._post(f"{self.user_id}/media", {
                "image_url": url, "is_carousel_item": "true",
            })
            if c and "id" in c:
                child_ids.append(c["id"])
            time.sleep(3)
        if not child_ids:
            return None
        carousel = self._post(f"{self.user_id}/media", {
            "media_type": "CAROUSEL",
            "children":   ",".join(child_ids),
            "caption":    caption[:2200],
        })
        if not carousel or "id" not in carousel:
            return None
        time.sleep(8)
        result = self._post(f"{self.user_id}/media_publish",
                            {"creation_id": carousel["id"]})
        if result and "id" in result:
            logger.info(f"Instagram carousel: id={result['id']}")
            return result["id"]
        return None


# ══════════════════════════════════════════════════════════════════════════════
# X / TWITTER v2 (Tweepy)
# ══════════════════════════════════════════════════════════════════════════════

class XPublisher:

    def __init__(self):
        self.api_key    = os.getenv("X_API_KEY", "")
        self.api_secret = os.getenv("X_API_SECRET", "")
        self.acc_token  = os.getenv("X_ACCESS_TOKEN", "")
        self.acc_secret = os.getenv("X_ACCESS_SECRET", "")
        self.bearer     = os.getenv("X_BEARER_TOKEN", "")
        self.enabled    = all([self.api_key, self.api_secret,
                               self.acc_token, self.acc_secret])
        self._v2  = None
        self._v1  = None
        if not self.enabled:
            logger.warning("X: credenziali mancanti")

    def _client_v2(self):
        if self._v2:
            return self._v2
        try:
            import tweepy
            self._v2 = tweepy.Client(
                bearer_token=self.bearer,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.acc_token,
                access_token_secret=self.acc_secret,
                wait_on_rate_limit=True,
            )
        except Exception as e:
            logger.error(f"X v2: {e}")
        return self._v2

    def _client_v1(self):
        if self._v1:
            return self._v1
        try:
            import tweepy
            auth = tweepy.OAuth1UserHandler(
                self.api_key, self.api_secret,
                self.acc_token, self.acc_secret,
            )
            self._v1 = tweepy.API(auth, wait_on_rate_limit=True)
        except Exception as e:
            logger.error(f"X v1: {e}")
        return self._v1

    def upload_media(self, image_path: str) -> Optional[str]:
        api = self._client_v1()
        if not api or not os.path.exists(image_path):
            return None
        try:
            return str(api.media_upload(image_path).media_id)
        except Exception as e:
            logger.error(f"X media upload: {e}")
        return None

    def tweet(self, text: str, media_id: str = None,
              reply_to: str = None) -> Optional[str]:
        if not self.enabled:
            return None
        c = self._client_v2()
        if not c:
            return None
        try:
            kw: dict = {"text": text[:270]}
            if media_id:
                kw["media_ids"] = [media_id]
            if reply_to:
                kw["in_reply_to_tweet_id"] = reply_to
            resp = c.create_tweet(**kw)
            tid  = str(resp.data["id"])
            logger.info(f"X tweet: {tid}")
            return tid
        except Exception as e:
            logger.error(f"X tweet: {e}")
        return None

    def post_thread(self, tweets: List[str],
                    image_path: str = None) -> List[str]:
        if not self.enabled or not tweets:
            return []
        ids     = []
        prev_id = None
        for i, text in enumerate(tweets):
            mid = self.upload_media(image_path) if i == 0 and image_path else None
            tid = self.tweet(text, media_id=mid, reply_to=prev_id)
            if tid:
                ids.append(tid)
                prev_id = tid
            time.sleep(3)
        return ids


# ══════════════════════════════════════════════════════════════════════════════
# BLUESKY (AT Protocol)
# ══════════════════════════════════════════════════════════════════════════════

class BlueskyPublisher:

    def __init__(self):
        self.handle   = os.getenv("BSKY_HANDLE", "")
        self.password = os.getenv("BSKY_PASSWORD", "")
        self.enabled  = bool(self.handle and self.password)
        self._client  = None
        if not self.enabled:
            logger.warning("Bluesky: credenziali mancanti")

    def _get_client(self):
        if self._client:
            return self._client
        try:
            from atproto import Client
            c = Client()
            c.login(self.handle, self.password)
            self._client = c
        except Exception as e:
            logger.error(f"Bluesky login: {e}")
        return self._client

    def post(self, text: str, image_path: str = None) -> bool:
        if not self.enabled:
            return False
        c = self._get_client()
        if not c:
            return False
        try:
            text = text[:300]
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    img_data = f.read()
                blob = c.upload_blob(img_data)
                from atproto import models
                c.send_post(
                    text=text,
                    embed=models.AppBskyEmbedImages.Main(
                        images=[models.AppBskyEmbedImages.Image(
                            alt="AS Roma stats · @ASRomaData",
                            image=blob.blob,
                        )]
                    ),
                )
            else:
                c.send_post(text=text)
            logger.info("Bluesky: pubblicato")
            return True
        except Exception as e:
            logger.error(f"Bluesky: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# THREADS (Meta Threads API)
# ══════════════════════════════════════════════════════════════════════════════

class ThreadsPublisher:

    BASE = "https://graph.threads.net/v1.0"

    def __init__(self):
        self.user_id  = os.getenv("THREADS_USER_ID", os.getenv("IG_USER_ID", ""))
        self.token    = os.getenv("THREADS_ACCESS_TOKEN", os.getenv("IG_ACCESS_TOKEN", ""))
        self.enabled  = os.getenv("THREADS_ENABLED", "false").lower() == "true"
        if self.enabled and not (self.user_id and self.token):
            logger.warning("Threads: THREADS_ENABLED=true ma credenziali mancanti")
            self.enabled = False

    def post(self, text: str, image_path: str = None) -> Optional[str]:
        if not self.enabled:
            return None
        img_url = upload_image(image_path) if image_path else None
        try:
            data: dict = {
                "media_type":   "IMAGE" if img_url else "TEXT",
                "text":         text[:500],
                "access_token": self.token,
            }
            if img_url:
                data["image_url"] = img_url
            r = requests.post(f"{self.BASE}/{self.user_id}/threads",
                              data=data, timeout=30)
            r.raise_for_status()
            cid = r.json().get("id")
            if not cid:
                return None
            time.sleep(5)
            pub = requests.post(
                f"{self.BASE}/{self.user_id}/threads_publish",
                data={"creation_id": cid, "access_token": self.token},
                timeout=30,
            )
            pub.raise_for_status()
            pid = pub.json().get("id")
            logger.info(f"Threads: id={pid}")
            return pid
        except Exception as e:
            logger.error(f"Threads: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PUBLISH ALL
# ══════════════════════════════════════════════════════════════════════════════

def publish_to_all_platforms(
    image_path: Optional[str],
    x_thread: List[str],
    ig_caption: str,
    bsky_text: str,
    threads_text: str = None,
) -> dict:
    results = {}

    # X
    x = XPublisher()
    if x_thread:
        ids = x.post_thread(x_thread, image_path=image_path)
        results["x"] = {"published": bool(ids), "tweet_ids": ids}
        time.sleep(3)

    # Instagram
    if image_path:
        ig = InstagramPublisher()
        pid = ig.publish_photo(image_path, ig_caption)
        results["instagram"] = {"published": bool(pid), "post_id": pid}

    # Bluesky
    bsky = BlueskyPublisher()
    results["bluesky"] = {"published": bsky.post(bsky_text, image_path=image_path)}
    time.sleep(2)

    # Threads
    th = ThreadsPublisher()
    if th.enabled:
        ok = th.post(threads_text or ig_caption, image_path=image_path)
        results["threads"] = {"published": bool(ok)}

    logger.info(f"Pubblicazione: {results}")
    return results
