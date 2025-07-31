import csv
import os
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re
import time
import logging

 # --- CONFIGURACIÓN ---
CSV_FILE = 'historico_consensos.csv'
LOG_FILE = 'scrapeo_historico.log'
logging.basicConfig(
    filename=LOG_FILE,
    filemode='a',
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO
)
# Forzar creación del archivo de log y mensaje de inicio
with open(LOG_FILE, 'a', encoding='utf-8') as flog:
    flog.write('\n--- Nueva ejecución del script ---\n')
logging.info('Inicio de ejecución de scrapeo_historico.py')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Referer': 'https://contests.covers.com/',
    'Cookie': 'consent=1;'
}

"""
Diccionarios de abreviaturas a nombre estándar para MLB y WNBA
Puedes expandirlos según tus necesidades.
"""
ABREVIATURAS_EQUIPOS = {
    # MLB
    'col': 'colorado', 'bal': 'baltimore', 'mia': 'miami', 'mil': 'milwaukee', 'chc': 'chicago', 'chw': 'chicago',
    'tor': 'toronto', 'det': 'detroit', 'atl': 'atlanta', 'tex': 'texas', 'ath': 'oakland', 'hou': 'houston',
    'az': 'arizona', 'pit': 'pittsburgh', 'sea': 'seattle', 'laa': 'angels', 'sd': 'san diego', 'stl': 'st louis',
    'lad': 'dodgers', 'bos': 'boston', 'phi': 'philadelphia', 'nyy': 'yankees', 'nym': 'mets', 'sf': 'san francisco',
    'tb': 'tampa bay', 'cin': 'cincinnati', 'cle': 'cleveland', 'kc': 'kansas city', 'was': 'washington', 'min': 'minnesota',
    # WNBA (ejemplo)
    'ny': 'new york', 'dal': 'dallas', 'gs': 'golden state', 'lv': 'las vegas', 'la': 'los angeles', 'chi': 'chicago',
    'ind': 'indiana', 'con': 'connecticut', 'pho': 'phoenix', 'was': 'washington', 'sea': 'seattle', 'min': 'minnesota',
}
def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)

def get_url_consenso(fecha):
    return f"https://contests.covers.com/consensus/topoverunderconsensus/all/expert/{fecha.strftime('%Y-%m-%d')}"

def get_url_resultados(deporte, fecha):
    # Ejemplo para MLB: https://www.covers.com/sports/mlb/matchups?selectedDate=2025-07-29
    deporte_map = {
        'MLB': 'mlb',
        'WNBA': 'wnba',
        'NFL': 'nfl',
        'NBA': 'nba',
        'NHL': 'nhl',
        'NCAAF': 'ncaaf',
        # Agrega más deportes según Covers
    }
    if deporte not in deporte_map:
        return None
    return f"https://www.covers.com/sports/{deporte_map[deporte]}/matchups?selectedDate={fecha.strftime('%Y-%m-%d')}"

def normalizar(texto):
    # Normaliza nombres de equipos eliminando tildes, espacios, guiones, puntos, comas y convirtiendo a minúsculas
    import unicodedata
    if not isinstance(texto, str):
        return ''
    texto = texto.strip().lower()
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')  # elimina tildes
    texto = texto.replace('&', 'and')
    texto = texto.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    texto = texto.replace('-', '').replace('.', '').replace(',', '').replace("'", '')
    texto = texto.replace('  ', ' ')
    texto = texto.replace('st ', 'saint ')
    texto = texto.replace('é', 'e')
    texto = texto.replace('ü', 'u')
    texto = texto.replace('ã', 'a')
    texto = texto.replace('ç', 'c')
    texto = texto.replace('the ', '')
    texto = texto.replace(' los ', ' ')
    texto = texto.replace(' las ', ' ')
    texto = texto.replace(' de ', ' ')
    texto = texto.replace('del ', '')
    texto = texto.replace(' la ', ' ')
    texto = texto.replace(' el ', ' ')
    texto = texto.replace(' fc', '')
    texto = texto.replace(' sc', '')
    texto = texto.replace(' ac', '')
    texto = texto.replace(' bc', '')
    texto = texto.replace('  ', ' ')
    texto = texto.strip()
    # Aplica mapeo de abreviaturas si existe
    if texto in ABREVIATURAS_EQUIPOS:
        return ABREVIATURAS_EQUIPOS[texto]
    return texto

# --- SCRAPING PRINCIPAL ---

def scrapear_consensos(fecha):
    print(f"Scrapeando consensos para {fecha.strftime('%Y-%m-%d')}")
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=chrome_options)
    url = get_url_consenso(fecha)
    driver.get(url)
    time.sleep(5)
    try:
        show_more = driver.find_element("id", "ShowMoreButton")
        if show_more.is_displayed() and show_more.is_enabled():
            show_more.click()
            print("[consensos] Botón 'Show More' presionado", flush=True)
            time.sleep(2)
    except Exception:
        pass
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    partidos = []
    filas = soup.find_all('tr')
    for fila in filas:
        celdas = fila.find_all('td')
        if not celdas or len(celdas) < 1:
            continue
        matchup_td = None
        for td in celdas:
            if td.find('span', class_='covers-CoversConsensus-table--teamBlock'):
                matchup_td = td
                break
        if not matchup_td:
            continue
        deporte = ''
        league_span = matchup_td.find('span', class_='covers-CoversConsensus-table--league')
        if league_span:
            league_a = league_span.find('a')
            if league_a:
                deporte = league_a.get_text(strip=True)
        eq1_tag = matchup_td.find('span', class_='covers-CoversConsensus-table--teamBlock')
        eq2_tag = matchup_td.find('span', class_='covers-CoversConsensus-table--teamBlock2')
        equipo1 = eq1_tag.find('a').get_text(strip=True) if eq1_tag and eq1_tag.find('a') else ''
        equipo2 = eq2_tag.find('a').get_text(strip=True) if eq2_tag and eq2_tag.find('a') else ''
        if not equipo1 or not equipo2:
            continue
        total = ''
        total_expertos = 0
        porc_under = porc_over = None
        for celda in celdas:
            porc_tags = celda.find_all('span')
            for porc_tag in porc_tags:
                porc_text = porc_tag.get_text(strip=True)
                porc_val = int(re.findall(r'\d+', porc_text)[0]) if re.findall(r'\d+', porc_text) else None
                if 'Over' in porc_text:
                    porc_over = porc_val
                elif 'Under' in porc_text:
                    porc_under = porc_val
        if len(celdas) >= 5:
            total = celdas[3].get_text(strip=True)
            picks_celda = celdas[4]
            picks = picks_celda.get_text(separator='|', strip=True).split('|')
            if len(picks) == 2 and picks[0].isdigit() and picks[1].isdigit():
                total_expertos = int(picks[0]) + int(picks[1])
        partidos.append({
            'fecha': fecha.strftime('%Y-%m-%d'),
            'deporte': deporte,
            'equipo1': equipo1,
            'equipo2': equipo2,
            'total': total,
            'porcentaje_under': porc_under,
            'porcentaje_over': porc_over,
            'total_expertos': total_expertos
        })
    driver.quit()
    return partidos

def scrapear_resultados(deporte, fecha):
    print(f"Scrapeando resultados para {deporte} {fecha.strftime('%Y-%m-%d')}")
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=chrome_options)
    url_resultados = get_url_resultados(deporte, fecha)
    if not url_resultados:
        print(f"No hay URL de resultados para {deporte}")
        driver.quit()
        return []
    driver.get(url_resultados)
    time.sleep(3)
    html_res = driver.page_source
    # Guardar HTML de matchups para análisis posterior
    safe_deporte = normalizar(deporte).replace('/', '_').replace(' ', '_')
    html_dir = 'html_matchups'
    os.makedirs(html_dir, exist_ok=True)
    html_filename = os.path.join(html_dir, f"{fecha.strftime('%Y-%m-%d')}_{safe_deporte}.html")
    if not os.path.exists(html_filename):
        with open(html_filename, 'w', encoding='utf-8') as fhtml:
            fhtml.write(html_res)
    soup_res = BeautifulSoup(html_res, 'html.parser')
    bloques = soup_res.find_all('div', class_='d-flex flex-row justify-content-between align-items-start align-items-xl-center mb-2')
    resultados = []
    for bloque in bloques:
        equipos = bloque.find_all('span', class_='text-nowrap d-inline-flex align-items-center')
        scores = bloque.find_all('strong', class_='team-score away position-relative fs-5 d-xl-none d-inline-block bg-white lh-1 baseball text-primary')
        scores += bloque.find_all('strong', class_='team-score home position-relative fs-5 d-xl-none d-inline-block bg-white lh-1 baseball winner')
        if len(scores) < 2:
            scores = bloque.find_all('strong', class_='team-score')
        if len(equipos) == 2 and len(scores) == 2:
            nombre1 = equipos[0].get_text(strip=True)
            nombre2 = equipos[1].get_text(strip=True)
            try:
                score1 = int(scores[0].get_text(strip=True))
                score2 = int(scores[1].get_text(strip=True))
            except Exception:
                score1 = score2 = ''
            resultados.append({
                'fecha': fecha.strftime('%Y-%m-%d'),
                'deporte': deporte,
                'equipo1': nombre1,
                'equipo2': nombre2,
                'score1': score1,
                'score2': score2
            })
    driver.quit()
    return resultados

# --- MAIN ---
if __name__ == "__main__":
    # Solo un día para pruebas
    fecha = datetime.strptime('2025-07-30', '%Y-%m-%d')
    print(f"Scrapeando consensos y resultados para {fecha.strftime('%Y-%m-%d')}")
    partidos_consenso = scrapear_consensos(fecha)
    # Obtener todos los deportes únicos
    deportes_encontrados = set([p['deporte'] for p in partidos_consenso if p['deporte']])
    # Scraping de resultados de todos los deportes en una sola lista
    resultados_todos = []
    for deporte in deportes_encontrados:
        resultados_todos.extend(scrapear_resultados(deporte, fecha))

    # Matching y unificación
    def nombres_similares(n1, n2):
        n1n = normalizar(n1)
        n2n = normalizar(n2)
        if n1n == n2n:
            return True
        if n1n in n2n or n2n in n1n:
            return True
        def levenshtein(a, b):
            if len(a) < len(b):
                return levenshtein(b, a)
            if len(b) == 0:
                return len(a)
            previous_row = range(len(b) + 1)
            for i, c1 in enumerate(a):
                current_row = [i + 1]
                for j, c2 in enumerate(b):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            return previous_row[-1]
        if levenshtein(n1n, n2n) <= 2:
            return True
        return False

    for partido in partidos_consenso:
        resultado1 = resultado2 = ''
        for res in resultados_todos:
            if (
                nombres_similares(partido['equipo1'], res['equipo1']) and nombres_similares(partido['equipo2'], res['equipo2'])
            ) or (
                nombres_similares(partido['equipo1'], res['equipo2']) and nombres_similares(partido['equipo2'], res['equipo1'])
            ):
                if nombres_similares(partido['equipo1'], res['equipo1']):
                    resultado1 = res['score1']
                    resultado2 = res['score2']
                else:
                    resultado1 = res['score2']
                    resultado2 = res['score1']
                break
        partido['resultado_equipo1'] = resultado1
        partido['resultado_equipo2'] = resultado2
        try:
            total = float(partido['total'])
            suma = int(resultado1) + int(resultado2)
            partido['resultado_real'] = 'over' if suma > total else 'under'
        except Exception:
            partido['resultado_real'] = ''

    # Guardar en un solo CSV
    with open('historico_consensos.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                'fecha', 'deporte', 'equipo1', 'equipo2', 'total', 'porcentaje_under', 'porcentaje_over', 'total_expertos',
                'resultado_equipo1', 'resultado_equipo2', 'resultado_real'
            ],
            delimiter=';'
        )
        writer.writeheader()
        for partido in partidos_consenso:
            writer.writerow(partido)
    print("Datos guardados en historico_consensos.csv (delimitador: punto y coma)")
