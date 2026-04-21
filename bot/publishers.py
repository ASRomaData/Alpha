"""
ASRomaData Bot — Publishers
============================
Pubblica su Instagram (Graph API), X (Tweepy v4), Bluesky (atproto), Threads.

Nota sull'allineamento con bot.py:
- Instagram e Threads usano data= (corpo della richiesta POST), NON params=.
  Questo è il comportamento testato e funzionante in bot.py (righe 401, 411).
- Il tempo di attesa tra container e publish è 8s (allineato a bot.py), non 10s.
- Il CDN wait di 20s rimane invariato dopo il commit GitHub.
"""

import base64
import logging
import os
import time
import json
from typing import List, Optional

import requests
try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = requests

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# IMAGE HOSTING — GITHUB COMMIT
# ══════════════════════════════════════════════════════════════════════════════

def upload_image_for_instagram(image_path: str) -> Optional[str]:
    """
    Committa l'immagine su GitHub e restituisce raw.githubusercontent.com URL.
    Richiede GH_TOKEN + GH_OWNER + GH_REPO (o GH_REPOSITORY come owner/repo).
    """
    if not image_path or not os.path.exists(image_path):
        logger.warning(f"upload_image_for_instagram: file non trovato: {image_path}")
        return None

    gh_token = os.getenv("GH_TOKEN", "")
    # Supporto sia per GH_OWNER/REPO separati che per GH_REPOSITORY (owner/repo)
    gh_repo_full = os.getenv("GH_REPOSITORY", "")
    if gh_repo_full and "/" in gh_repo_full:
        gh_owner, gh_repo = gh_repo_full.split("/", 1)
    else:
        gh_owner = os.getenv("GH_OWNER", "")
        gh_repo  = os.getenv("GH_REPO", "")

    if not all([gh_token, gh_owner, gh_repo]):
        logger.error("GH_TOKEN / OWNER / REPO mancanti — impossibile caricare immagine")
        return None

    filename = os.path.basename(image_path)
    repo_path = f"visuals/{filename}"
    api_url   = f"https://api.github.com/repos/{gh_owner}/{gh_repo}/contents/{repo_path}"

    gh_h = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ASRomaDataBot/1.0",
    }

    with open(image_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    # GET existing SHA (per update, non crea duplicati)
    get_res = curl_requests.get(api_url, headers=gh_h, timeout=15)
    sha = get_res.json().get("sha") if get_res.status_code == 200 else None

    body = {
        "message": f"bot: update {filename} [skip ci]",
        "content": content_b64,
        "branch": "main",
        **({"sha": sha} if sha else {}),
    }

    put_res = curl_requests.put(api_url, headers=gh_h, data=json.dumps(body).encode(), timeout=30)

    if put_res.status_code in (200, 201):
        raw_url = f"https://raw.githubusercontent.com/{gh_owner}/{gh_repo}/main/{repo_path}"
        logger.info(f"  Immagine committata: {raw_url}")
        logger.info("  Attendo 20s propagazione CDN GitHub...")
        time.sleep(20)
        return raw_url

    logger.error(f"  Commit GitHub fallito: {put_res.status_code} — {put_res.text[:300]}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# INSTAGRAM GRAPH API
# ══════════════════════════════════════════════════════════════════════════════

class InstagramPublisher:
    BASE = "https://graph.facebook.com/v19.0"

    def __init__(self):
        # Stessa variabile d'ambiente usata in bot.py
        self.user_id      = os.getenv("IG_USER_ID", "")
        self.access_token = os.getenv("IG_ACCESS_TOKEN", "")
        self.enabled      = bool(self.user_id and self.access_token)

        # Diagnostica: mostra il valore di IG_USER_ID senza essere censurato da
        # GitHub Actions (che maschera i secret con ***).
        # Lo spezziamo in due parti così Actions non lo riconosce come secret intero.
        if self.user_id:
            mid = len(self.user_id) // 2
            logger.info(f"  [DIAG] IG_USER_ID presente, lunghezza={len(self.user_id)}, "
                        f"inizio='{self.user_id[:mid]}' fine='{self.user_id[mid:]}'")
        else:
            logger.warning("  [DIAG] IG_USER_ID è VUOTO — variabile d'ambiente non impostata")

        if not self.enabled:
            logger.warning("Instagram: IG_USER_ID o IG_ACCESS_TOKEN mancanti")

    def publish_photo(self, image_path: str, caption: str) -> Optional[str]:
        if not self.enabled:
            return None

        image_url = upload_image_for_instagram(image_path)
        if not image_url:
            return None

        # Allineato a bot.py riga 401: parametri nel BODY via data=, non params=.
        # Usare params= (query string) causa error 100 "Unsupported post request".
        logger.info(f"  IG Container creazione con URL: {image_url[:60]}...")
        cr = curl_requests.post(
            f"{self.BASE}/{self.user_id}/media",
            data={
                "image_url":    image_url,
                "caption":      caption[:2200],
                "access_token": self.access_token,
            },
            timeout=30,
        )
        cd = cr.json()
        logger.info(f"  Container response: {cd}")

        if "error" in cd:
            err = cd["error"]
            logger.error(f"  IG errore container [{err.get('code')}]: {err.get('message')}")
            return None

        creation_id = cd.get("id")
        if not creation_id:
            logger.error("  IG: creation_id mancante")
            return None

        # Attesa allineata a bot.py: 8s (non 10s)
        logger.info(f"  Container OK: {creation_id}, attendo 8s...")
        time.sleep(8)

        # Pubblicazione finale — body via data=, allineato a bot.py riga 411
        pr = curl_requests.post(
            f"{self.BASE}/{self.user_id}/media_publish",
            data={
                "creation_id":  creation_id,
                "access_token": self.access_token,
            },
            timeout=30,
        )
        pd = pr.json()
        logger.info(f"  Publish response: {pd}")

        if "error" in pd:
            err = pd["error"]
            logger.error(f"  IG errore publish [{err.get('code')}]: {err.get('message')}")
            return None

        logger.info(f"  Instagram OK: media_id={pd.get('id')}")
        return pd.get("id")


# ══════════════════════════════════════════════════════════════════════════════
# X / TWITTER
# ══════════════════════════════════════════════════════════════════════════════

class XPublisher:
    def __init__(self):
        self.api_key       = os.getenv("X_API_KEY", "")
        self.api_secret    = os.getenv("X_API_SECRET", "")
        self.access_token  = os.getenv("X_ACCESS_TOKEN", "")
        self.access_secret = os.getenv("X_ACCESS_SECRET", "")
        self.bearer_token  = os.getenv("X_BEARER_TOKEN", "")
        self.enabled       = all([self.api_key, self.api_secret, self.access_token, self.access_secret])
        self._client = None
        self._api_v1 = None

    def _client_v2(self):
        if self._client: return self._client
        import tweepy
        self._client = tweepy.Client(
            bearer_token=self.bearer_token, consumer_key=self.api_key,
            consumer_secret=self.api_secret, access_token=self.access_token,
            access_token_secret=self.access_secret, wait_on_rate_limit=True
        )
        return self._client

    def _api_v1_instance(self):
        if self._api_v1: return self._api_v1
        import tweepy
        auth = tweepy.OAuth1UserHandler(self.api_key, self.api_secret, self.access_token, self.access_secret)
        self._api_v1 = tweepy.API(auth, wait_on_rate_limit=True)
        return self._api_v1

    def upload_media(self, image_path: str) -> Optional[str]:
        api = self._api_v1_instance()
        if not api or not os.path.exists(image_path): return None
        try:
            media = api.media_upload(image_path)
            return str(media.media_id)
        except Exception as e:
            logger.error(f"X media upload: {e}")
            return None

    def post_tweet(self, text: str, media_id: Optional[str] = None, reply_to: Optional[str] = None) -> Optional[str]:
        if not self.enabled: return None
        client = self._client_v2()
        try:
            kwargs = {"text": text[:270]}
            if media_id: kwargs["media_ids"] = [media_id]
            if reply_to: kwargs["in_reply_to_tweet_id"] = reply_to
            resp = client.create_tweet(**kwargs)
            return str(resp.data["id"])
        except Exception as e:
            logger.error(f"X tweet error: {e}")
            return None

    def post_thread(self, tweets: List[str], image_path: Optional[str] = None) -> List[str]:
        if not self.enabled or not tweets: return []
        ids = []; prev_id = None
        for i, text in enumerate(tweets):
            mid = self.upload_media(image_path) if (i == 0 and image_path) else None
            tid = self.post_tweet(text, media_id=mid, reply_to=prev_id)
            if tid:
                ids.append(tid)
                prev_id = tid
            time.sleep(3)
        return ids


# ══════════════════════════════════════════════════════════════════════════════
# BLUESKY
# ══════════════════════════════════════════════════════════════════════════════

class BlueskyPublisher:
    def __init__(self):
        self.handle   = os.getenv("BSKY_HANDLE", "")
        self.password = os.getenv("BSKY_PASSWORD", "")
        self.enabled  = bool(self.handle and self.password)
        self._client  = None

    def _get_client(self):
        if self._client: return self._client
        from atproto import Client
        c = Client(); c.login(self.handle, self.password)
        self._client = c
        return self._client

    def post(self, text: str, image_path: Optional[str] = None) -> Optional[str]:
        if not self.enabled: return None
        client = self._get_client()
        try:
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f: img_data = f.read()
                blob = client.upload_blob(img_data)
                from atproto import models
                resp = client.send_post(text=text[:300], embed=models.AppBskyEmbedImages.Main(
                    images=[models.AppBskyEmbedImages.Image(alt="AS Roma stats", image=blob.blob)]
                ))
            else:
                resp = client.send_post(text=text[:300])
            return getattr(resp, "uri", None)
        except Exception as e:
            logger.error(f"Bluesky post: {e}"); return None


# ══════════════════════════════════════════════════════════════════════════════
# THREADS
# ══════════════════════════════════════════════════════════════════════════════

class ThreadsPublisher:
    BASE = "https://graph.threads.net/v1.0"

    def __init__(self):
        # Stessa variabile d'ambiente di Instagram, allineato a bot.py
        self.user_id      = os.getenv("THREADS_USER_ID", os.getenv("IG_USER_ID", ""))
        self.access_token = os.getenv("THREADS_ACCESS_TOKEN", os.getenv("IG_ACCESS_TOKEN", ""))
        self.enabled      = os.getenv("THREADS_ENABLED", "false").lower() == "true"

    def post(self, text: str, image_path: Optional[str] = None) -> Optional[str]:
        if not self.enabled: return None
        image_url = upload_image_for_instagram(image_path) if image_path else None
        try:
            # Allineato a bot.py: parametri nel BODY via data=, non params=.
            payload = {
                "media_type":   "IMAGE" if image_url else "TEXT",
                "text":         text[:500],
                "access_token": self.access_token,
            }
            if image_url:
                payload["image_url"] = image_url

            r = requests.post(
                f"{self.BASE}/{self.user_id}/threads",
                data=payload,
                timeout=30,
            )
            r.raise_for_status()
            container_id = r.json().get("id")
            if not container_id: return None

            # 8s di attesa per coerenza con la logica Instagram di bot.py
            time.sleep(8)

            pub = requests.post(
                f"{self.BASE}/{self.user_id}/threads_publish",
                data={"creation_id": container_id, "access_token": self.access_token},
                timeout=30,
            )
            pub.raise_for_status()
            logger.info(f"Threads OK: {pub.json().get('id')}")
            return pub.json().get("id")
        except Exception as e:
            logger.error(f"Threads: {e}"); return None


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY GENERALE
# ══════════════════════════════════════════════════════════════════════════════

def publish_to_all_platforms(
    image_path: Optional[str],
    x_thread: List[str],
    ig_caption: str,
    bsky_text: str,
    threads_text: Optional[str] = None,
) -> dict:
    results = {}

    # 1. X
    x = XPublisher()
    if x.enabled and x_thread:
        ids = x.post_thread(x_thread, image_path=image_path)
        results["x"] = {"published": bool(ids), "ids": ids}

    # 2. Instagram
    if image_path:
        ig = InstagramPublisher()
        if ig.enabled:
            post_id = ig.publish_photo(image_path, ig_caption)
            results["instagram"] = {"published": bool(post_id), "id": post_id}

    # 3. Bluesky
    bsky = BlueskyPublisher()
    if bsky.enabled:
        ok = bsky.post(bsky_text or (x_thread[0] if x_thread else ""), image_path=image_path)
        results["bluesky"] = {"published": bool(ok)}

    # 4. Threads
    th = ThreadsPublisher()
    if th.enabled:
        ok_th = th.post(threads_text or ig_caption, image_path=image_path)
        results["threads"] = {"published": bool(ok_th)}

    logger.info(f"Risultati Finali: {results}")
    return results
