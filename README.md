Gekkō Manager 🌙
Um gerenciador de animes simples e eficiente construído com Flet e VLC. Ele permite centralizar seus sites de anime favoritos, sincronizar episódios e assisti-los diretamente em um player integrado (ou no navegador como fallback).
✨ Melhorias Realizadas
Correção de Sintaxe Flet: Atualizado para a versão mais recente do Flet (v0.85+), corrigindo o uso de ícones, cores e propriedades de janela.
Gerenciamento de Banco de Dados: Adicionada integridade referencial (FOREIGN KEY) e deleção em cascata para que, ao remover um site, seus episódios também sejam removidos.
Robustez na Extração: Melhorada a lógica de extração de streams, ignorando iframes irrelevantes (como anúncios do Google) e tratando melhor erros de rede.
UX Aprimorada:
Adicionado suporte a Enter no campo de URL para adicionar sites.
Feedback visual mais claro durante a sincronização e extração.
Ícones e cores padronizados.
Estabilidade: Correção de bugs em threads e fechamento de conexões SQLite.
🚀 Como Usar
1. Pré-requisitos
Você precisa ter o VLC Media Player instalado no seu sistema para o player integrado funcionar.
2. Instalação das Dependências
Bash
pip install flet requests beautifulsoup4 python-vlc yt-dlp selenium webdriver-manager
3. Execução
Bash
python main.py
🛠️ Tecnologias Utilizadas
Flet: Interface gráfica moderna e responsiva.
SQLite: Armazenamento local de sites e episódios.
BeautifulSoup4 & Selenium: Web scraping para encontrar episódios.
yt-dlp: Extração de links de vídeo de alta qualidade.
python-vlc: Integração com o player VLC.
Nota: Este projeto é para fins educacionais. Respeite os termos de serviço dos sites que você adicionar.