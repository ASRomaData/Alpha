"""
ASRomaData Bot — Publishers
==============================
Pubblica su Instagram (Graph API), X (Tweepy v4), Bluesky (atproto), Threads.

Instagram richiede un URL pubblico per l'immagine.
Strategia upload immagine (gratuita, zero auth):
  1. catbox.moe  — permanente, nessun account, max 200MB
  2. tmpfiles.org — 24h retention, nessun account
  3. 0x0.st       — permanente, nessun account
"""

import base64
import logging
import os
import time
from typing import List, Optional

import requests
try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = requests  # fallback

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE HOSTING — catbox.moe + fallback chain
# ══════════════════════════════════════════════════════════════════════════════

def upload_image_for_instagram(image_path: str) -> Optional[str]:
    """
    Committa l'immagine su GitHub e restituisce raw.githubusercontent.com URL.
    Stesso approccio del bot RomaStats (funzionante).
    Repo deve essere pubblico. Richiede GH_TOKEN + GH_OWNER + GH_REPO.
    """
    if not image_path or not os.path.exists(image_path):
        logger.warning(f"upload_image_for_instagram: file non trovato: {image_path}")
        return None

    gh_token = os.getenv("GH_TOKEN", "")
    gh_owner = os.getenv("GH_OWNER", "")
    gh_repo  = os.getenv("GH_REPO", "")

    if not all([gh_token, gh_owner, gh_repo]):
        logger.error("GH_TOKEN / GH_OWNER / GH_REPO mancanti — impossibile caricare immagine")
        return None

    filename = os.path.basename(image_path)
    # Store images in visuals/ folder in the repo
    repo_path = f"visuals/{filename}"
    api_url   = f"https://api.github.com/repos/{gh_owner}/{gh_repo}/contents/{repo_path}"
    gh_h = {
        "Authorization":        f"Bearer {gh_token}",
        "Accept":               "application/vnd.github+json",
        "Content-Type":         "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":           "ASRomaDataBot/1.0",   # required by GitHub API
    }

    with open(image_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    # GET existing SHA (required to update an existing file)
    get_res = curl_requests.get(api_url, headers=gh_h, timeout=15)
    sha = get_res.json().get("sha") if get_res.status_code == 200 else None

    body = {
        "message": f"bot: update {filename} [skip ci]",
        "content": content_b64,
        "branch":  "main",
        **({"sha": sha} if sha else {}),
    }
    import json as _json
    put_res = curl_requests.put(api_url, headers=gh_h, data=_json.dumps(body).encode(), timeout=30)

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
    """
    Instagram Graph API publisher.
    Usa curl_cffi (stesso approccio del bot RomaStats funzionante).
    Passa parametri come form data — NON come JSON.
    """

    BASE = "https://graph.facebook.com/v19.0"

    def __init__(self):
        self.user_id      = os.getenv("IG_USER_ID", "")
        self.access_token = os.getenv("IG_ACCESS_TOKEN", "")
        self.enabled      = bool(self.user_id and self.access_token)
        if not self.enabled:
            logger.warning("Instagram: IG_USER_ID o IG_ACCESS_TOKEN mancanti")

    def publish_photo(self, image_path: str, caption: str) -> Optional[str]:
        if not self.enabled:
            return None

        image_url = upload_image_for_instagram(image_path)
        if not image_url:
            logger.error("Instagram: impossibile ottenere URL pubblico immagine")
            return None

        # Step 1: crea container (form-encoded, curl_cffi — identico a RomaStats)
        logger.info(f"  Container con URL: {image_url[:80]}...")
        cr = curl_requests.post(
            f"{self.BASE}/{self.user_id}/media",
            data={"image_url": image_url, "caption": caption[:2200], "access_token": self.access_token},
            timeout=30,
        )
        cd = cr.json()
        logger.info(f"  Container response: {cd}")
        if "error" in cd:
            e = cd["error"]
            logger.error(f"  IG errore container [{e.get('code')}]: {e.get('message')}")
            return None
        creation_id = cd.get("id")
        if not creation_id:
            logger.error("  IG: creation_id mancante")
            return None

        # Step 2: pubblica
        logger.info(f"  Container OK: {creation_id}, attendo 8s...")
        time.sleep(8)
        pr = curl_requests.post(
            f"{self.BASE}/{self.user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": self.access_token},
            timeout=30,
        )
        pd = pr.json()
        logger.info(f"  Publish response: {pd}")
        if "error" in pd:
            e = pd["error"]
            logger.error(f"  IG errore publish [{e.get('code')}]: {e.get('message')}")
            return None
        media_id = pd.get("id")
        logger.info(f"  Instagram OK: media_id={media_id}")
        return media_id

    def publish_carousel(self, image_paths: List[str], caption: str) -> Optional[str]:
        """Pubblica carousel (max 10 immagini)."""
        if not self.enabled or not image_paths:
            return None
        child_ids = []
        for path in image_paths[:10]:
            url = upload_image_for_instagram(path)
            if not url:
                continue
            cr = curl_requests.post(
                f"{self.BASE}/{self.user_id}/media",
                data={"image_url": url, "is_carousel_item": "true", "access_token": self.access_token},
                timeout=30,
            )
            cd = cr.json()
            if "id" in cd:
                child_ids.append(cd["id"])
            time.sleep(3)
        if not child_ids:
            return None
        carousel = curl_requests.post(
            f"{self.BASE}/{self.user_id}/media",
            data={"media_type": "CAROUSEL", "children": ",".join(child_ids),
                  "caption": caption[:2200], "access_token": self.access_token},
            timeout=30,
        )
        cd = carousel.json()
        if "id" not in cd:
            return None
        time.sleep(8)
        pr = curl_requests.post(
            f"{self.BASE}/{self.user_id}/media_publish",
            data={"creation_id": cd["id"], "access_token": self.access_token},
            timeout=30,
        )
        pd = pr.json()
        media_id = pd.get("id")
        if media_id:
            logger.info(f"  Instagram carousel OK: media_id={media_id}")
        return media_id


# ══════════════════════════════════════════════════════════════════════════════
# X / TWITTER (Tweepy v4)
# ══════════════════════════════════════════════════════════════════════════════

class XPublisher:

    def __init__(self):
        self.api_key       = os.getenv("X_API_KEY", "")
        self.api_secret    = os.getenv("X_API_SECRET", "")
        self.access_token  = os.getenv("X_ACCESS_TOKEN", "")
        self.access_secret = os.getenv("X_ACCESS_SECRET", "")
        self.bearer_token  = os.getenv("X_BEARER_TOKEN", "")
        self.enabled       = all([self.api_key, self.api_secret,
                                  self.access_token, self.access_secret])
        self._client       = None
        self._api_v1       = None
        if not self.enabled:
            logger.warning("X: credenziali mancanti")

    def _client_v2(self):
        if self._client:
            return self._client
        try:
            import tweepy
            self._client = tweepy.Client(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_secret,
                wait_on_rate_limit=True,
            )
        except Exception as e:
            logger.error(f"X Client v2: {e}")
        return self._client

    def _api_v1_instance(self):
        if self._api_v1:
            return self._api_v1
        try:
            import tweepy
            auth = tweepy.OAuth1UserHandler(
                self.api_key, self.api_secret,
                self.access_token, self.access_secret,
            )
            self._api_v1 = tweepy.API(auth, wait_on_rate_limit=True)
        except Exception as e:
            logger.error(f"X API v1: {e}")
        return self._api_v1

    def upload_media(self, image_path: str) -> Optional[str]:
        api = self._api_v1_instance()
        if not api or not os.path.exists(image_path):
            return None
        try:
            media = api.media_upload(image_path)
            return str(media.media_id)
        except Exception as e:
            logger.error(f"X media upload: {e}")
        return None

    def post_tweet(self, text: str, media_id: Optional[str] = None,
                   reply_to: Optional[str] = None) -> Optional[str]:
        if not self.enabled:
            return None
        client = self._client_v2()
        if not client:
            return None
        try:
            kwargs: dict = {"text": text[:270]}
            if media_id:
                kwargs["media_ids"] = [media_id]
            if reply_to:
                kwargs["in_reply_to_tweet_id"] = reply_to
            resp = client.create_tweet(**kwargs)
            tweet_id = str(resp.data["id"])
            logger.info(f"X tweet: {tweet_id}")
            return tweet_id
        except Exception as e:
            logger.error(f"X tweet error: {e}")
        return None

    def post_thread(self, tweets: List[str],
                    image_path: Optional[str] = None) -> List[str]:
        if not self.enabled or not tweets:
            return []
        ids     = []
        prev_id = None
        for i, text in enumerate(tweets):
            media_id = None
            if i == 0 and image_path:
                media_id = self.upload_media(image_path)
            tweet_id = self.post_tweet(text, media_id=media_id, reply_to=prev_id)
            if tweet_id:
                ids.append(tweet_id)
                prev_id = tweet_id
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

    def post(self, text: str, image_path: Optional[str] = None) -> Optional[str]:
        """Single post. Returns post URI or None."""
        if not self.enabled:
            return None
        client = self._get_client()
        if not client:
            return None
        try:
            text = text[:300]
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    img_data = f.read()
                blob = client.upload_blob(img_data)
                from atproto import models
                resp = client.send_post(
                    text=text,
                    embed=models.AppBskyEmbedImages.Main(
                        images=[models.AppBskyEmbedImages.Image(
                            alt="AS Roma stats · @ASRomaData",
                            image=blob.blob,
                        )]
                    ),
                )
            else:
                resp = client.send_post(text=text)
            uri = getattr(resp, "uri", None)
            cid = getattr(resp, "cid", None)
            logger.info(f"Bluesky: pubblicato OK — {uri}")
            return uri
        except Exception as e:
            logger.error(f"Bluesky post: {e}")
        return None

    def post_thread(self, texts: List[str], image_path: Optional[str] = None) -> bool:
        """
        Pubblica un thread Bluesky: il primo post include l'immagine,
        i successivi sono reply in catena.
        """
        if not self.enabled or not texts:
            return False
        client = self._get_client()
        if not client:
            return False

        parent_ref = None
        root_ref   = None

        for i, text in enumerate(texts):
            try:
                text = text[:300]
                kwargs: dict = {"text": text}

                # Prima immagine solo sul primo post
                if i == 0 and image_path and os.path.exists(image_path):
                    with open(image_path, "rb") as f:
                        img_data = f.read()
                    blob = client.upload_blob(img_data)
                    from atproto import models
                    kwargs["embed"] = models.AppBskyEmbedImages.Main(
                        images=[models.AppBskyEmbedImages.Image(
                            alt="AS Roma stats · @ASRomaData",
                            image=blob.blob,
                        )]
                    )

                # Reply chain
                if parent_ref:
                    from atproto import models
                    kwargs["reply_to"] = models.AppBskyFeedPost.ReplyRef(
                        parent=parent_ref,
                        root=root_ref or parent_ref,
                    )

                resp = client.send_post(**kwargs)
                uri  = getattr(resp, "uri", "")
                cid  = getattr(resp, "cid", "")
                logger.info(f"Bluesky thread {i+1}/{len(texts)}: {uri}")

                from atproto import models
                ref = models.ComAtprotoRepoStrongRef.Main(uri=uri, cid=cid)
                if i == 0:
                    root_ref = ref
                parent_ref = ref

                time.sleep(2)

            except Exception as e:
                logger.error(f"Bluesky thread post {i+1}: {e}")
                break

        return parent_ref is not None


# ══════════════════════════════════════════════════════════════════════════════
# THREADS (Meta Threads API)
# ══════════════════════════════════════════════════════════════════════════════

class ThreadsPublisher:

    BASE = "https://graph.threads.net/v1.0"

    def __init__(self):
        self.user_id      = os.getenv("THREADS_USER_ID", os.getenv("IG_USER_ID", ""))
        self.access_token = os.getenv("THREADS_ACCESS_TOKEN", os.getenv("IG_ACCESS_TOKEN", ""))
        self.enabled      = os.getenv("THREADS_ENABLED", "false").lower() == "true"
        if self.enabled and not (self.user_id and self.access_token):
            logger.warning("Threads: THREADS_ENABLED=true ma credenziali mancanti")
            self.enabled = False

    def post(self, text: str, image_path: Optional[str] = None) -> Optional[str]:
        if not self.enabled:
            return None
        image_url = upload_image_for_instagram(image_path) if image_path else None
        try:
            data: dict = {
                "media_type":   "IMAGE" if image_url else "TEXT",
                "text":         text[:500],
                "access_token": self.access_token,
            }
            if image_url:
                data["image_url"] = image_url
            elif image_path and not image_url:
                logger.warning("Threads: upload immagine fallito, pubblico solo testo")
                data["media_type"] = "TEXT"

            r = requests.post(
                f"{self.BASE}/{self.user_id}/threads",
                data=data, timeout=30,
            )
            logger.info(f"  Threads container response: {r.status_code} {r.text[:200]}")
            r.raise_for_status()
            container_id = r.json().get("id")
            if not container_id:
                return None

            time.sleep(5)
            pub = requests.post(
                f"{self.BASE}/{self.user_id}/threads_publish",
                data={"creation_id": container_id, "access_token": self.access_token},
                timeout=30,
            )
            pub.raise_for_status()
            post_id = pub.json().get("id")
            logger.info(f"Threads: pubblicato (id={post_id})")
            return post_id
        except Exception as e:
            logger.error(f"Threads: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PUBLISH ALL — utility
# ══════════════════════════════════════════════════════════════════════════════

def publish_to_all_platforms(
    image_path: Optional[str],
    x_thread: List[str],
    ig_caption: str,
    bsky_text: str,
    threads_text: Optional[str] = None,
) -> dict:
    results = {}

    # ── X ────────────────────────────────────────────────────────
    x = XPublisher()
    if x_thread:
        ids = x.post_thread(x_thread, image_path=image_path)
        results["x"] = {"published": bool(ids), "tweet_ids": ids}
        time.sleep(3)

    # ── Instagram ────────────────────────────────────────────────
    if image_path:
        ig = InstagramPublisher()
        post_id = ig.publish_photo(image_path, ig_caption)
        results["instagram"] = {"published": bool(post_id), "post_id": post_id}

    # ── Bluesky ──────────────────────────────────────────────────
    bsky = BlueskyPublisher()
    if len(x_thread) > 1:
        # Pubblica come thread se ci sono più parti (pre-match / post-match)
        ok = bsky.post_thread(x_thread, image_path=image_path)
    else:
        # Post singolo (weekly o testo breve)
        ok = bool(bsky.post(bsky_text or (x_thread[0] if x_thread else ""), image_path=image_path))
    results["bluesky"] = {"published": ok}
    time.sleep(2)

    # ── Threads ──────────────────────────────────────────────────
    th = ThreadsPublisher()
    if th.enabled:
        ok_th = th.post(threads_text or ig_caption, image_path=image_path)
        results["threads"] = {"published": bool(ok_th)}

    logger.info(f"Pubblicazione completata: {results}")
    return results
