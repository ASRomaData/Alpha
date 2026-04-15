"""
ASRomaData Bot — Publishers
Pubblica su Instagram (Graph API), X (Tweepy v4), Bluesky (atproto), Threads.
"""

import os
import time
import base64
import logging
import requests
from typing import Optional, List

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# INSTAGRAM GRAPH API
# ──────────────────────────────────────────────────────────────────

class InstagramPublisher:
    """Pubblica immagini e carousel su Instagram via Graph API."""

    BASE_URL = "https://graph.facebook.com/v19.0"

    def __init__(self):
        self.user_id      = os.getenv("IG_USER_ID", "")
        self.access_token = os.getenv("IG_ACCESS_TOKEN", "")
        self.enabled      = bool(self.user_id and self.access_token)
        if not self.enabled:
            logger.warning("Instagram: IG_USER_ID o IG_ACCESS_TOKEN mancanti")

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        url = f"{self.BASE_URL}/{endpoint}"
        data["access_token"] = self.access_token
        try:
            r = requests.post(url, data=data, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Instagram API error: {e}")
            return None

    def publish_photo(self, image_url: str, caption: str) -> Optional[str]:
        """
        Pubblica una singola foto su Instagram.
        image_url: URL pubblico dell'immagine (deve essere accessibile da Facebook)
        Restituisce l'ID del post pubblicato.
        """
        if not self.enabled:
            return None

        # Step 1: crea media container
        container = self._post(f"{self.user_id}/media", {
            "image_url": image_url,
            "caption":   caption,
        })
        if not container or "id" not in container:
            logger.error("Instagram: creazione container fallita")
            return None

        container_id = container["id"]
        time.sleep(5)  # aspetta che il container sia pronto

        # Step 2: pubblica
        result = self._post(f"{self.user_id}/media_publish", {
            "creation_id": container_id,
        })
        if result and "id" in result:
            logger.info(f"Instagram: post pubblicato (id={result['id']})")
            return result["id"]
        return None

    def publish_carousel(self, image_urls: List[str], caption: str) -> Optional[str]:
        """Pubblica un carousel (max 10 immagini)."""
        if not self.enabled or not image_urls:
            return None

        # Crea i container per ogni immagine
        child_ids = []
        for url in image_urls[:10]:
            c = self._post(f"{self.user_id}/media", {
                "image_url":  url,
                "is_carousel_item": "true",
            })
            if c and "id" in c:
                child_ids.append(c["id"])
            time.sleep(2)

        if not child_ids:
            return None

        # Crea container carousel
        carousel = self._post(f"{self.user_id}/media", {
            "media_type": "CAROUSEL",
            "children":   ",".join(child_ids),
            "caption":    caption,
        })
        if not carousel or "id" not in carousel:
            return None

        time.sleep(5)

        # Pubblica
        result = self._post(f"{self.user_id}/media_publish", {
            "creation_id": carousel["id"],
        })
        if result and "id" in result:
            logger.info(f"Instagram: carousel pubblicato (id={result['id']})")
            return result["id"]
        return None


# ──────────────────────────────────────────────────────────────────
# X / TWITTER (Tweepy v4)
# ──────────────────────────────────────────────────────────────────

class XPublisher:
    """Pubblica tweet e thread su X (Twitter) API v2."""

    def __init__(self):
        self.api_key        = os.getenv("X_API_KEY", "")
        self.api_secret     = os.getenv("X_API_SECRET", "")
        self.access_token   = os.getenv("X_ACCESS_TOKEN", "")
        self.access_secret  = os.getenv("X_ACCESS_SECRET", "")
        self.bearer_token   = os.getenv("X_BEARER_TOKEN", "")
        self.enabled = all([self.api_key, self.api_secret,
                            self.access_token, self.access_secret])
        self._client = None

        if not self.enabled:
            logger.warning("X: credenziali mancanti")

    def _get_client(self):
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
            return self._client
        except ImportError:
            logger.error("tweepy non installato")
        except Exception as e:
            logger.error(f"X client init error: {e}")
        return None

    def _get_api_v1(self):
        """API v1.1 per upload media."""
        try:
            import tweepy
            auth = tweepy.OAuth1UserHandler(
                self.api_key, self.api_secret,
                self.access_token, self.access_secret
            )
            return tweepy.API(auth, wait_on_rate_limit=True)
        except Exception as e:
            logger.error(f"X API v1 init error: {e}")
        return None

    def upload_media(self, image_path: str) -> Optional[str]:
        """Carica un'immagine su X e restituisce il media_id."""
        api = self._get_api_v1()
        if not api:
            return None
        try:
            media = api.media_upload(image_path)
            return str(media.media_id)
        except Exception as e:
            logger.error(f"X media upload error: {e}")
        return None

    def post_tweet(self, text: str, media_id: Optional[str] = None,
                   reply_to: Optional[str] = None) -> Optional[str]:
        """Posta un singolo tweet. Restituisce il tweet_id."""
        if not self.enabled:
            return None
        client = self._get_client()
        if not client:
            return None
        try:
            kwargs = {"text": text[:270]}
            if media_id:
                kwargs["media_ids"] = [media_id]
            if reply_to:
                kwargs["in_reply_to_tweet_id"] = reply_to
            resp = client.create_tweet(**kwargs)
            tweet_id = str(resp.data["id"])
            logger.info(f"X: tweet pubblicato (id={tweet_id})")
            return tweet_id
        except Exception as e:
            logger.error(f"X tweet error: {e}")
        return None

    def post_thread(self, tweets: List[str],
                    image_path: Optional[str] = None) -> List[str]:
        """
        Posta un thread di tweet.
        Allega l'immagine solo al primo tweet.
        Restituisce lista di tweet_id pubblicati.
        """
        if not self.enabled or not tweets:
            return []

        tweet_ids = []
        prev_id   = None

        for i, text in enumerate(tweets):
            media_id = None
            if i == 0 and image_path:
                media_id = self.upload_media(image_path)

            tweet_id = self.post_tweet(text, media_id=media_id, reply_to=prev_id)
            if tweet_id:
                tweet_ids.append(tweet_id)
                prev_id = tweet_id
            time.sleep(3)  # evita rate limiting

        return tweet_ids


# ──────────────────────────────────────────────────────────────────
# BLUESKY (AT Protocol)
# ──────────────────────────────────────────────────────────────────

class BlueskyPublisher:
    """Pubblica su Bluesky via atproto."""

    def __init__(self):
        self.handle   = os.getenv("BSKY_HANDLE", "")
        self.password = os.getenv("BSKY_PASSWORD", "")
        self.enabled  = bool(self.handle and self.password)
        self._client  = None
        if not self.enabled:
            logger.warning("Bluesky: BSKY_HANDLE o BSKY_PASSWORD mancanti")

    def _get_client(self):
        if self._client:
            return self._client
        try:
            from atproto import Client
            c = Client()
            c.login(self.handle, self.password)
            self._client = c
            return c
        except ImportError:
            logger.error("atproto non installato")
        except Exception as e:
            logger.error(f"Bluesky login error: {e}")
        return None

    def post(self, text: str, image_path: Optional[str] = None) -> bool:
        """Pubblica un post su Bluesky (max 300 caratteri)."""
        if not self.enabled:
            return False
        client = self._get_client()
        if not client:
            return False
        try:
            text = text[:300]
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    img_data = f.read()
                # Determina mime type
                mime = "image/jpeg" if image_path.lower().endswith(".jpg") else "image/png"
                blob = client.upload_blob(img_data)
                from atproto import models
                client.send_post(
                    text=text,
                    embed=models.AppBskyEmbedImages.Main(
                        images=[models.AppBskyEmbedImages.Image(
                            alt="AS Roma stats · @ASRomaData",
                            image=blob.blob,
                        )]
                    )
                )
            else:
                client.send_post(text=text)
            logger.info("Bluesky: post pubblicato")
            return True
        except Exception as e:
            logger.error(f"Bluesky post error: {e}")
        return False


# ──────────────────────────────────────────────────────────────────
# THREADS (via Instagram Graph API — se abilitato)
# ──────────────────────────────────────────────────────────────────

class ThreadsPublisher:
    """
    Pubblica su Threads via Threads API (Meta).
    Richiede Threads API access — in alternativa usa il cross-posting
    automatico da Instagram se configurato nel Business Manager.
    """

    BASE_URL = "https://graph.threads.net/v1.0"

    def __init__(self):
        self.user_id      = os.getenv("THREADS_USER_ID", os.getenv("IG_USER_ID", ""))
        self.access_token = os.getenv("THREADS_ACCESS_TOKEN", os.getenv("IG_ACCESS_TOKEN", ""))
        self.enabled      = os.getenv("THREADS_ENABLED", "false").lower() == "true"
        if self.enabled and not (self.user_id and self.access_token):
            logger.warning("Threads: credenziali mancanti nonostante THREADS_ENABLED=true")
            self.enabled = False

    def post(self, text: str, image_url: Optional[str] = None) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            # Crea media container
            data: dict = {
                "media_type": "IMAGE" if image_url else "TEXT",
                "text": text[:500],
                "access_token": self.access_token,
            }
            if image_url:
                data["image_url"] = image_url

            r = requests.post(
                f"{self.BASE_URL}/{self.user_id}/threads",
                data=data, timeout=30
            )
            r.raise_for_status()
            container_id = r.json().get("id")
            if not container_id:
                return None

            time.sleep(5)

            # Pubblica
            pub = requests.post(
                f"{self.BASE_URL}/{self.user_id}/threads_publish",
                data={"creation_id": container_id, "access_token": self.access_token},
                timeout=30
            )
            pub.raise_for_status()
            post_id = pub.json().get("id")
            logger.info(f"Threads: post pubblicato (id={post_id})")
            return post_id
        except Exception as e:
            logger.error(f"Threads error: {e}")
        return None


# ──────────────────────────────────────────────────────────────────
# IMAGE HOST: GitHub raw URL (gratuito, usa il repo)
# ──────────────────────────────────────────────────────────────────

def upload_image_to_github(local_path: str, github_path: str) -> Optional[str]:
    """
    Carica un'immagine nel repository GitHub e restituisce URL pubblico.
    Usato per fornire a Instagram Graph API un URL pubblico dell'immagine.
    Richiede: GH_TOKEN, GH_OWNER, GH_REPO environment variables.
    """
    token  = os.getenv("GH_TOKEN", "")
    owner  = os.getenv("GH_OWNER", "")
    repo   = os.getenv("GH_REPO", "")

    if not all([token, owner, repo, os.path.exists(local_path)]):
        return None

    try:
        with open(local_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()

        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{github_path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Controlla se esiste già (per aggiornare)
        existing = requests.get(url, headers=headers, timeout=15)
        payload: dict = {
            "message": f"bot: upload {github_path}",
            "content": content,
        }
        if existing.status_code == 200:
            payload["sha"] = existing.json()["sha"]

        r = requests.put(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()

        # URL raw per accesso pubblico
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{github_path}"
        logger.info(f"GitHub upload: {raw_url}")
        return raw_url
    except Exception as e:
        logger.error(f"GitHub upload error: {e}")
    return None


# ──────────────────────────────────────────────────────────────────
# PUBLISH ALL: utility per pubblicare su tutte le piattaforme
# ──────────────────────────────────────────────────────────────────

def publish_to_all_platforms(
    image_path: Optional[str],
    x_thread: List[str],
    ig_caption: str,
    bsky_text: str,
    threads_text: Optional[str] = None,
) -> dict:
    """
    Pubblica il contenuto su tutte le piattaforme configurate.
    Restituisce dict con risultati per piattaforma.
    """
    results = {}

    # ── X thread ─────────────────────────────────────────────────
    x_pub = XPublisher()
    if x_thread:
        ids = x_pub.post_thread(x_thread, image_path=image_path)
        results["x"] = {"published": bool(ids), "tweet_ids": ids}
        logger.info(f"X: {len(ids)} tweet pubblicati")
        time.sleep(3)

    # ── Instagram ────────────────────────────────────────────────
    if image_path:
        ig_pub = InstagramPublisher()
        # Carica immagine su GitHub per URL pubblico
        github_img_path = f"visuals/latest_{os.path.basename(image_path)}"
        img_url = upload_image_to_github(image_path, github_img_path)
        if img_url:
            post_id = ig_pub.publish_photo(img_url, ig_caption)
            results["instagram"] = {"published": bool(post_id), "post_id": post_id}
        else:
            logger.warning("Instagram: impossibile ottenere URL pubblico immagine")
            results["instagram"] = {"published": False}

    # ── Bluesky ──────────────────────────────────────────────────
    bsky_pub = BlueskyPublisher()
    ok = bsky_pub.post(bsky_text, image_path=image_path)
    results["bluesky"] = {"published": ok}
    time.sleep(2)

    # ── Threads ──────────────────────────────────────────────────
    th_pub = ThreadsPublisher()
    if th_pub.enabled:
        img_url_th = results.get("instagram", {}).get("img_url")
        ok_th = th_pub.post(threads_text or ig_caption, image_url=img_url_th)
        results["threads"] = {"published": bool(ok_th)}

    logger.info(f"Pubblicazione completata: {results}")
    return results
