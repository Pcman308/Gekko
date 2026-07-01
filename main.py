"""
Gekkō Manager
─────────────
Gerenciador de animes com player integrado.
Dependências:
    pip install flet requests beautifulsoup4 python-vlc yt-dlp selenium webdriver-manager
"""

import flet as ft
import sqlite3
import requests
import threading
import time
import re
import os

from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ── dependências opcionais ───────────────────────────────────────────────────
try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

try:
    import vlc
    HAS_VLC = True
except ImportError:
    HAS_VLC = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        HAS_WDM = True
    except ImportError:
        HAS_WDM = False
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    HAS_WDM = False

DB_PATH = "anime_manager.db"

# ─────────────────────────────────────────────────────────────────────────────
# BANCO DE DADOS
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id  INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS animes (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER,
            title   TEXT,
            url     TEXT,
            UNIQUE(site_id, url),
            FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# SELENIUM
# ─────────────────────────────────────────────────────────────────────────────

def _make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])

    if HAS_WDM:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=opts)
    else:
        return webdriver.Chrome(options=opts)

def fetch_html_with_js(url: str, wait_sec: int = 5) -> str:
    driver = _make_driver()
    try:
        driver.get(url)
        time.sleep(wait_sec)
        return driver.page_source
    finally:
        driver.quit()

def fetch_iframes_src(url: str) -> list[str]:
    driver = _make_driver()
    try:
        driver.get(url)
        time.sleep(5)
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        return [f.get_attribute("src") for f in iframes if f.get_attribute("src")]
    finally:
        driver.quit()

# ─────────────────────────────────────────────────────────────────────────────
# EXTRATOR DE STREAM
# ─────────────────────────────────────────────────────────────────────────────

def extract_stream_url(page_url: str, on_status=None) -> str | None:
    def status(msg):
        if on_status:
            on_status(msg)
        print(f"[extract] {msg}")

    # 1. yt-dlp
    if HAS_YTDLP:
        status("yt-dlp: tentando extração direta…")
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best[ext=mp4]/best",
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(page_url, download=False)
                url = info.get("url") or (info.get("formats") or [{}])[-1].get("url")
                if url:
                    status("yt-dlp: stream encontrado ✔")
                    return url
        except Exception as e:
            status(f"yt-dlp falhou: {e}")

    # 2. Selenium + iframes
    if HAS_SELENIUM:
        status("Selenium: buscando iframes com player…")
        try:
            iframes = fetch_iframes_src(page_url)
            status(f"Selenium: {len(iframes)} iframes encontrados")
            for src in iframes:
                if not src or src.startswith("about:") or "google" in src:
                    continue
                status(f"Tentando iframe: {src[:60]}...")
                if HAS_YTDLP:
                    try:
                        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "format": "best[ext=mp4]/best"}) as ydl:
                            info = ydl.extract_info(src, download=False)
                            url  = info.get("url") or (info.get("formats") or [{}])[-1].get("url")
                            if url:
                                status("Stream via iframe ✔")
                                return url
                    except Exception:
                        pass
                try:
                    html = requests.get(src, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
                    for pattern in [r'https?://[^\s"\']+\.m3u8[^\s"\']*', r'https?://[^\s"\']+\.mp4[^\s"\']*']:
                        found = re.findall(pattern, html)
                        if found:
                            status(f"Regex no iframe: stream encontrado ✔")
                            return found[0]
                except Exception:
                    pass
        except Exception as e:
            status(f"Selenium falhou: {e}")

    # 3. Fallback: regex HTML bruto
    status("Fallback: regex no HTML da página…")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        html = requests.get(page_url, headers=headers, timeout=15).text
        for pattern in [r'https?://[^\s"\']+\.m3u8[^\s"\']*', r'https?://[^\s"\']+\.mp4[^\s"\']*']:
            found = re.findall(pattern, html)
            if found:
                status("Regex no HTML: stream encontrado ✔")
                return found[0]
    except Exception as e:
        status(f"Regex falhou: {e}")

    status("Nenhum stream encontrado.")
    return None

# ─────────────────────────────────────────────────────────────────────────────
# SCRAPER DE EPISÓDIOS
# ─────────────────────────────────────────────────────────────────────────────

EPISODE_KEYWORDS = ["ep", "episod", "capitulo", "watch", "assistir", "video", "item", "online", "temporada"]

def scrape_episodes(site_url: str, on_status=None) -> list[tuple[str, str]]:
    def status(msg):
        if on_status:
            on_status(msg)

    html = None
    if HAS_SELENIUM:
        status("Selenium: carregando site com JS…")
        try:
            html = fetch_html_with_js(site_url, wait_sec=6)
            status("Selenium: HTML carregado ✔")
        except Exception as e:
            status(f"Selenium falhou, usando requests: {e}")

    if not html:
        status("requests: carregando HTML estático…")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            html = requests.get(site_url, headers=headers, timeout=15).text
        except Exception as e:
            status(f"Erro ao carregar: {e}")
            return []

    soup    = BeautifulSoup(html, "html.parser")
    results = []
    seen    = set()

    for a in soup.find_all("a", href=True):
        raw_href = str(a.get("href", ""))
        title    = a.get_text(separator=" ", strip=True)
        href_low = raw_href.lower()
        title_low = title.lower()

        if not any(kw in href_low or kw in title_low for kw in EPISODE_KEYWORDS):
            continue
        if len(title) < 3:
            continue

        link = urljoin(site_url, raw_href)
        if link in seen:
            continue
        seen.add(link)
        results.append((title, link))

    status(f"{len(results)} episódios encontrados.")
    return results

# ─────────────────────────────────────────────────────────────────────────────
# PLAYER VLC
# ─────────────────────────────────────────────────────────────────────────────

class VLCPlayer:
    def __init__(self):
        self._inst   = vlc.Instance("--no-xlib --quiet") if HAS_VLC else None
        self._player = self._inst.media_player_new() if HAS_VLC else None

    def play(self, url: str):
        if not self._inst: return
        media = self._inst.media_new(url)
        self._player.set_media(media)
        self._player.play()

    def pause(self):
        if self._player: self._player.pause()

    def resume(self):
        if self._player: self._player.play()

    def stop(self):
        if self._player: self._player.stop()

    def set_volume(self, vol: int):
        if self._player: self._player.audio_set_volume(max(0, min(100, vol)))

    def is_playing(self) -> bool:
        return bool(self._player and self._player.is_playing() == 1)

    def get_position(self) -> float:
        return self._player.get_position() if self._player else 0.0

    def get_time(self) -> int:
        if not self._player: return 0
        time_ms = self._player.get_time()
        return max(0, time_ms) if time_ms != -1 else 0

    def get_length(self) -> int:
        if not self._player: return 0
        length_ms = self._player.get_length()
        return max(0, length_ms) if length_ms != -1 else 0

    def set_position(self, pos: float):
        if self._player: self._player.set_position(max(0.0, min(1.0, pos)))

# ─────────────────────────────────────────────────────────────────────────────
# APP PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def main(page: ft.Page):
    # Configuração correta para Flet moderno
    page.title = "Gekkō Manager"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1120
    page.window_height = 840
    page.bgcolor = ft.Colors.GREY_900

    init_db()

    player = VLCPlayer() if HAS_VLC else None
    current_site_id = {"v": None}

    # ── widgets ──────────────────────────────────────────────────────────────
    url_input   = ft.TextField(label="URL do Site", expand=True, border_color=ft.Colors.GREY_700, on_submit=lambda _: add_site(None))
    sites_list  = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4)
    animes_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=2)
    loading     = ft.ProgressBar(visible=False, width=float("inf"), color=ft.Colors.ORANGE_400)
    status_text = ft.Text("", size=12, color=ft.Colors.GREY_400, italic=True)

    player_title   = ft.Text("Nenhum episódio selecionado", size=13, weight="bold",
                               color=ft.Colors.ORANGE_300, no_wrap=True, expand=True)
                               
    btn_play_pause = ft.IconButton(ft.Icons.PLAY_ARROW, disabled=True, icon_color=ft.Colors.WHITE,
                                    on_click=lambda _: toggle_play())
    btn_stop       = ft.IconButton(ft.Icons.STOP, disabled=True, icon_color=ft.Colors.WHITE,
                                    on_click=lambda _: do_stop())
    volume_slider  = ft.Slider(min=0, max=100, value=80, width=130, active_color=ft.Colors.ORANGE_400,
                                on_change=lambda e: update_volume(e))
    seek_bar  = ft.ProgressBar(value=0, expand=True, color=ft.Colors.ORANGE_500, bgcolor=ft.Colors.GREY_800, height=6)
    time_text = ft.Text("0:00 / 0:00", size=11, color=ft.Colors.GREY_400)

    # ── utilidades ───────────────────────────────────────────────────────────

    def fmt_ms(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def safe_update():
        try: page.update()
        except Exception: pass

    def open_browser(url: str):
        if not url.startswith(("http://", "https://")): url = "https://" + url
        page.launch_url(url)

    # ── controles do player ──────────────────────────────────────────────────

    def update_volume(e):
        if player: player.set_volume(int(e.control.value))

    def toggle_play():
        if not player: return
        if player.is_playing():
            player.pause()
            btn_play_pause.icon = ft.Icons.PLAY_ARROW
        else:
            player.resume()
            btn_play_pause.icon = ft.Icons.PAUSE
        safe_update()

    def do_stop():
        if not player: return
        player.stop()
        btn_play_pause.icon = ft.Icons.PLAY_ARROW
        seek_bar.value  = 0
        time_text.value = "0:00 / 0:00"
        safe_update()

    def _seek_loop():
        while True:
            time.sleep(0.5)
            if player and player.is_playing():
                seek_bar.value  = max(0.0, min(1.0, player.get_position()))
                time_text.value = f"{fmt_ms(player.get_time())} / {fmt_ms(player.get_length())}"
                safe_update()

    threading.Thread(target=_seek_loop, daemon=True).start()

    def open_episode(url: str, title: str):
        if not player:
            open_browser(url)
            return

        player_title.value      = f"⏳ Extraindo: {title}"
        btn_play_pause.disabled = True
        btn_stop.disabled       = True
        btn_play_pause.icon     = ft.Icons.PLAY_ARROW
        status_text.value       = "Iniciando extração de stream…"
        safe_update()

        def worker():
            def on_status(msg):
                status_text.value = msg
                safe_update()

            stream = extract_stream_url(url, on_status=on_status)

            if stream:
                try:
                    player.play(stream)
                    player.set_volume(int(volume_slider.value))
                    btn_play_pause.icon     = ft.Icons.PAUSE
                    btn_play_pause.disabled = False
                    btn_stop.disabled       = False
                    player_title.value      = title
                    status_text.value       = "▶ Reproduzindo via VLC"
                except Exception as e:
                    player_title.value = f"❌ Erro ao reproduzir"
                    status_text.value  = f"Erro: {str(e)}"
            else:
                player_title.value = f"❌ Stream não encontrado"
                status_text.value  = "Abrindo no navegador como fallback…"
                open_browser(url)
            safe_update()

        threading.Thread(target=worker, daemon=True).start()

    # ── gerenciamento de sites ────────────────────────────────────────────────

    def add_site(_):
        if not url_input.value or not url_input.value.strip(): return
        url = url_input.value.strip()
        if not url.startswith(("http://", "https://")): url = "https://" + url
        
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute("INSERT INTO sites (url) VALUES (?)", (url,))
            conn.commit()
            url_input.value = ""
            load_sites()
            status_text.value = "✔ Site adicionado com sucesso."
        except sqlite3.IntegrityError:
            status_text.value = "⚠ Este site já foi adicionado."
        except Exception as e:
            status_text.value = f"❌ Erro: {str(e)}"
        finally:
            conn.close()
        page.update()

    def load_sites():
        sites_list.controls.clear()
        conn = sqlite3.connect(DB_PATH)
        sites = conn.execute("SELECT id, url FROM sites").fetchall()
        
        if not sites:
            sites_list.controls.append(ft.Text("Nenhum site adicionado ainda.", color=ft.Colors.GREY_600, size=12, italic=True))
        
        for s_id, s_url in sites:
            active = current_site_id["v"] == s_id
            sites_list.controls.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=10, vertical=8),
                    border=ft.Border.all(2 if active else 1, ft.Colors.ORANGE_400 if active else ft.Colors.GREY_800),
                    border_radius=8,
                    ink=True,
                    bgcolor=ft.Colors.GREY_850 if active else ft.Colors.GREY_900,
                    content=ft.Row([
                        ft.Text("🌐", size=18),
                        ft.Text(s_url, expand=True, size=11, no_wrap=True, color=ft.Colors.GREY_300),
                        ft.IconButton(ft.Icons.SYNC, icon_size=16, tooltip="Sincronizar", icon_color=ft.Colors.ORANGE_300,
                                      on_click=lambda _, i=s_id, u=s_url: start_sync(i, u)),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, tooltip="Excluir", icon_color=ft.Colors.RED_400,
                                      on_click=lambda _, i=s_id: delete_site(i)),
                    ]),
                    on_click=lambda _, i=s_id: select_site(i),
                )
            )
        conn.close()
        page.update()

    def select_site(site_id):
        current_site_id["v"] = site_id
        load_sites()
        load_animes(site_id)

    def start_sync(site_id, url):
        loading.visible   = True
        status_text.value = "Sincronizando…"
        page.update()
        threading.Thread(target=_sync_worker, args=(site_id, url), daemon=True).start()

    def _sync_worker(site_id, url):
        def on_status(msg):
            status_text.value = msg
            safe_update()
        try:
            episodes = scrape_episodes(url, on_status=on_status)
            conn  = sqlite3.connect(DB_PATH)
            count = 0
            for title, link in episodes:
                cur = conn.execute("INSERT OR IGNORE INTO animes (site_id, title, url) VALUES (?, ?, ?)", (site_id, title, link))
                count += cur.rowcount
            conn.commit()
            conn.close()
            loading.visible   = False
            status_text.value = f"✔ {count} novos episódios adicionados."
        except Exception as e:
            loading.visible   = False
            status_text.value = f"❌ Erro na sincronização: {str(e)}"
        load_animes(site_id)
        safe_update()

    def load_animes(site_id):
        animes_list.controls.clear()
        if not site_id:
            animes_list.controls.append(ft.Text("Selecione um site para ver seus episódios.", color=ft.Colors.GREY_600, size=12, italic=True))
            safe_update()
            return
        
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT title, url FROM animes WHERE site_id = ? ORDER BY id DESC", (site_id,))
        rows = cursor.fetchall()
        conn.close()

        def make_handler(u, t): return lambda _: open_episode(u, t)

        for title, ep_url in rows:
            animes_list.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, color=ft.Colors.ORANGE_400, size=22),
                    title=ft.Text(title, size=13, weight=ft.FontWeight.W_600),
                    subtitle=ft.Text(ep_url, size=10, color=ft.Colors.GREY_600, no_wrap=True),
                    dense=True,
                    on_click=make_handler(ep_url, title),
                )
            )

        if not rows:
            animes_list.controls.append(ft.Text("Clique em 🔄 no site para buscar episódios.", color=ft.Colors.GREY_600, size=12, italic=True))
        safe_update()

    def delete_site(site_id):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM sites WHERE id = ?", (site_id,))
        conn.commit()
        conn.close()
        if current_site_id["v"] == site_id:
            current_site_id["v"] = None
            animes_list.controls.clear()
        load_sites()

    # ── avisos de dependências em falta ──────────────────────────────────────
    dep_warnings = []
    if not HAS_VLC: dep_warnings.append("⚠ VLC não encontrado → Instale o VLC Media Player no sistema.")
    if not HAS_YTDLP: dep_warnings.append("⚠ yt-dlp não encontrado → pip install yt-dlp")
    if not HAS_SELENIUM: dep_warnings.append("⚠ Selenium não encontrado → pip install selenium webdriver-manager")

    # ── barra do player ──────────────────────────────────────────────────────
    player_bar = ft.Container(
        bgcolor=ft.Colors.GREY_900,
        border=ft.Border(top=ft.BorderSide(1, ft.Colors.GREY_800)),
        padding=ft.padding.symmetric(horizontal=16, vertical=8),
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.LIVE_TV, color=ft.Colors.ORANGE_400, size=20),
                player_title,
                time_text,
            ]),
            ft.Row([seek_bar]),
            ft.Row([
                btn_play_pause, btn_stop,
                ft.Icon(ft.Icons.VOLUME_UP, size=18, color=ft.Colors.GREY_500),
                volume_slider,
                ft.Container(expand=True),
                status_text,
            ]),
        ], spacing=4),
    )

    def dep_badge(label, ok):
        return ft.Text(f"  {label} {'✔' if ok else '✗'}", size=11, color=ft.Colors.GREEN_400 if ok else ft.Colors.RED_400)

    # ── layout principal ─────────────────────────────────────────────────────
    page.add(
        ft.Container(
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            content=ft.Row([
                ft.Text("月", size=32, weight=ft.FontWeight.W_900, color=ft.Colors.ORANGE_400),
                ft.Text("Gekkō Manager", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(expand=True),
                dep_badge("VLC",      HAS_VLC),
                dep_badge("yt-dlp",   HAS_YTDLP),
                dep_badge("Selenium", HAS_SELENIUM),
            ]),
        ),
        *[ft.Container(padding=ft.padding.symmetric(horizontal=16, vertical=2),
            content=ft.Text(w, size=11, color=ft.Colors.YELLOW_700)) for w in dep_warnings],
        loading,
        ft.Container(
            padding=ft.padding.symmetric(horizontal=16, vertical=6),
            content=ft.Row([
                url_input,
                ft.ElevatedButton("Adicionar Site", icon=ft.Icons.ADD, on_click=add_site, 
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE_700, color=ft.Colors.WHITE)), 
            ]),
        ),
        ft.Divider(height=1, color=ft.Colors.GREY_800),
        ft.Container(
            expand=True,
            content=ft.Row([
                ft.Column([
                    ft.Text("  Meus Sites", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_500),
                    ft.Container(expand=True, content=sites_list),
                ], expand=1),
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_800),
                ft.Column([
                    ft.Text("  Episódios", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_500),
                    ft.Container(expand=True, content=animes_list),
                ], expand=2),
            ], expand=True),
        ),
        player_bar,
    )
    load_sites()

if __name__ == "__main__":
    ft.app(target=main)
