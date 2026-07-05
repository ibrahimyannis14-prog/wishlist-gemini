from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from scrapling import Fetcher
from urllib.parse import urlparse

# On crée le serveur web
app = FastAPI(title="Wishlist Scraper API")

# On autorise ton site HTML à discuter avec ce serveur Python (c'est la sécurité CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Accepte les requêtes de n'importe quel site
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Une petite fonction de secours pour deviner le nom de la boutique si on ne le trouve pas
def guess_shop_from_url(url_string: str) -> str:
    try:
        parsed_uri = urlparse(url_string)
        host = parsed_uri.netloc.replace('www.', '')
        parts = host.split('.')
        name = parts[-2] if len(parts) > 2 else parts[0]
        return name.capitalize()
    except Exception:
        return ""

# Voici la route principale. Quand ton site HTML appellera /api/scrape?url=..., ce code s'exécutera
@app.get("/api/scrape")
def scrape_url(url: str = Query(..., description="Lien de l'article à scrapper")):
    # Si on oublie de donner une URL, on renvoie une erreur
    if not url:
        raise HTTPException(status_code=400, detail="URL manquante")
    
    print(f"On cherche les infos pour : {url}")
    
    try:
        # 1. On demande à Scrapling d'aller chercher la page web
        fetcher = Fetcher()
        response = fetcher.get(url)
        
        # 2. On cherche les informations dans le code de la page (titre, image, nom du site)
        title = response.css('meta[property="og:title"]::attr(content)').get()
        if not title:
            title = response.css('title::text').get()
            
        image = response.css('meta[property="og:image"]::attr(content)').get()
        shop = response.css('meta[property="og:site_name"]::attr(content)').get()
        
        # 3. On nettoie un peu le texte trouvé
        title = title.strip() if title else ""
        shop = shop.strip() if shop else guess_shop_from_url(url)
        image = image.strip() if image else None
        
        # 4. On prépare le paquet final qui sera renvoyé à ton site HTML
        result = {
            "title": title,
            "shop": shop,
            "image": image,
            "price": None,
            "availability": "Inconnue"
        }
        
        return result

    except Exception as e:
        print(f"Erreur lors du scraping : {str(e)}")
        # S'il y a un problème (site bloqué, lien cassé), on renvoie un résultat vide pour ne pas faire planter ton site
        return {
            "title": "", 
            "shop": guess_shop_from_url(url), 
            "image": None, 
            "price": None, 
            "availability": "Inconnue"
        }