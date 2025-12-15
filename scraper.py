import os
import json
import time
import requests
import shutil  # <--- AGREGA ESTO
from datetime import datetime
from urllib.parse import quote
from playwright.sync_api import sync_playwright


# Configuración de límites
MAX_TRENDS = 2
MAX_TWEETS = 2
MAX_REPLIES_PER_TWEET = 5


# Configuración de directorios
LOGIN_DIR = "login"
OUTPUT_DIR = "tuits"

# --- INICIO DEL CAMBIO ---
if os.path.exists(OUTPUT_DIR):
    try:
        shutil.rmtree(OUTPUT_DIR)  # Esto borra la carpeta y todo lo de adentro
        print(f"🧹 Carpeta '{OUTPUT_DIR}' eliminada. Iniciando limpieza...")
        time.sleep(1) # Una pequeña pausa para asegurar que el sistema libere la carpeta
    except OSError as e:
        print(f"⚠️ No se pudo borrar la carpeta antigua: {e}")
# --- FIN DEL CAMBIO ---

IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
os.makedirs(OUTPUT_DIR, exist_ok=True) # Aquí se crea de nuevo, totalmente vacía
os.makedirs(IMAGES_DIR, exist_ok=True)

def load_session(context):
    """Carga cookies y localStorage desde archivos guardados en la carpeta login."""
    cookies_path = os.path.join(LOGIN_DIR, "twitter_cookies.json")
    localstorage_path = os.path.join(LOGIN_DIR, "twitter_localstorage.json")
    
    if os.path.exists(cookies_path):
        with open(cookies_path, "r") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print(f"🍪 Cookies cargadas desde '{cookies_path}'")
    else:
        raise FileNotFoundError(f"Archivo {cookies_path} no encontrado. Ejecuta login.py primero.")

    page = context.new_page()
    page.goto("https://x.com", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    if os.path.exists(localstorage_path):
        with open(localstorage_path, "r") as f:
            localStorage = json.load(f)
        page.evaluate("""(data) => {
            for (const [key, value] of Object.entries(data)) {
                if (value && typeof value === 'string') {
                    localStorage.setItem(key, value);
                }
            }
        }""", localStorage)
        print(f"💾 localStorage cargado desde '{localstorage_path}'")
    else:
        print(f"⚠️  Archivo {localstorage_path} no encontrado. Continuando sin localStorage.")
    
    return page

def download_image(url, folder_path, image_name):
    """Descarga una imagen desde una URL y la guarda en la carpeta especificada."""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            # Obtener la extensión del archivo desde la URL o usar jpg por defecto
            ext = os.path.splitext(url.split('?')[0])[1]
            if not ext:
                ext = '.jpg'
            
            file_path = os.path.join(folder_path, f"{image_name}{ext}")
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            return file_path
    except Exception as e:
        print(f"❌ Error descargando imagen: {e}")
    return None

def extract_trends(page):
    """Extrae las tendencias reales desde la pestaña de trending."""
    print("🌐 Navegando a tendencias...")
    page.goto("https://x.com/explore/tabs/trending", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    trends = []
    trend_elements = page.query_selector_all('[data-testid="trend"]')
    print(f"📊 Encontradas {len(trend_elements)} tendencias.")

    for el in trend_elements:
        try:
            title_div = el.query_selector('div[dir="ltr"][style*="color: rgb(15, 20, 25)"]')
            if title_div:
                title = title_div.text_content().strip()
                if title and title not in trends:
                    trends.append(title)
                    print(f"  ➤ {title}")
        except Exception:
            continue
    return trends[:MAX_TRENDS]  # Limitar a MAX_TRENDS tendencias

def scrape_replies_from_tweet(page, tweet_element, max_replies=10):
    """Extrae las respuestas de un tweet específico."""
    replies = []
    
    try:
        # Hacer clic en el tweet para abrir el hilo de respuestas
        tweet_element.click()
        page.wait_for_timeout(3000)
        
        # Esperar a que cargue el detalle del tweet
        page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
        
        # Buscar el contenedor de respuestas
        reply_elements = page.query_selector_all('[data-testid="tweet"]')
        
        # El primer tweet es el original, los siguientes son respuestas
        for i, reply_element in enumerate(reply_elements[1:max_replies+1]):  # Limitar a max_replies respuestas
            try:
                # Extraer datos de la respuesta
                author_elem = reply_element.query_selector('div[data-testid="User-Name"] a[role="link"]:first-child')
                author = author_elem.text_content().strip() if author_elem else "Anónimo"

                handle_elem = reply_element.query_selector('div[data-testid="User-Name"] a[role="link"]:nth-child(2)')
                handle = handle_elem.text_content().strip() if handle_elem else ""

                text_elem = reply_element.query_selector('[data-testid="tweetText"]')
                text = text_elem.text_content().strip() if text_elem else ""

                # Métricas
                reply_elem = reply_element.query_selector('[data-testid="reply"]')
                retweet_elem = reply_element.query_selector('[data-testid="retweet"]')
                like_elem = reply_element.query_selector('[data-testid="like"]')
                
                replies_count = reply_elem.text_content().strip() if reply_elem else "0"
                retweets = retweet_elem.text_content().strip() if retweet_elem else "0"
                likes = like_elem.text_content().strip() if like_elem else "0"

                # Timestamp
                time_elem = reply_element.query_selector('time')
                timestamp = time_elem.get_attribute('datetime') if time_elem else ""

                # Extraer imágenes de la respuesta
                images = []
                image_elements = reply_element.query_selector_all('img[alt="Image"]')
                for j, img_elem in enumerate(image_elements):
                    img_src = img_elem.get_attribute('src')
                    if img_src and ('pbs.twimg.com/media/' in img_src or 'pbs.twimg.com/' in img_src):
                        high_quality_src = (img_src
                                          .replace('&name=small', '&name=large')
                                          .replace('&name=medium', '&name=large')
                                          .replace('_normal', ''))
                        images.append(high_quality_src)

                reply_data = {
                    "author": author,
                    "handle": handle,
                    "text": text,
                    "replies": replies_count,
                    "retweets": retweets,
                    "likes": likes,
                    "timestamp": timestamp,
                    "image_urls": images
                }

                replies.append(reply_data)
                print(f"      💬 Respuesta {i+1}: {author} - {text[:50]}...")

            except Exception as e:
                print(f"      ❌ Error procesando respuesta: {e}")
                continue
        
        # Cerrar el detalle del tweet
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        
    except Exception as e:
        print(f"    ❌ Error al abrir respuestas: {e}")
        # Intentar cerrar el modal si está abierto
        try:
            page.keyboard.press("Escape")
        except:
            pass
    
    return replies

def scrape_tweets_from_trend(context, trend_title, max_tweets=60, max_replies_per_tweet=10):
    """Abre una NUEVA pestaña por tendencia y extrae tweets de la pestaña TOP con sus respuestas."""
    query = quote(trend_title)
    
    # URL para búsqueda en la pestaña TOP (más relevante/popular)
    url = f"https://x.com/search?q={query}&src=trend_click"
    
    print(f"\n📥 Scrapeando tendencia (TOP): {trend_title}")
    page = context.new_page()
    try:
        page.goto(url, timeout=60000)
        page.wait_for_timeout(5000)

        # Asegurarse de que estamos en la pestaña TOP
        try:
            top_button = page.query_selector('//span[contains(text(), "Top")] | //a[contains(text(), "Top")] | //div[contains(text(), "Top")]')
            if top_button:
                top_button.click()
                print("  ✅ Cambiando a pestaña TOP")
                page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  ℹ️  No se pudo cambiar a TOP, continuando con búsqueda por defecto: {e}")

        tweets = []
        last_height = page.evaluate("document.body.scrollHeight")
        attempts = 0
        max_attempts = 5

        while len(tweets) < max_tweets and attempts < max_attempts:
            # Seleccionar solo tweets visibles y no procesados
            tweet_elements = page.query_selector_all('article[data-testid="tweet"]')
            new_tweets = 0

            for tweet in tweet_elements:
                if len(tweets) >= max_tweets:
                    break
                
                tweet_id = tweet.get_attribute("aria-labelledby") or str(hash(tweet.inner_html()[:100]))
                if any(t.get("id") == tweet_id for t in tweets):
                    continue

                try:
                    # Extraer datos básicos del tweet
                    author_elem = tweet.query_selector('div[data-testid="User-Name"] a[role="link"]:first-child')
                    author = author_elem.text_content().strip() if author_elem else "Anónimo"

                    handle_elem = tweet.query_selector('div[data-testid="User-Name"] a[role="link"]:nth-child(2)')
                    handle = handle_elem.text_content().strip() if handle_elem else ""

                    text_elem = tweet.query_selector('[data-testid="tweetText"]')
                    text = text_elem.text_content().strip() if text_elem else ""

                    # Métricas
                    reply_elem = tweet.query_selector('[data-testid="reply"]')
                    retweet_elem = tweet.query_selector('[data-testid="retweet"]')
                    like_elem = tweet.query_selector('[data-testid="like"]')
                    
                    replies = reply_elem.text_content().strip() if reply_elem else "0"
                    retweets = retweet_elem.text_content().strip() if retweet_elem else "0"
                    likes = like_elem.text_content().strip() if like_elem else "0"

                    # Timestamp
                    time_elem = tweet.query_selector('time')
                    timestamp = time_elem.get_attribute('datetime') if time_elem else ""

                    # Extraer imágenes
                    images = []
                    image_elements = tweet.query_selector_all('img[alt="Image"]')
                    for i, img_elem in enumerate(image_elements):
                        img_src = img_elem.get_attribute('src')
                        if img_src and ('pbs.twimg.com/media/' in img_src or 'pbs.twimg.com/' in img_src):
                            high_quality_src = (img_src
                                              .replace('&name=small', '&name=large')
                                              .replace('&name=medium', '&name=large')
                                              .replace('_normal', ''))
                            images.append(high_quality_src)

                    # SCRAPEO DE RESPUESTAS - PARA CADA TWEET OBTENER max_replies_per_tweet RESPUESTAS
                    tweet_replies = []
                    if max_replies_per_tweet > 0:  # Si queremos respuestas para este tweet
                        print(f"    🔍 Obteniendo hasta {max_replies_per_tweet} respuestas para el tweet {len(tweets) + 1}...")
                        tweet_replies = scrape_replies_from_tweet(page, tweet, max_replies=max_replies_per_tweet)

                    tweet_data = {
                        "id": tweet_id,
                        "author": author,
                        "handle": handle,
                        "text": text,
                        "replies": replies,
                        "retweets": retweets,
                        "likes": likes,
                        "timestamp": timestamp,
                        "image_urls": images,
                        "thread_replies": tweet_replies,
                        "reply_count": len(tweet_replies)
                    }

                    tweets.append(tweet_data)
                    new_tweets += 1

                    print(f"  ✅ Tweet {len(tweets)}: {author} - {text[:50]}... ({len(images)} imágenes, {len(tweet_replies)} respuestas)")

                except Exception as e:
                    print(f"  ❌ Error procesando tweet: {e}")
                    continue

            if new_tweets == 0:
                attempts += 1
                print(f"  🔄 No hay nuevos tweets, intento {attempts}/{max_attempts}")
            else:
                attempts = 0

            # Scroll suave
            page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            page.wait_for_timeout(3000)

            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                attempts += 1
                print(f"  🔄 No hay más contenido, intento {attempts}/{max_attempts}")
            last_height = new_height

        print(f"  📊 Total tweets obtenidos para '{trend_title}': {len(tweets)}")
        total_replies = sum(len(tweet.get("thread_replies", [])) for tweet in tweets)
        print(f"  💬 Total respuestas obtenidas: {total_replies}")
        return tweets
    except Exception as e:
        print(f"  ❌ Error en la pestaña: {e}")
        return []
    finally:
        page.close()

def sanitize_filename(name):
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip()[:100]

def save_trend_data(trend, tweets):
    """Guarda los datos de la tendencia directamente en OUTPUT_DIR y las imágenes en IMAGES_DIR."""
    trend_filename = sanitize_filename(trend)
    
    # Crear carpeta específica para las imágenes de esta tendencia
    trend_images_dir = os.path.join(IMAGES_DIR, trend_filename)
    os.makedirs(trend_images_dir, exist_ok=True)

    # Procesar tweets y descargar imágenes
    processed_tweets = []
    image_count = 0
    
    for i, tweet in enumerate(tweets):
        # Crear copia del tweet sin el ID interno
        processed_tweet = {k: v for k, v in tweet.items() if k != "id"}
        processed_tweet["downloaded_images"] = []
        
        # Descargar imágenes del tweet principal
        for j, img_url in enumerate(tweet.get("image_urls", [])):
            image_name = f"tweet_{i+1}_img_{j+1}"
            saved_path = download_image(img_url, trend_images_dir, image_name)
            
            if saved_path:
                # Guardar ruta relativa desde el directorio de imágenes
                rel_path = os.path.relpath(saved_path, IMAGES_DIR)
                processed_tweet["downloaded_images"].append(rel_path)
                image_count += 1
        
        # Procesar respuestas y descargar sus imágenes
        processed_replies = []
        for k, reply in enumerate(tweet.get("thread_replies", [])):
            processed_reply = reply.copy()
            processed_reply["downloaded_images"] = []
            
            # Descargar imágenes de la respuesta
            for l, img_url in enumerate(reply.get("image_urls", [])):
                image_name = f"tweet_{i+1}_reply_{k+1}_img_{l+1}"
                saved_path = download_image(img_url, trend_images_dir, image_name)
                
                if saved_path:
                    rel_path = os.path.relpath(saved_path, IMAGES_DIR)
                    processed_reply["downloaded_images"].append(rel_path)
                    image_count += 1
            
            processed_replies.append(processed_reply)
        
        processed_tweet["thread_replies"] = processed_replies
        processed_tweets.append(processed_tweet)

    # Guardar datos en JSON directamente en OUTPUT_DIR
    data = {
        "trend": trend,
        "scraped_at": datetime.now().isoformat(),
        "tweet_count": len(processed_tweets),
        "total_replies": sum(len(tweet.get("thread_replies", [])) for tweet in processed_tweets),
        "image_count": image_count,
        "tweets": processed_tweets
    }

    # Guardar directamente en OUTPUT_DIR sin subcarpeta
    json_path = os.path.join(OUTPUT_DIR, f"{trend_filename}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Datos guardados: {json_path}")
    print(f"💬 {data['total_replies']} respuestas obtenidas")
    print(f"🖼️  {image_count} imágenes descargadas en: {trend_images_dir}")
    
    return json_path, image_count

def main():
    print("🚀 Iniciando scraping completo de tendencias con tweets y respuestas (MODO SEGUNDO PLANO)")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,  # CAMBIADO: Ahora se ejecuta en modo headless (sin interfaz)
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images',  # Opcional: acelera la carga si no necesitas imágenes
                '--mute-audio',
                '--no-first-run',
                '--disable-default-apps',
                '--disable-features=TranslateUI',
                '--disable-background-timer-throttling',
                '--disable-renderer-backgrounding',
                '--disable-backgrounding-occluded-windows',
                '--lang=en-US',
                '--disable-features=WebRtcHideLocalIpsWithMdns'
            ]
        )

        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            # Configuraciones adicionales para modo headless
            java_script_enabled=True,
            ignore_https_errors=True
        )

        try:
            base_page = load_session(context)
            trends = extract_trends(base_page)

            if not trends:
                print("❌ No se encontraron tendencias.")
                # ✅ Salir limpiamente si no hay datos
                return 0  # Código de éxito para no detener el workflow

            print(f"\n🔍 Procesando {min(len(trends), MAX_TRENDS)} tendencias...")
            total_images = 0
            total_tweets = 0
            total_replies = 0

            # Procesar solo las primeras MAX_TRENDS tendencias
            for i, trend in enumerate(trends[:MAX_TRENDS], 1):
                try:
                    print(f"\n📋 Procesando tendencia {i}/{MAX_TRENDS}: {trend}")
                    tweets = scrape_tweets_from_trend(context, trend, max_tweets=MAX_TWEETS, max_replies_per_tweet=MAX_REPLIES_PER_TWEET)

                    if tweets:
                        json_path, image_count = save_trend_data(trend, tweets)
                        total_images += image_count
                        total_tweets += len(tweets)
                        total_replies += sum(len(tweet.get("thread_replies", [])) for tweet in tweets)
                    else:
                        print(f"❌ No se encontraron tweets para: {trend}")

                    # Pausa entre tendencias (solo si no es la última)
                    if i < MAX_TRENDS and i < len(trends[:MAX_TRENDS]):
                        print("⏳ Esperando 10 segundos antes de la siguiente tendencia...")
                        time.sleep(10)

                except Exception as e:
                    print(f"❌ Error crítico al procesar '{trend}': {str(e)}")
                    # ✅ Continuar con la siguiente tendencia en lugar de fallar todo
                    continue

            # ✅ Si no se encontraron TENDENCIAS VÁLIDAS, evitar subir datos vacíos
            if total_tweets == 0:
                print("⚠️ No se obtuvieron tweets válidos. Abortando commit.")
                return 0

            print(f"\n🎉 ¡Proceso completado!")
            print(f"📊 Tendencias procesadas: {min(len(trends), MAX_TRENDS)}")
            print(f"🐦 Total de tweets obtenidos: {total_tweets}")
            print(f"💬 Total de respuestas obtenidas: {total_replies}")
            print(f"🖼️  Total de imágenes descargadas: {total_images}")
            print(f"📁 Datos guardados en: {OUTPUT_DIR}/")
            print(f"🖼️  Imágenes guardadas en: {IMAGES_DIR}/")

        except Exception as e:
            print(f"❌ Error general en el proceso: {e}")
            # ✅ Manejar correctamente la excepción general
            return 1
        finally:
            browser.close()

if __name__ == "__main__":
    main()
