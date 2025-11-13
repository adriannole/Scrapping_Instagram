import os
import time
import random
import math
import re
import json
from io import BytesIO
import base64
from typing import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests

# Configuración básica (usar variables de entorno para credenciales en producción)
INSTA_USERNAME = os.getenv("INSTA_USER", "0978925415")
INSTA_PASSWORD = os.getenv("INSTA_PASS", "Arbolito157@")
TARGET_ACCOUNT = os.getenv("INSTA_TARGET", "palomita.buena_onda")

# ---------------------------------
# Utilidades
# ---------------------------------

USER_AGENTS = [
    # Pool simple de user-agents reales (rotación ligera)
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
]

class Pacer:
    """Pacer adaptativo para tiempos humanos con factor de escala dinámico."""
    def __init__(self) -> None:
        self.scale = 1.0
        self.ma_page = None  # media móvil de tiempos de carga

    def sleep(self, a=1.2, b=3.5, label: str | None = None):
        # variación aleatoria + factor de escala
        base = random.uniform(a, b)
        dur = base * self.scale
        if label:
            print(f"⏳ {label}: {dur:.2f}s (scale={self.scale:.2f})")
        time.sleep(dur)

    def on_page_load(self, seconds: float):
        # actualizar media móvil simple
        if self.ma_page is None:
            self.ma_page = seconds
        else:
            self.ma_page = 0.7 * self.ma_page + 0.3 * seconds
        # ajustar escala: si páginas lentas, aumentar descansos
        if self.ma_page > 6.0:
            self.scale = min(2.5, self.scale * 1.15)
        elif self.ma_page < 3.0:
            self.scale = max(0.85, self.scale * 0.95)
        else:
            # mantener
            self.scale = min(2.0, max(0.9, self.scale))


PACER = Pacer()

def human_sleep(a=1.2, b=3.5, label: str | None = None):
    PACER.sleep(a, b, label)

def timed_get(driver, url: str, label: str = "navegar"):
    t0 = time.time()
    driver.get(url)
    dt = time.time() - t0
    PACER.on_page_load(dt)
    print(f"🧭 {label}: {dt:.2f}s")


def benford_expected():
    return {d: math.log10(1 + 1/d) for d in range(1, 10)}


def first_digit(n: int | None):
    if not n or n <= 0:
        return None
    return int(str(n)[0])


def normalize_count(txt: str | None):
    if not txt:
        return None
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

def parse_followers_from_html(html: str) -> int | None:
    """Extrae el número de seguidores desde el HTML usando múltiples estrategias/idiomas."""
    patterns = [
        r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)\s*\}',  # GraphQL JSON
        r'"followers_count"\s*:\s*(\d+)',
        r'"follower_count"\s*:\s*(\d+)',
        r'(?:content=|\>)\s*"?([0-9.,]+[kKmM]?)\s+(?:seguidores|followers)"?',  # meta og:description u otros
        r'([0-9.,]+[kKmM]?)\s+(?:seguidores|followers)'
    ]
    for p in patterns:
        m = re.search(p, html, flags=re.IGNORECASE)
        if m:
            return normalize_count(m.group(1))
    return None

# ---------------------------------
# Debug helpers
# ---------------------------------

DEBUG_DUMPS = 0

def save_debug_html(username: str, html: str):
    global DEBUG_DUMPS
    if DEBUG_DUMPS >= 10:
        return
    try:
        os.makedirs('debug_html', exist_ok=True)
        safe = re.sub(r'[^a-zA-Z0-9_.-]', '_', username)
        path = os.path.join('debug_html', f'{safe}.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        DEBUG_DUMPS += 1
        print(f"[DEBUG] HTML guardado: {path}")
    except Exception as e:
        print(f"[WARN] No se pudo guardar debug HTML: {e}")

# ---------------------------------
# Selenium inicialización
# ---------------------------------

def build_driver(headless: bool = True):
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument('--headless=new')  # modo headless moderno
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument('--lang=es-ES')
    # Ventana con tamaño aleatorio para variar huella
    if not headless:
        w = random.choice([1280, 1366, 1440, 1536, 1600])
        h = random.choice([720, 768, 900, 1050])
        opts.add_argument(f'--window-size={w},{h}')
    else:
        opts.add_argument('--start-maximized')
    ua = random.choice(USER_AGENTS)
    opts.add_argument(f'user-agent={ua}')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(options=opts)
    return driver

# ---------------------------------
# Login y scraping
# ---------------------------------

def login(driver):
    # Intentar cargar cookies para evitar login
    cookies_path = 'cookies.json'
    if os.path.exists(cookies_path):
        timed_get(driver, 'https://www.instagram.com/', label='cargar home con cookies')
        try:
            with open(cookies_path, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            for c in cookies:
                # Ajustar campos requeridos por Selenium
                c = {k: v for k, v in c.items() if k in ['name', 'value', 'domain', 'path', 'expiry', 'secure', 'httpOnly', 'sameSite']}
                driver.add_cookie(c)
            driver.refresh()
            PACER.sleep(4, 7, label='post cookies refresh')
            if 'login' not in driver.current_url:
                print('🔐 Login por cookies OK')
                return
        except Exception as e:
            print(f'Cookies no aplicadas: {e}')

    timed_get(driver, 'https://www.instagram.com/accounts/login/', label='cargar login')
    human_sleep(4, 6, label='espera login')
    user_el = driver.find_element(By.NAME, 'username')
    pass_el = driver.find_element(By.NAME, 'password')
    user_el.send_keys(INSTA_USERNAME)
    pass_el.send_keys(INSTA_PASSWORD)
    pass_el.send_keys(Keys.ENTER)
    human_sleep(7, 11, label='post login')
    if 'login' in driver.current_url:
        raise RuntimeError('Login falló, revisar credenciales o challenge de seguridad.')
    # Guardar cookies para próximas sesiones
    try:
        with open('cookies.json', 'w', encoding='utf-8') as f:
            json.dump(driver.get_cookies(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'No se pudo guardar cookies: {e}')


def open_followers_modal(driver):
    timed_get(driver, f'https://www.instagram.com/{TARGET_ACCOUNT}/', label='cargar perfil objetivo')
    human_sleep(3, 6, label='post perfil objetivo')
    link = driver.find_element(By.XPATH, '//a[contains(@href, "/followers/")]')
    link.click()
    human_sleep(4, 7, label='abrir modal seguidores')


def collect_usernames_progressive(driver, limit=30, existing_cache=None, max_workers=20, counts_logged_out=True, scroll_limit=500):
    """Captura usuarios MIENTRAS TÚ haces scroll manual. Se detiene automáticamente tras 10 segundos sin cambios."""
    wait = WebDriverWait(driver, 20)
    def get_scroll_box():
        for _ in range(3):
            try:
                sb = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div._aano')))
                return sb
            except:
                try:
                    sb = wait.until(EC.presence_of_element_located((By.XPATH, '//div[@role="dialog"]//div[contains(@style, "overflow")]')))
                    return sb
                except:
                    time.sleep(2)
        return None

    scroll_box = get_scroll_box()
    if not scroll_box:
        raise RuntimeError('No se encontró scroll box de seguidores.')

    # Enfocar scroll box y cerrar overlays si aparecen
    try:
        driver.execute_script("arguments[0].setAttribute('tabindex','0'); arguments[0].focus();", scroll_box)
        ActionChains(driver).move_to_element(scroll_box).perform()
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", scroll_box)
    except Exception as e:
        print(f"[WARN] No se pudo enfocar scroll box: {e}")

    # Intentar cerrar overlays de login si aparecen
    try:
        dismiss_login_interstitial(driver)
    except Exception as e:
        print(f"[WARN] No se pudo cerrar overlay: {e}")

    if existing_cache is None:
        existing_cache = {}

    usernames_seen = set()
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {}

    last_user_count = 0
    last_change_time = time.time()
    timeout_seconds = 10  # Se detiene tras 10 segundos sin nuevos usuarios

    print(f"🎯 MODO MANUAL: Haz scroll en la ventana de Instagram.")
    print(f"   Se detendrá automáticamente tras {timeout_seconds}s sin cambios.")
    print(f"   Objetivo: {limit} usuarios\n")

    # Bucle de monitoreo continuo
    while True:
        time.sleep(1)  # Revisar cada segundo
        
        # Recolectar usuarios visibles actualmente
        try:
            scroll_box = get_scroll_box()
            if not scroll_box:
                print('[ERROR] No se pudo recuperar scroll_box')
                break
            
            links = scroll_box.find_elements(By.TAG_NAME, 'a')
        except Exception as e:
            print(f"[WARN] Error obteniendo links: {e}")
            continue
        
        new_users = []
        for link in links:
            try:
                href = link.get_attribute('href')
                if not href or 'instagram.com' not in href:
                    continue
                # Filtrar links que no son perfiles
                if any(x in href for x in ['/p/', '/reel/', '/explore/', '/stories/', '/direct/']):
                    continue
                # Extraer username
                parts = href.rstrip('/').split('/')
                if len(parts) > 0:
                    u = parts[-1]
                    if u and len(u) > 0 and u not in ['accounts', 'explore', 'reels', 'direct', 'stories'] and u not in usernames_seen:
                        usernames_seen.add(u)
                        new_users.append(u)
            except Exception:
                continue

        # Lanzar workers para nuevos usuarios (solo si no están en cache)
        for u in new_users:
            if u not in existing_cache and u not in futures:
                if counts_logged_out:
                    fut = executor.submit(profile_followers_logged_out, u)
                    futures[fut] = u

        # Verificar si hubo cambios
        current_user_count = len(usernames_seen)
        if current_user_count > last_user_count:
            # Hay nuevos usuarios, resetear contador de tiempo
            print(f"  📊 Usuarios capturados: {current_user_count} | Procesando: {len(futures)}")
            last_user_count = current_user_count
            last_change_time = time.time()  # Reiniciar el tiempo
            
            # Guardar progreso cada 20 usuarios
            if current_user_count % 20 == 0:
                try:
                    with open('cache_followers.json', 'w', encoding='utf-8') as f:
                        json.dump(existing_cache, f, ensure_ascii=False, indent=2)
                    print(f"💾 Progreso guardado: {len(existing_cache)} usuarios en caché")
                except Exception as e:
                    print(f"[WARN] No se pudo guardar progreso: {e}")
        else:
            # No hay cambios, calcular tiempo transcurrido REAL
            elapsed = int(time.time() - last_change_time)
            print(f"  ⏱️  Sin cambios: {elapsed}s / {timeout_seconds}s")

        # Verificar condiciones de salida
        if current_user_count >= limit:
            print(f"\n✅ Límite alcanzado: {limit} usuarios")
            break
        
        # Calcular tiempo real sin cambios
        time_without_change = time.time() - last_change_time
        if time_without_change >= timeout_seconds:
            print(f"\n⏹️  Detenido: {timeout_seconds}s sin nuevos usuarios")
            break

    # Esperar a que terminen todos los workers
    print(f"\n⏳ Esperando resultados de {len(futures)} workers en paralelo...")
    completed = 0
    for fut in as_completed(futures):
        u = futures[fut]
        try:
            followers = fut.result()
            existing_cache[u] = followers
            completed += 1
            if completed % 50 == 0:
                print(f"  ✅ Procesados: {completed}/{len(futures)}")
        except Exception as e:
            print(f"[WARN] Error en worker para {u}: {e}")
            existing_cache[u] = None

    executor.shutdown(wait=True)
    print(f"\n✅ Scraping completado: {len(usernames_seen)} usuarios descubiertos, {completed} procesados")
    return list(usernames_seen)[:limit]


def dismiss_login_interstitial(driver):
    """Intenta cerrar/ocultar el modal de inicio de sesión estando deslogueado."""
    # 1) Intentar botón de cierre
    candidates = [
        (By.XPATH, '//button[@aria-label="Close" or @aria-label="Cerrar"]'),
        (By.XPATH, '//div[@role="dialog"]//button[contains(.,"Ahora no") or contains(.,"Not now")]')
    ]
    for by, sel in candidates:
        try:
            btn = driver.find_element(by, sel)
            btn.click()
            PACER.sleep(0.8, 1.6, label='cerrar modal login')
            return
        except:
            continue
    # 2) ESCAPE
    try:
        from selenium.webdriver.common.keys import Keys
        driver.switch_to.active_element.send_keys(Keys.ESCAPE)
        PACER.sleep(0.5, 1.0)
    except:
        pass
    # 3) Forzar ocultar overlays por JS
    try:
        driver.execute_script('''
          const dialogs = document.querySelectorAll('div[role="dialog"], div[style*="position: fixed"], div[style*="position:fixed"]');
          dialogs.forEach(d => d.style.display = 'none');
        ''')
    except:
        pass


def profile_followers_logged_out(username: str) -> int | None:
    """Abrir un driver headless sin login, cerrar modal de login y obtener followers del perfil."""
    # Delay aleatorio antes de cada petición para evitar bloqueos
    time.sleep(random.uniform(2.0, 5.0))
    
    drv = build_driver(headless=True)
    try:
        timed_get(drv, f'https://www.instagram.com/{username}/', label=f'perfil (logged-out) {username}')
        PACER.sleep(1.5, 3.5, label='intersticial login check')
        dismiss_login_interstitial(drv)
        PACER.sleep(1.0, 2.0, label='post dismiss')
        # Detectar posibles mensajes de rate limit o bloqueo
        pg_pre = drv.page_source
        if re.search(r'please wait a few minutes|try again later', pg_pre, flags=re.IGNORECASE):
            print(f"[RATE-LIMIT] Instagram limitó las peticiones (logged-out) para {username}")
            return None
        # 1) Intentar recuperar desde el enlace de seguidores (innerText o title)
        try:
            a = drv.find_element(By.XPATH, '//a[contains(@href, "/followers")]')
            raw = drv.execute_script('return arguments[0].innerText', a) or ''
            raw = raw.strip()
            # Si viene algo como "1.234 seguidores" o "1,2k"
            m = re.search(r'([0-9.,]+[kKmM]?)', raw)
            if m:
                val = normalize_count(m.group(1))
                if val:
                    return val
            # A veces el número está en el atributo title
            title = a.get_attribute('title')
            if title:
                val = normalize_count(title.strip())
                if val:
                    return val
        except Exception:
            pass

        # 2) Intentar meta og:description
        try:
            meta = drv.find_element(By.XPATH, '//meta[@property="og:description"]')
            content = meta.get_attribute('content') or ''
            m = re.search(r'([0-9.,]+[kKmM]?)\s+(?:seguidores|followers)', content, flags=re.IGNORECASE)
            if m:
                val = normalize_count(m.group(1))
                if val is not None:
                    return val
        except Exception:
            pass

        # 3) Fallback: parsear HTML completo
        pg = drv.page_source
        val = parse_followers_from_html(pg)
        if val is not None:
            return val
        # Guardar HTML para diagnóstico
        save_debug_html(username, pg)
    except Exception as e:
        print(f"[WARN] Error obteniendo followers de {username}: {e}")
    finally:
        drv.quit()
    return None


def profile_followers_logged_in(driver, username: str) -> int | None:
    """Usa el driver logueado para abrir el perfil y extraer el número de seguidores."""
    try:
        timed_get(driver, f'https://www.instagram.com/{username}/', label=f'perfil (logged-in) {username}')
        PACER.sleep(1.2, 2.4, label='espera perfil')
        # Detectar estados de bloqueo
        pg_pre = driver.page_source
        if re.search(r'please wait a few minutes|try again later', pg_pre, flags=re.IGNORECASE):
            print(f"[RATE-LIMIT] Instagram limitó (logged-in) para {username}")
            return None
        # Intentos con el enlace de seguidores
        try:
            a = driver.find_element(By.XPATH, '//a[contains(@href, "/followers")]')
            raw = driver.execute_script('return arguments[0].innerText', a) or ''
            m = re.search(r'([0-9.,]+[kKmM]?)', raw)
            if m:
                v = normalize_count(m.group(1))
                if v:
                    return v
            title = a.get_attribute('title')
            if title:
                v = normalize_count(title.strip())
                if v:
                    return v
        except Exception:
            pass
        # Meta description
        try:
            meta = driver.find_element(By.XPATH, '//meta[@property="og:description"]')
            content = meta.get_attribute('content') or ''
            m = re.search(r'([0-9.,]+[kKmM]?)\s+(?:seguidores|followers)', content, flags=re.IGNORECASE)
            if m:
                v = normalize_count(m.group(1))
                if v is not None:
                    return v
        except Exception:
            pass
        # Fallback parse HTML
        v = parse_followers_from_html(driver.page_source)
        if v is not None:
            return v
        save_debug_html(username, driver.page_source)
    except Exception as e:
        print(f"[WARN] Error (logged-in) en {username}: {e}")
    return None


def fetch_followers_logged_in_sequential(driver, usernames: Iterable[str], existing_cache: dict, min_delay=2.0, max_delay=4.0):
    """Navega secuencialmente con sesión logueada y actualiza el cache de followers."""
    processed = 0
    for u in usernames:
        if u in existing_cache and isinstance(existing_cache[u], int):
            continue
        time.sleep(random.uniform(min_delay, max_delay))
        v = profile_followers_logged_in(driver, u)
        existing_cache[u] = v
        processed += 1
        if processed % 20 == 0:
            try:
                with open('cache_followers.json', 'w', encoding='utf-8') as f:
                    json.dump(existing_cache, f, ensure_ascii=False, indent=2)
                print(f"💾 Progreso (logueado) guardado: {len(existing_cache)} usuarios")
            except Exception as e:
                print(f"[WARN] No se pudo guardar progreso (logueado): {e}")


def get_session_from_driver(driver) -> requests.Session:
    """Extrae cookies del driver Selenium y crea una sesión de requests."""
    session = requests.Session()
    
    # Extraer cookies importantes
    csrftoken = None
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
        if cookie['name'] == 'csrftoken':
            csrftoken = cookie['value']
    
    # Headers completos para simular navegador real
    session.headers.update({
        'User-Agent': driver.execute_script('return navigator.userAgent'),
        'Accept': '*/*',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.instagram.com/',
        'X-Requested-With': 'XMLHttpRequest',
        'X-IG-App-ID': '936619743392459',  # App ID de Instagram Web
        'X-ASBD-ID': '129477',
        'X-IG-WWW-Claim': '0',
        'Origin': 'https://www.instagram.com',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    })
    
    if csrftoken:
        session.headers['X-CSRFToken'] = csrftoken
    
    return session


def fetch_user_info_api(session: requests.Session, username: str, retries=3) -> dict | None:
    """Consulta la API interna de Instagram para obtener info del usuario (incluye followers)."""
    for attempt in range(retries):
        try:
            url = f'https://www.instagram.com/api/v1/users/web_profile_info/?username={username}'
            time.sleep(random.uniform(0.5, 1.2))  # Delay más conservador
            resp = session.get(url, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                user = data.get('data', {}).get('user', {})
                if user:
                    followers = user.get('edge_followed_by', {}).get('count')
                    if followers is not None:
                        return {'username': username, 'followers': followers}
            elif resp.status_code == 429:
                wait_time = (2 ** attempt) * 3  # Backoff exponencial
                print(f"[RATE-LIMIT API] Esperando {wait_time}s antes de reintentar...")
                time.sleep(wait_time)
                continue
            elif resp.status_code == 404:
                print(f"[INFO] Usuario {username} no encontrado")
                return {'username': username, 'followers': None}
            else:
                print(f"[WARN] API retornó {resp.status_code} para {username}")
                if attempt < retries - 1:
                    time.sleep(random.uniform(2, 4))
                    continue
        except Exception as e:
            print(f"[WARN] Error en API para {username} (intento {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(random.uniform(1, 3))
                continue
    
    return None


def fetch_followers_api_batch(driver, usernames: Iterable[str], existing_cache: dict, max_workers=5):
    """Usa requests con cookies del driver para consultar followers vía API en paralelo."""
    session = get_session_from_driver(driver)
    to_process = [u for u in usernames if u not in existing_cache or not isinstance(existing_cache.get(u), int)]
    
    print(f"🚀 Consultando {len(to_process)} usuarios vía API de Instagram (paralelo)...")
    
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {executor.submit(fetch_user_info_api, session, u): u for u in to_process}
    
    processed = 0
    failed_users = []
    
    for fut in as_completed(futures):
        u = futures[fut]
        try:
            result = fut.result()
            if result and result.get('followers') is not None:
                existing_cache[u] = result['followers']
            else:
                # Marcar para fallback
                failed_users.append(u)
                existing_cache[u] = None
            processed += 1
            if processed % 20 == 0:
                print(f"  ⚡ API: {processed}/{len(to_process)} procesados")
                try:
                    with open('cache_followers.json', 'w', encoding='utf-8') as f:
                        json.dump(existing_cache, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[WARN] No se pudo guardar progreso API: {e}")
        except Exception as e:
            print(f"[WARN] Error procesando {u}: {e}")
            failed_users.append(u)
            existing_cache[u] = None
    
    executor.shutdown(wait=True)
    print(f"✅ API completada: {processed} usuarios procesados")
    
    # Fallback: intentar obtener los que fallaron usando navegación
    if failed_users:
        print(f"🔄 Fallback: Intentando obtener {len(failed_users)} usuarios que fallaron con API...")
        for u in failed_users[:20]:  # Limitar a 20 para no tardar mucho
            time.sleep(random.uniform(2, 4))
            val = profile_followers_logged_in(driver, u)
            if val is not None:
                existing_cache[u] = val
                print(f"  ✅ Fallback OK: {u} = {val} seguidores")
        
        # Guardar después del fallback
        try:
            with open('cache_followers.json', 'w', encoding='utf-8') as f:
                json.dump(existing_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] No se pudo guardar después de fallback: {e}")


def fetch_followers_logged_out_many(usernames: list[str], max_workers: int = 20) -> dict:
    """Procesamiento paralelo de followers en batches de 'max_workers' con pausas."""
    results = {}
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures_map = {}
    for u in usernames:
        fut = executor.submit(profile_followers_logged_out, u)
        futures_map[fut] = u
    completed = 0
    for fut in as_completed(futures_map):
        u = futures_map[fut]
        try:
            followers = fut.result()
            results[u] = followers
            completed += 1
            if completed % 50 == 0:
                print(f"Procesados: {completed}/{len(usernames)}")
                # Pausa entre cada 50 para no saturar
                time.sleep(random.uniform(10, 20))
        except Exception as e:
            print(f"Error obteniendo seguidores de {u}: {e}")
            results[u] = None
    executor.shutdown(wait=True)
    return results


def scrape_for_benford(limit_users=30, resume=True, counts_logged_out=True, max_workers=20):
    """Obtiene muestra de seguidores + sus conteos de followers para análisis Benford."""
    cache_path = 'cache_followers.json'
    cache = {}
    if resume and os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"Caché cargado: {len(cache)} usuarios previamente procesados")
        except:
            pass

    driver = build_driver(headless=False)
    try:
        login(driver)
        open_followers_modal(driver)
        print(f"🚀 Iniciando scraping progresivo: scroll + extracción paralela simultánea")
        usernames = collect_usernames_progressive(driver, limit=limit_users, existing_cache=cache,
                                                  max_workers=max_workers, counts_logged_out=counts_logged_out)
        # Si preferimos evitar bloqueos, calcular counts con el mismo driver logueado
        if not counts_logged_out:
            print("🔐 Usando sesión logueada para obtener seguidores vía API (rápido)")
            fetch_followers_api_batch(driver, usernames, cache, max_workers=5)
    finally:
        driver.quit()

    # Guardar cache actualizado
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"💾 Caché guardado: {len(cache)} usuarios")
    except Exception as e:
        print(f"No se pudo guardar caché: {e}")

    # Preparar resultados para análisis Benford
    results = []
    for u in usernames:
        followers = cache.get(u)
        results.append({'username': u, 'followers': followers})
    return results


def benford_analysis(results):
    """Analiza distribución del primer dígito según Benford."""
    expected_pct = benford_expected()
    counts = {d: 0 for d in range(1, 10)}
    total = 0
    for r in results:
        f = r.get('followers')
        d = first_digit(f)
        if d:
            counts[d] += 1
            total += 1
    if total == 0:
        observed_pct = {d: 0.0 for d in range(1, 10)}
    else:
        observed_pct = {d: counts[d] / total for d in range(1, 10)}
    return {'expected_pct': expected_pct, 'observed_pct': observed_pct, 'sample_size': total}


def benford_plot_png(analysis):
    """Genera gráfico PNG (base64) de Benford."""
    import matplotlib
    matplotlib.use('Agg')  # sin GUI, safe para threading
    import matplotlib.pyplot as plt
    digits = list(range(1, 10))
    exp_vals = [analysis['expected_pct'][d] * 100 for d in digits]
    obs_vals = [analysis['observed_pct'][d] * 100 for d in digits]
    x = range(len(digits))
    width = 0.35
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([p - width/2 for p in x], exp_vals, width, label='Benford Esperado', color='#5A9')
    ax.bar([p + width/2 for p in x], obs_vals, width, label='Observado', color='#E74')
    ax.set_xlabel('Primer dígito')
    ax.set_ylabel('Porcentaje (%)')
    ax.set_title('Distribución Benford: Seguidores de Seguidores')
    ax.set_xticks(x)
    ax.set_xticklabels(digits)
    ax.legend()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('ascii')
    buf.close()
    plt.close(fig)
    return img_b64
