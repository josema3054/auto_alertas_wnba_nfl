"""
Script automatizado para scrapeo, guardado de partidos y envío de alertas por Telegram
"""


import os
import sys
import json
from datetime import datetime, timedelta
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re

# Importar TelegramNotifier y settings adaptados a la estructura actual
from telegram_notifier import TelegramNotifier
import settingspsautoalerta as settings

PARTIDOS_FILE = 'partidos_hoy_all.json'

def get_url_fecha():
    hoy = datetime.now().date()
    # Usar la URL de All Leagues para obtener todos los deportes
    return f"https://contests.covers.com/consensus/topoverunderconsensus/all/expert/{hoy.strftime('%Y-%m-%d')}"

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

def scrape_partidos():
    """Scrapea los partidos y sus horas, devuelve lista de dicts"""
    url = get_url_fecha()
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)
    time.sleep(5)  # Espera para que cargue el JS

    # Intentar presionar el botón 'Show More' si existe
    try:
        show_more = driver.find_element("id", "ShowMoreButton")
        if show_more.is_displayed() and show_more.is_enabled():
            show_more.click()
            print("[scrape_partidos] Botón 'Show More' presionado", flush=True)
            time.sleep(2)  # Espera a que cargue el resto de los partidos
        else:
            print("[scrape_partidos] Botón 'Show More' encontrado pero no interactivo", flush=True)
    except Exception:
        print("[scrape_partidos] Botón 'Show More' no encontrado", flush=True)

    html = driver.page_source
    driver.quit()
    soup = BeautifulSoup(html, 'html.parser')
    partidos = []
    # Buscar filas de la tabla de consenso
    filas = soup.find_all('tr')
    for fila in filas:
        celdas = fila.find_all('td')
        if not celdas or len(celdas) < 1:
            continue
        # Extraer equipos y deporte
        matchup_td = None
        for td in celdas:
            if td.find('span', class_='covers-CoversConsensus-table--teamBlock'):
                matchup_td = td
                break
        if not matchup_td:
            continue
        # Extraer el deporte
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
        # Hora (si existe en otra celda)
        hora_et = ''
        for celda in celdas:
            texto = celda.get_text(separator=' ', strip=True)
            if re.search(r'(am|pm) ET', texto):
                hora_et = texto
                break
        # Convertir hora ET a fecha y hora argentina (acepta formatos con y sin puntos)
        fecha_arg = ''
        hora_arg = ''
        if hora_et:
            hora_et_limpia = hora_et.replace('ET', '').strip()
            # Elimina puntos y dobles espacios
            hora_et_limpia = re.sub(r'\.', '', hora_et_limpia)
            hora_et_limpia = re.sub(r'\s+', ' ', hora_et_limpia)
            # Agrega el año actual si no está presente
            año_actual = datetime.now().year
            # Si el string no contiene el año, lo agregamos al final
            if str(año_actual) not in hora_et_limpia:
                hora_et_limpia = f"{hora_et_limpia} {año_actual}"
            formatos = ["%a %b %d %I:%M %p %Y", "%A %B %d %I:%M %p %Y"]
            for fmt in formatos:
                try:
                    dt = datetime.strptime(hora_et_limpia, fmt)
                    dt_arg = dt + timedelta(hours=1)  # ET=UTC-4, Argentina=UTC-3
                    fecha_arg = dt_arg.strftime("%Y-%m-%d")
                    hora_arg = dt_arg.strftime("%H:%M")
                    break
                except Exception:
                    continue
            if not fecha_arg:
                # Si sigue fallando, intenta con el formato original con puntos y año
                hora_et_puntos = hora_et.replace('ET', '').strip()
                if str(año_actual) not in hora_et_puntos:
                    hora_et_puntos = f"{hora_et_puntos} {año_actual}"
                try:
                    dt = datetime.strptime(hora_et_puntos, "%a. %b. %d %I:%M %p %Y")
                    dt_arg = dt + timedelta(hours=1)
                    fecha_arg = dt_arg.strftime("%Y-%m-%d")
                    hora_arg = dt_arg.strftime("%H:%M")
                except Exception:
                    fecha_arg = ''
                    hora_arg = ''
        # Porcentajes Over/Under y picks
        porc_under = porc_over = None
        # Asigna correctamente los porcentajes según el texto
        for celda in celdas:
            porc_tags = celda.find_all('span')
            for porc_tag in porc_tags:
                porc_text = porc_tag.get_text(strip=True)
                porc_val = int(re.findall(r'\d+', porc_text)[0]) if re.findall(r'\d+', porc_text) else None
                if 'Over' in porc_text:
                    porc_over = porc_val
                elif 'Under' in porc_text:
                    porc_under = porc_val
        # Picks: suma de los dos números en la celda correspondiente
        # Extraer el total y los picks según la posición de las celdas
        total = ''
        total_expertos = 0
        if len(celdas) >= 5:
            # El cuarto <td> es el total
            total = celdas[3].get_text(strip=True)
            # El quinto <td> son los picks (ejemplo: 5<br>3)
            picks_celda = celdas[4]
            picks = picks_celda.get_text(separator='|', strip=True).split('|')
            if len(picks) == 2 and picks[0].isdigit() and picks[1].isdigit():
                total_expertos = int(picks[0]) + int(picks[1])
        partido = {
            'deporte': deporte,
            'equipo1': equipo1,
            'equipo2': equipo2,
            'fecha': fecha_arg,
            'hora': hora_arg,
            'porcentaje_under': porc_under,
            'porcentaje_over': porc_over,
            'total': total,
            'total_expertos': total_expertos
        }
        partidos.append(partido)
    return partidos

def guardar_partidos(partidos):
    with open(PARTIDOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(partidos, f, ensure_ascii=False, indent=2)
    print(f"✅ Partidos guardados en {PARTIDOS_FILE}", flush=True)

def cargar_partidos():
    if not os.path.exists(PARTIDOS_FILE):
        return []
    with open(PARTIDOS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

## Eliminar definición duplicada de hora_a_datetime
def hora_a_datetime(fecha_str, hora_str):
    # fecha_str: '2025-07-27', hora_str: '22:31'
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        hora = datetime.strptime(hora_str, "%H:%M").time()
        return datetime.combine(fecha, hora)
    except Exception:
        return None

def enviar_alerta(partido):
    notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)
    mensaje = (
        f"Deporte: {partido.get('deporte', '')}\n"
        f"Partido: {partido.get('equipo1', '')} vs {partido.get('equipo2', '')}\n"
        f"Hora: {partido.get('hora', '')}\n"
        f"Total: {partido.get('total', '')}\n"
        f"Under: {partido.get('porcentaje_under', '')}%\n"
        f"Over: {partido.get('porcentaje_over', '')}%\n"
        f"Total picks: {partido.get('total_expertos', '')}"
    )
    notifier.send_message_sync(mensaje)
    print(f"🚨 Alerta enviada: {mensaje}", flush=True)

def enviar_alerta_scrapeo(partido):
    notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)
    mensaje = (
        f"SOLO SCRAPEO\n"
        f"Deporte: {partido.get('deporte', '')}\n"
        f"Partido: {partido.get('equipo1', '')} vs {partido.get('equipo2', '')}\n"
        f"Hora: {partido.get('hora', '')}\n"
        f"Total: {partido.get('total', '')}\n"
        f"Under: {partido.get('porcentaje_under', '')}%\n"
        f"Over: {partido.get('porcentaje_over', '')}%\n"
        f"Total picks: {partido.get('total_expertos', '')}"
    )
    notifier.send_message_sync(mensaje)
    print(f"📋 Scrapeo enviado: {mensaje}", flush=True)

def main():
    print("Scrapeando partidos y guardando horas...", flush=True)
    partidos = scrape_partidos()
    for partido in partidos:
        partido['alertado'] = False
    guardar_partidos(partidos)
    # Calcular resumen por deporte
    resumen = {}
    for partido in partidos:
        d = partido.get('deporte', 'Otro')
        resumen[d] = resumen.get(d, 0) + 1
    total = len(partidos)
    resumen_str = f"Partidos scrapeados para hoy: {total}\n" + "\n".join([f"{k}: {v}" for k, v in resumen.items()])
    # Enviar resumen a Telegram
    notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)
    notifier.send_message_sync(resumen_str)
    print(resumen_str, flush=True)
    print("Esperando partidos próximos para alerta...", flush=True)
    fecha_ultimo_scrapeo = datetime.now().date()
    scrapeo_realizado_hoy = True
    def normalizar(texto):
        return texto.strip().lower() if isinstance(texto, str) else ''

    while True:
        ahora = datetime.now()
        # Log periódico cada minuto para confirmar que el script está activo
        print(f"[{ahora.strftime('%H:%M:%S')}] Script activo y esperando partidos...", flush=True)

        partidos = cargar_partidos()
        cambios = False
        # Solo hacer un re-scrapeo si hay partidos en rango
        partidos_en_rango = [p for p in partidos if (dt := hora_a_datetime(p['fecha'], p['hora'])) and 14 <= (dt - ahora).total_seconds() / 60 <= 16 and not p.get('alertado', False)]
        nuevos_partidos = []
        if partidos_en_rango:
            print(f"[{ahora.strftime('%H:%M:%S')}] Re-escrapeando para partidos próximos...", flush=True)
            nuevos_partidos = scrape_partidos()
        for partido in partidos:
            dt = hora_a_datetime(partido['fecha'], partido['hora'])
            if not dt:
                continue
            minutos = (dt - ahora).total_seconds() / 60
            if 14 <= minutos <= 16 and not partido.get('alertado', False):
                print(f"[{ahora.strftime('%H:%M:%S')}] Re-escrapeando: {partido['equipo1']} vs {partido['equipo2']}", flush=True)
                partido_actualizado = None
                for p in nuevos_partidos:
                    if (normalizar(p.get('equipo1')) == normalizar(partido.get('equipo1')) and
                        normalizar(p.get('equipo2')) == normalizar(partido.get('equipo2')) and
                        normalizar(p.get('fecha')) == normalizar(partido.get('fecha')) and
                        normalizar(p.get('hora')) == normalizar(partido.get('hora'))):
                        partido_actualizado = p
                        break
                # Solo enviar alerta si over o under > 79%
                alerta = False
                partido_alerta = partido_actualizado if partido_actualizado else partido
                if partido_alerta.get('porcentaje_over', 0) and partido_alerta['porcentaje_over'] > 79:
                    alerta = True
                if partido_alerta.get('porcentaje_under', 0) and partido_alerta['porcentaje_under'] > 79:
                    alerta = True
                if alerta:
                    enviar_alerta(partido_alerta)
                partido['alertado'] = True
                cambios = True
        if cambios:
            guardar_partidos(partidos)
        time.sleep(60)  # Revisar cada minuto

if __name__ == "__main__":
    main()
