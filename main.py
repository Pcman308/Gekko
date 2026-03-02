import flet as ft
import sqlite3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import threading

def init_db():
    conn = sqlite3.connect("anime_manager.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS animes (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER, title TEXT, url TEXT, UNIQUE(site_id, url))")
    conn.commit()
    conn.close()

def main(page: ft.Page):
    page.title = "Gekkō Manager"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1000
    page.window_height = 800
    
    init_db()

    url_input = ft.TextField(label="URL do Site", expand=True)
    sites_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
    animes_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
    loading = ft.ProgressBar(visible=False)

    # Nova forma de abrir URLs para evitar o RuntimeWarning
    def open_link(url):
        page.launch_url(url)

    def add_site(_):
        if not url_input.value: return
        url = url_input.value.strip()
        conn = sqlite3.connect("anime_manager.db")
        try:
            conn.execute("INSERT INTO sites (url) VALUES (?)", (url,))
            conn.commit()
            url_input.value = ""
            load_sites()
        except: pass
        finally: conn.close()
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
                    padding=10,
                    border=ft.Border.all(1, "grey700"), # Corrigido para ft.Border.all
                    border_radius=8,
                    content=ft.Row([
                        ft.Text("🌐", size=20),
                        ft.Text(s_url, expand=True, size=12, no_wrap=True),
                        ft.TextButton("Atualizar", on_click=lambda _, i=s_id, u=s_url: start_sync(i, u)),
                        ft.TextButton(content=ft.Text("Excluir", color="red400"), on_click=lambda _, i=s_id: delete_site(i)),
                    ]),
                    on_click=lambda _, i=s_id: load_animes(i)
                )
            )
        conn.close()
        page.update()

    def start_sync(site_id, url):
        loading.visible = True
        page.update()
        threading.Thread(target=sync_worker, args=(site_id, url), daemon=True).start()

    def sync_worker(site_id, url):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            
            conn = sqlite3.connect("anime_manager.db")
            # Filtro mais abrangente para capturar episódios
            for a in soup.find_all("a", href=True):
                raw_href = a.get('href')
                title = a.text.strip()
                href_str = str(raw_href).lower()
                
                # Procura por padrões comuns de episódios
                if any(x in href_str or x in title.lower() for x in ["ep", "episodio", "capitulo", "video", "item"]):
                    if len(title) > 2: # Evita pegar lixo
                        link = urljoin(url, str(raw_href))
                        conn.execute("INSERT OR IGNORE INTO animes (site_id, title, url) VALUES (?, ?, ?)", (site_id, title, link))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Erro no Scrape: {e}")
        
        loading.visible = False
        load_animes(site_id)
        page.update()

    def load_animes(site_id):
        animes_list.controls.clear()
        conn = sqlite3.connect("anime_manager.db")
        cursor = conn.cursor()
        cursor.execute("SELECT title, url FROM animes WHERE site_id = ? ORDER BY id DESC", (site_id,))
        rows = cursor.fetchall()
        for title, url in rows:
            animes_list.controls.append(
                ft.ListTile(
                    title=ft.Text(title, size=14, weight="bold"),
                    subtitle=ft.Text(url, size=11, color="grey500", no_wrap=True),
                    trailing=ft.Button("Abrir", on_click=lambda _, u=url: open_link(u)) # Usando Button (moderno)
                )
            )
        if not rows:
            animes_list.controls.append(ft.Text("Clique em 'Atualizar' no site desejado.", color="grey"))
        conn.close()
        page.update()

    def delete_site(site_id):
        conn = sqlite3.connect("anime_manager.db")
        conn.execute("DELETE FROM sites WHERE id = ?", (site_id,))
        conn.execute("DELETE FROM animes WHERE site_id = ?", (site_id,))
        conn.commit()
        conn.close()
        load_sites()
        animes_list.controls.clear()
        page.update()

    page.add(
        ft.Text("Gekkō Manager", size=28, weight="bold"),
        loading,
        ft.Row([url_input, ft.Button("Adicionar Site", on_click=add_site)]), # Button substituindo ElevatedButton
        ft.Divider(height=20),
        ft.Row([
            ft.Column([ft.Text("Meus Sites", weight="bold"), sites_list], expand=1),
            ft.VerticalDivider(),
            ft.Column([ft.Text("Lista de Episódios", weight="bold"), animes_list], expand=2),
        ], expand=True)
    )
    load_sites()

if __name__ == "__main__":
    ft.run(main) # ft.run substituindo ft.app

