import flet as ft
import sqlite3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import asyncio

# --- Banco de Dados ---
def init_db():
    conn = sqlite3.connect("anime_manager.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS animes (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER, title TEXT, url TEXT, UNIQUE(site_id, url))")
    conn.commit()
    conn.close()

async def main(page: ft.Page):
    page.title = "Gekkō Manager"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1000
    page.window_height = 800
    
    init_db()

    # --- Componentes de UI ---
    url_input = ft.TextField(label="URL do Site", expand=True, hint_text="https://...")
    sites_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
    animes_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
    loading = ft.ProgressBar(visible=False)

    # --- Funções ---
    def add_site(_): # Usei _ para silenciar o aviso de 'e' não acessado
        if not url_input.value: return
        url = url_input.value.strip()
        conn = sqlite3.connect("anime_manager.db")
        try:
            conn.execute("INSERT INTO sites (url) VALUES (?)", (url,))
            conn.commit()
            url_input.value = ""
            load_sites()
        except sqlite3.Error:
            pass
        finally:
            conn.close()
        page.update()

    def load_sites():
        sites_list.controls.clear()
        conn = sqlite3.connect("anime_manager.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, url FROM sites")
        for row in cursor.fetchall():
            s_id, s_url = row
            sites_list.controls.append(
                ft.Container(
                    padding=5,
                    border=ft.border.all(1, "grey700"),
                    border_radius=8,
                    content=ft.Row([
                        ft.Text("🌐", size=20),
                        ft.Text(s_url, expand=True, size=12, no_wrap=True),
                        ft.TextButton("Atualizar", on_click=lambda _, i=s_id, u=s_url: page.run_task(sync, i, u)),
                        ft.TextButton("X", on_click=lambda _, i=s_id: delete_site(i), content=ft.Text("X", color="red")),
                    ]),
                    on_click=lambda _, i=s_id: load_animes(i)
                )
            )
        conn.close()
        page.update()

    async def sync(site_id, url):
        loading.visible = True
        page.update()
        try:
            res = await asyncio.to_thread(requests.get, url, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            conn = sqlite3.connect("anime_manager.db")
            
            for a in soup.find_all("a", href=True):
                # Correção para o erro de Pyright: Garante que href seja string
                raw_href = a.get('href')
                href = str(raw_href).lower() if raw_href else ""
                
                if any(x in href for x in ["ep", "video", "item"]):
                    title = a.text.strip() or "Conteúdo"
                    link = urljoin(url, str(raw_href))
                    conn.execute("INSERT OR IGNORE INTO animes (site_id, title, url) VALUES (?, ?, ?)", (site_id, title, link))
            
            conn.commit()
            conn.close()
            load_animes(site_id)
        except Exception:
            pass
        loading.visible = False
        page.update()

    def load_animes(site_id):
        animes_list.controls.clear()
        conn = sqlite3.connect("anime_manager.db")
        cursor = conn.cursor()
        cursor.execute("SELECT title, url FROM animes WHERE site_id = ?", (site_id,))
        for title, url in cursor.fetchall():
            animes_list.controls.append(
                ft.ListTile(
                    title=ft.Text(title, size=14, weight="bold"),
                    subtitle=ft.Text(url, size=10, no_wrap=True),
                    trailing=ft.ElevatedButton("Abrir", on_click=lambda _, u=url: page.launch_url(u))
                )
            )
        conn.close()
        page.update()

    def delete_site(site_id):
        conn = sqlite3.connect("anime_manager.db")
        conn.execute("DELETE FROM sites WHERE id = ?", (site_id,))
        conn.commit()
        conn.close()
        load_sites()

    # --- Montagem da Tela ---
    page.add(
        ft.Text("Gekkō Manager", size=25, weight="bold"),
        loading,
        ft.Row([url_input, ft.ElevatedButton("Add Site", on_click=add_site)]),
        ft.Divider(),
        ft.Row([
            ft.Column([ft.Text("Sites"), sites_list], expand=1),
            ft.VerticalDivider(),
            ft.Column([ft.Text("Conteúdo"), animes_list], expand=2),
        ], expand=True)
    )
    load_sites()

if __name__ == "__main__":
    ft.app(target=main)
