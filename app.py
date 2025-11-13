# Importa la librería 'time', que nos permite
# agregar pausas en nuestro script.
import time
import random
import re

# De la librería 'selenium', importamos 'webdriver'.
# Este es el módulo principal que nos deja controlar el navegador.
from selenium import webdriver

# De 'selenium', importamos 'By'. Se usa para especificar
# CÓMO vamos a buscar un elemento (por ej: por su ID,
# por su nombre, por XPATH, etc.).
from selenium.webdriver.common.by import By

# De 'selenium', importamos 'Keys'. Se usa para simular
# que presionamos teclas del teclado (como Enter, Tab, F5, etc.).
from selenium.webdriver.common.keys import Keys

# Esta línea está "comentada" con un '#'.
# Python la ignora por completo. Originalmente, se usaba
# para decirle a Selenium manualmente dónde estaba el "chromedriver.exe".
# from selenium.webdriver.chrome.service import Service

# Importa la librería 'pandas' y le da el apodo 'pd'.
# La usaremos después para organizar nuestros datos como en una
# hoja de cálculo.
import pandas as pd

# --- Fase 2: El Scraper ---
# Esto es solo un comentario para organizar el código.

# Este comentario explica lo que hace la línea de abajo.
# Iniciar Chrome sin especificar ejecutable ni Service (Selenium Manager lo gestiona)

# --- ¡Esta es la línea clave! ---
# 1. Llama a 'webdriver.Chrome()'.
# 2. Selenium Manager (que viene adentro) ve que no le diste
#    una ruta, así que automáticamente busca tu versión de Chrome,
#    descarga el 'chromedriver.exe' correcto y lo usa.
# 3. La variable 'driver' se convierte en nuestro "control remoto"
#    para la ventana del navegador que se acaba de abrir.


# Imprime un mensaje en tu terminal para avisar que el navegador se inició.
print("¡Navegador iniciado! 🤖 Abriendo Google...")

# ... (imports) ...

# Opciones para reducir detección como bot
chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--start-maximized")
chrome_options.add_argument("--lang=es-ES")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])  # Oculta bandera de automatización
chrome_options.add_experimental_option('useAutomationExtension', False)

driver = webdriver.Chrome(options=chrome_options)

def human_sleep(min_s: float = 1.2, max_s: float = 3.5, label: str = ""):
    """Pausa aleatoria para simular comportamiento humano."""
    dur = random.uniform(min_s, max_s)
    if label:
        print(f"⏳ Pausa {label}: {dur:.2f}s")
    time.sleep(dur)

def get_profile_counts(username: str) -> dict:
    """Visita el perfil y devuelve followers / following. Maneja privados y errores.

    Retorna: { 'username': str, 'followers': int|None, 'following': int|None, 'is_private': bool, 'ok': bool }
    """
    url = f"https://www.instagram.com/{username}/"
    data = {"username": username, "followers": None, "following": None, "is_private": False, "ok": False}
    try:
        driver.get(url)
        human_sleep(2.5, 5.0, label=f"cargar perfil {username}")

        page_source = driver.page_source

        # Detectar cuenta privada (palabras típicas)
        if re.search(r"Esta cuenta es privada|Private", page_source, re.IGNORECASE):
            data["is_private"] = True

        # Intentar obtener seguidores y seguidos vía XPATH estable
        # Patrón típico: enlaces a /followers/ y /following/
        try:
            followers_el = driver.find_element(By.XPATH, '//a[contains(@href,"/followers")]/span/span')
            raw_followers = followers_el.text.strip()
        except:
            raw_followers = None
        try:
            following_el = driver.find_element(By.XPATH, '//a[contains(@href,"/following")]/span/span')
            raw_following = following_el.text.strip()
        except:
            raw_following = None

        def normalize_count(txt: str | None) -> int | None:
            if not txt:
                return None
            # Quitar puntos, comas y convertir abreviaturas (k, m)
            t = txt.lower().replace('.', '').replace(',', '')
            mult = 1
            if t.endswith('k'):
                mult = 1000
                t = t[:-1]
            elif t.endswith('m'):
                mult = 1000000
                t = t[:-1]
            try:
                return int(float(t) * mult)
            except:
                return None

        data["followers"] = normalize_count(raw_followers)
        data["following"] = normalize_count(raw_following)
        data["ok"] = True if (data["followers"] is not None or data["following"] is not None) else False
    except Exception as e:
        print(f"❌ Error leyendo perfil {username}: {e}")
    return data

print("¡Navegador iniciado! 🤖 Abriendo Instagram...")

# Cambiamos la URL a la página de inicio de sesión de Instagram
driver.get("https://www.instagram.com/accounts/login/")
# Damos tiempo para que la página cargue
time.sleep(5) 

INSTA_USERNAME = "0978925415"
INSTA_PASSWORD = "Arbolito157@"
TARGET_ACCOUNT = "palomita.buena_onda" # Cambia esto por el nombre real


campo_usuario = driver.find_element(By.NAME, "username")

# 2. Encontrar el campo de contraseña
campo_password = driver.find_element(By.NAME, "password")
print("Campos de usuario y contraseña encontrados.")


# 2. Escribir en los campos usando send_keys()
campo_usuario.send_keys(INSTA_USERNAME)
campo_password.send_keys(INSTA_PASSWORD)

campo_password.send_keys(Keys.ENTER)
time.sleep(10)
url_actual = driver.current_url

if "login" not in url_actual:
    print("✅ LOGIN EXITOSO. Continuamos la navegación.")
    
    # Navegar a la cuenta objetivo
    driver.get(f"https://www.instagram.com/{TARGET_ACCOUNT}/")
    time.sleep(3)
    
    # Clic en el enlace de seguidores (Usando XPATH robusto)
    try:
        followers_link = driver.find_element(By.XPATH, '//a[contains(@href, "/followers/")]')
        followers_link.click() 
        time.sleep(5) # Esperar a que el modal cargue completamente

    except Exception as e:
        print(f"❌ Error al hacer clic en el enlace de seguidores. {e}")
        driver.quit()
        exit()

    # 3. SCROLL DINÁMICO (Versión mejorada con múltiples estrategias + pausas humanas)
    try:
        print("🔍 Buscando contenedor de seguidores...")
        
        # Intentar múltiples estrategias para encontrar el contenedor scrollable
        scroll_box = None
        
        # Estrategia 1: Buscar por clase CSS específica de Instagram
        try:
            scroll_box = driver.find_element(By.CSS_SELECTOR, 'div._aano')
            print("✅ Contenedor encontrado (Estrategia 1: CSS _aano)")
        except:
            pass
        
        # Estrategia 2: Buscar el div scrollable dentro del dialog
        if not scroll_box:
            try:
                scroll_box = driver.find_element(By.XPATH, '//div[@role="dialog"]//div[contains(@style, "overflow-y: scroll") or contains(@style, "overflow: auto")]')
                print("✅ Contenedor encontrado (Estrategia 2: overflow)")
            except:
                pass
        
        # Estrategia 3: Buscar por estructura más genérica
        if not scroll_box:
            try:
                # Esperar un poco más y buscar cualquier div scrollable en el dialog
                time.sleep(2)
                possible_containers = driver.find_elements(By.XPATH, '//div[@role="dialog"]//div')
                for container in possible_containers:
                    # Verificar si el elemento tiene scroll
                    scroll_height = driver.execute_script("return arguments[0].scrollHeight", container)
                    client_height = driver.execute_script("return arguments[0].clientHeight", container)
                    if scroll_height > client_height and scroll_height > 100:
                        scroll_box = container
                        print(f"✅ Contenedor encontrado (Estrategia 3: análisis dinámico - altura: {scroll_height}px)")
                        break
            except:
                pass
        
        if not scroll_box:
            raise Exception("No se pudo encontrar el contenedor de seguidores")
        
        # Verificar la altura inicial
        initial_height = driver.execute_script("return arguments[0].scrollHeight", scroll_box)
        print(f"📏 Altura inicial del contenedor: {initial_height}px")

        print("📜 Iniciando scroll dinámico...")
        last_height = initial_height
        scroll_count = 0
        no_change_count = 0  # Contador de intentos sin cambio
        max_scrolls = 50  # Límite de seguridad para evitar bucles infinitos
        
        while scroll_count < max_scrolls:
            scroll_count += 1
            # Pequeña pausa humana antes de cada scroll
            human_sleep(1.0, 2.2, label=f"scroll {scroll_count}")
            # Ejecutar JavaScript: Mueve el scroll del elemento hasta el final
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_box)
            # Esperar a que carguen nuevos elementos con tiempo aleatorio
            human_sleep(1.8, 3.4, label="carga nuevos elementos")
            
            # Obtener la nueva altura
            new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_box)
            
            print(f"  Scroll #{scroll_count} - Altura: {new_height}px (anterior: {last_height}px)")
            
            # Si no hay cambio en la altura
            if new_height == last_height:
                no_change_count += 1
                print(f"  ⚠️ Sin cambios detectados ({no_change_count}/3)")
                
                # Esperamos 3 intentos consecutivos sin cambio para confirmar que terminó
                if no_change_count >= 3:
                    print(f"✅ ¡Scroll completo! Lista cargada tras {scroll_count} scrolls.")
                    break
            else:
                # Si hubo cambio, reiniciar el contador
                no_change_count = 0
                last_height = new_height
        
        if scroll_count >= max_scrolls:
            print(f"⚠️ Se alcanzó el límite máximo de scrolls ({max_scrolls}). Continuando con los datos cargados...")

        # -----------------------------------------------
        # 4. EXTRACCIÓN DE NOMBRES DE USUARIO
        # -----------------------------------------------
        print("\n🔎 Extrayendo nombres de usuario...")
        
            # Buscar todos los enlaces dentro del scroll_box que contengan nombres de usuario
            # Instagram usa <a> tags con href="/username/" para cada seguidor
        follower_links = scroll_box.find_elements(By.XPATH, './/a[contains(@href, "/")]')
        
            # Lista para almacenar los nombres de usuario únicos
        usernames = []
        
        for link in follower_links:
            try:
                href = link.get_attribute('href')
                if href and '/p/' not in href and '/reel/' not in href and '/explore/' not in href:
                    username = href.rstrip('/').split('/')[-1]
                    if username and username not in ['accounts', 'explore', 'reels', 'direct', ''] and username not in usernames:
                        usernames.append(username)
            except:
                continue
        
            print(f"✅ Se extrajeron {len(usernames)} nombres de usuario únicos.")
        
            # Mostrar los primeros 10 como muestra
            print("\n📋 Primeros 10 seguidores:")
            for i, username in enumerate(usernames[:10], 1):
                print(f"  {i}. @{username}")
        
        if len(usernames) > 10:
            print(f"  ... y {len(usernames) - 10} más.")

        # -----------------------------------------------
        # 5. EXTRAER FOLLOWERS DE CADA PERFIL (LIMITADO)
        # -----------------------------------------------
        print("\n🧪 Obteniendo métricas básicas de los primeros perfiles...")
        LIMIT = 15  # Limitar para evitar ser bloqueado
        profile_stats = []
        for idx, user in enumerate(usernames[:LIMIT], 1):
            print(f"➡️ ({idx}/{LIMIT}) Perfil @{user}")
            data = get_profile_counts(user)
            profile_stats.append(data)
            # Pausa humana entre perfiles
            human_sleep(2.0, 5.0, label=f"post-perfil {user}")

        # Mostrar resumen
        print("\n📊 Resumen seguidores/seguidos (primeros):")
        for ps in profile_stats:
            print(f"  @{ps['username']}: followers={ps['followers']} following={ps['following']} privado={ps['is_private']}")

        # Nota: CSV desactivado por solicitud del usuario
        print("\n💡 CSV desactivado (se podría activar fácilmente si se requiere).")
        
            # (Se eliminó bloque de guardado CSV)

    except Exception as e:
        print(f"❌ ERROR: Falló el scroll dinámico. {e}")
        print("💡 Sugerencia: Verifica manualmente el XPATH del contenedor en las DevTools del navegador.")
        driver.quit()
        exit()
    
else:
    print("❌ ERROR DE LOGIN. No se pudo iniciar sesión.")
    driver.quit()
