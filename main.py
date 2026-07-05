import os
import re
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from scrapling import Fetcher
from urllib.parse import urlparse

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

# Fonction pour extraire et nettoyer le prix (ex: "49,90 €" -> 49.90)
def extract_price(response) -> float:
    # 1. Cherche dans les balises E-commerce classiques (OpenGraph Product)
    price_str = response.css('meta[property="product:price:amount"]::attr(content)').get()
    
    if not price_str:
        price_str = response.css('meta[property="og:price:amount"]::attr(content)').get()
        
    # 2. Cherche dans les balises Schema.org (très utilisées par les boutiques)
    if not price_str:
        price_str = response.css('[itemprop="price"]::attr(content)').get()
        
    if not price_str:
        price_str = response.css('[itemprop="price"]::text').get()

    # Si on trouve un texte, on en extrait uniquement les chiffres
    if price_str:
        # Trouve les nombres avec point ou virgule
        match = re.search(r'[\d]+[.,]?[\d]*', price_str)
        if match:
            try:
                return float(match.group().replace(',', '.'))
            except ValueError:
                return None
    return None

@app.get("/api/scrape")
def scrape_url(url: str = Query(..., description="Lien de l'article à scrapper")):
    if not url:
        raise HTTPException(status_code=400, detail="URL manquante")
    
    print(f"[SCRAPE] Demande reçue pour : {url}")
    
    try:
        fetcher = Fetcher()
        response = fetcher.get(url)
        
        # --- TITRE ---
        title = response.css('meta[property="og:title"]::attr(content)').get()
        if not title:
            title = response.css('title::text').get()
            
        # --- BOUTIQUE ---
        shop = response.css('meta[property="og:site_name"]::attr(content)').get()
        
        # --- IMAGE (Avec filets de sécurité) ---
        image = response.css('meta[property="og:image"]::attr(content)').get()
        if not image: # Filet 1 : Balise Twitter
            image = response.css('meta[name="twitter:image"]::attr(content)').get()
        if not image: # Filet 2 : Balise Schema.org générique
            image = response.css('meta[itemprop="image"]::attr(content)').get()
        if not image: # Filet 3 : Balise link image_src
            image = response.css('link[rel="image_src"]::attr(href)').get()
            
        # --- PRIX ---
        price = extract_price(response)
        
        # Nettoyage final
        title = title.strip() if title else ""
        shop = shop.strip() if shop else guess_shop_from_url(url)
        image = image.strip() if image else None
        
        result = {
            "title": title,
            "shop": shop,
            "image": image,
            "price": price,
            "availability": "Inconnue"
        }
        
        print(f"[SCRAPE] Succès ! Renvoi des données au frontend.")
        return result

    except Exception as e:
        print(f"[SCRAPE] ERREUR : {str(e)}")
        return {
            "title": "", 
            "shop": guess_shop_from_url(url), 
            "image": None, 
            "price": None, 
            "availability": "Inconnue"
        }
