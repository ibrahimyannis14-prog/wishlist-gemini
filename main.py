import os
import re
import json
from urllib.parse import urlparse, urljoin
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from scrapling import Fetcher, StealthyFetcher

app = FastAPI(title="Wishlist Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def guess_shop_from_url(url_string: str) -> str:
    try:
        parsed_uri = urlparse(url_string)
        host = parsed_uri.netloc.replace('www.', '')
        parts = host.split('.')
        name = parts[-2] if len(parts) > 2 else parts[0]
        return name.capitalize()
    except Exception:
        return ""


def parse_price_string(price_str: str):
    if not price_str:
        return None
    # Garde uniquement chiffres, points, virgules
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    if not cleaned:
        return None
    # Cas "1.299,00" (format FR) -> "1299.00"
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        # "49,90" -> décimale ; "1,299" -> millier (rare sans point)
        if len(cleaned.split(',')[-1]) == 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_jsonld_product(response):
    """Cherche un bloc JSON-LD schema.org/Product, souvent la source la plus fiable."""
    scripts = response.css('script[type="application/ld+json"]::text').getall()
    for raw in scripts:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        # Gère aussi le cas @graph
        flat = []
        for c in candidates:
            if isinstance(c, dict) and "@graph" in c:
                flat.extend(c["@graph"])
            else:
                flat.append(c)
        for item in flat:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type", "")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "Product" in types:
                offers = item.get("offers")
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                offers = offers or {}
                image = item.get("image")
                if isinstance(image, list):
                    image = image[0] if image else None
                if isinstance(image, dict):
                    image = image.get("url")
                return {
                    "title": item.get("name"),
                    "image": image,
                    "price": parse_price_string(str(offers.get("price"))) if offers.get("price") else None,
                    "availability": offers.get("availability", ""),
                }
    return None


def extract_price_from_meta(response):
    for selector in [
        'meta[property="product:price:amount"]::attr(content)',
        'meta[property="og:price:amount"]::attr(content)',
        '[itemprop="price"]::attr(content)',
        '[itemprop="price"]::text',
        'meta[name="twitter:data1"]::attr(content)',
    ]:
        price_str = response.css(selector).get()
        if price_str:
            price = parse_price_string(price_str)
            if price is not None:
                return price
    return None


def extract_data(response, url: str):
    jsonld = extract_jsonld_product(response) or {}

    title = jsonld.get("title") or response.css('meta[property="og:title"]::attr(content)').get()
    if not title:
        title = response.css('title::text').get()

    shop = response.css('meta[property="og:site_name"]::attr(content)').get()

    image = jsonld.get("image") or response.css('meta[property="og:image"]::attr(content)').get()
    if not image:
        image = response.css('meta[name="twitter:image"]::attr(content)').get()
    if not image:
        image = response.css('meta[itemprop="image"]::attr(content)').get()
    if not image:
        image = response.css('link[rel="image_src"]::attr(href)').get()
    if image:
        image = urljoin(url, image.strip())  # résout les URLs relatives / protocol-relative

    price = jsonld.get("price")
    if price is None:
        price = extract_price_from_meta(response)

    availability_raw = (jsonld.get("availability") or "").lower()
    availability = "outofstock" if "outofstock" in availability_raw else (
        "instock" if "instock" in availability_raw else "Inconnue"
    )

    title = title.strip() if title else ""
    shop = shop.strip() if shop else guess_shop_from_url(url)

    return {
        "title": title,
        "shop": shop,
        "image": image,
        "price": price,
        "availability": availability,
    }


def has_enough_data(data: dict) -> bool:
    return bool(data.get("price")) and bool(data.get("image"))


@app.get("/api/scrape")
def scrape_url(url: str = Query(..., description="Lien de l'article à scrapper")):
    if not url:
        raise HTTPException(status_code=400, detail="URL manquante")

    print(f"[SCRAPE] Demande reçue pour : {url}")

    # 1er essai : fetch HTTP simple (rapide)
    try:
        response = Fetcher().get(url, timeout=15)
        data = extract_data(response, url)
    except Exception as e:
        print(f"[SCRAPE] Échec fetch simple : {e}")
        data = {"title": "", "shop": guess_shop_from_url(url), "image": None, "price": None, "availability": "Inconnue"}

    # 2e essai si données incomplètes : fetch avec navigateur headless (JS + anti-bot)
    if not has_enough_data(data):
        try:
            print("[SCRAPE] Données incomplètes, tentative avec StealthyFetcher...")
            response = StealthyFetcher().get(url, timeout=25)
            data2 = extract_data(response, url)
            # fusionne : on garde ce qu'on avait déjà si le 2e essai ne trouve rien de mieux
            for key in ["title", "shop", "image", "price"]:
                if not data.get(key) and data2.get(key):
                    data[key] = data2[key]
            if data.get("availability") == "Inconnue" and data2.get("availability") != "Inconnue":
                data["availability"] = data2["availability"]
        except Exception as e:
            print(f"[SCRAPE] Échec StealthyFetcher : {e}")

    print(f"[SCRAPE] Résultat : {data}")
    return data
