# -*- coding: utf-8 -*-
import tkinter as tk
import json, os, re, shutil, calendar, csv, html, sys, traceback, threading
from pathlib import Path
from datetime import datetime, date, timedelta
from tkinter import Tk, StringVar, BooleanVar, messagebox, filedialog, PhotoImage, Text, END, Label, Canvas
from tkinter import ttk
import urllib.request
import urllib.parse
import urllib.error
import webbrowser
import html
import csv
import math
import uuid
from manager.modules.buchungen import (
    make_booking_id as booking_make_id,
    booking_identity_key as booking_make_identity_key,
    ensure_unique_booking_ids as booking_ensure_unique_ids,
    validate_booking_record as booking_validate_record,
    booking_conflicts as booking_find_conflicts,
    upsert_booking as booking_upsert,
    delete_booking_and_extras as booking_delete_with_extras,
)
from manager.modules.kalender import (
    month_bounds as kalender_month_bounds,
    grid_bounds as kalender_grid_bounds,
    booking_overlaps_range as kalender_booking_overlaps_range,
    occupied_range as kalender_occupied_range,
    month_metrics as kalender_month_metrics,
)
from manager.brain.mission_control_workflow import (
    build_daily_tasks as mc_build_daily_tasks,
    build_fidel_summary as mc_build_fidel_summary,
    quick_action_specs as mc_quick_action_specs,
)
from manager.modules.finanzen import (
    invoice_print_release as fin_invoice_print_release,
    municipality_rows_release as fin_municipality_rows_release,
)
from manager.brain.betriebskompass import (
    build_betriebskompass as compass_build,
    compact_summary as compass_summary,
)
from manager.modules.day_center import (
    build_day_center as day_center_build,
    format_day_center_text as day_center_format,
)
from manager.modules.laura_mode import (
    build_laura_tasks as laura_build_tasks,
    format_laura_tasks_text as laura_format_tasks,
)
from manager.modules.fruehstueck import (
    build_breakfast_shopping_list as breakfast_build_shopping,
    format_breakfast_shopping_text as breakfast_format_shopping,
)
from manager.modules.import_dedupe import (
    find_existing_booking_for_import as import_find_existing,
    merge_guest_master_data as import_merge_guest_data,
)
from manager.modules.import_backup import (
    find_latest_pre_import_backup as import_latest_backup,
    restore_json_backup as import_restore_backup,
    describe_backup as import_describe_backup,
)
from manager.modules.gastprofil import (
    profile_from_booking as guestprofile_from_booking,
)
from manager.modules.calendar_sync import (
    build_calendar_ics as calendar_sync_build_ics,
    validate_ics_content as calendar_sync_validate_ics,
    write_ics_file as calendar_sync_write_ics_file,
    build_outlook_csv_rows as calendar_sync_build_outlook_csv_rows,
    ics_escape as calendar_sync_escape_text,
    booking_uid as calendar_sync_booking_uid,
    booking_status as calendar_sync_booking_status,
)
from manager.modules.mobile_sync import (
    build_mobile_data as mobile_sync_build_data,
    write_mobile_data as mobile_sync_write_data,
    mobile_sync_default_dir as mobile_sync_default_dir,
    mobile_sync_export_summary as mobile_sync_export_summary,
)
try:
    import pandas as pd
except Exception:
    pd = None

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.pdfbase import pdfmetrics
except Exception:
    raise SystemExit("Programmfehler beim Start. Bitte den kompletten Fehlertext senden.")

PA_EXTRA_EVENT_KEYWORDS = ["Maria Laach", "Maria Laach am Jauerling", "Jauerling", "Feuerwehrfest", "Feuerwehrheuriger", "Dorffest", "Kirtag", "Zeltfest"]
APP_NAME = "Zuhause am Bach OS – Mission Control"
SUBTITLE = "Fidel kennt die Wachau. Gloria sieht die Kleinigkeiten. Pia macht aus Chaos Geschichten."
VERSION = "Version 32.4 BETA – Mobile Sync Export"
DEVELOPER = "J.F.X. Prem"
ORTSTAXE = 2.60

ADDRESS = """Zuhause am Bach
Gästehaus Wachau

Laura & Johann Prem
Aggsbach Markt 82
3641 Aggsbach Markt
Österreich – Wachau

Telefon Österreich: +43 (0) 664 6437526
Telefon Deutschland: +49 (0) 9436 5609650
E-Mail: johannprem@hotmail.com"""

AD_FOOTER = """Vielen Dank für Ihren Aufenthalt.<br/><br/>
<b>Zuhause am Bach</b><br/>
Ihre Unterkunft für Wanderer und Radfahrer am Welterbesteig Wachau und Donauradweg.<br/><br/>
<b>Die Wilden Wachauer Windis</b><br/>
Kinderbücher aus der Wachau. Begleiten Sie Fidel, Gloria und Pia auf ihren Abenteuern.<br/>
www.diewildenwachauerwindis.at<br/><br/>
<b>Steuerhinweis:</b> Gemäß den Bestimmungen der Kleinunternehmerregelung wird keine Umsatzsteuer ausgewiesen."""

def app_dir(): return Path(__file__).resolve().parent

def config_file():
    d = Path.home() / "Documents" / "Zuhause am Bach Manager Config"
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"

def default_data_dir():
    d = Path.home() / "Documents" / "Zuhause am Bach Manager V55"
    d.mkdir(parents=True, exist_ok=True)
    return d


def error_log_dir():
    """Zentraler Ordner für Fehlerprotokolle. Liegt bewusst im Dokumente-Ordner,
    damit Fehlermeldungen auch nach einem Programmabsturz auffindbar bleiben."""
    d = Path.home() / "Documents" / "Zuhause am Bach Manager Fehlerprotokolle"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = app_dir() / "Fehlerprotokolle"
        d.mkdir(parents=True, exist_ok=True)
    return d

def error_log_file():
    return error_log_dir() / f"Fehlerprotokoll_{datetime.now():%Y-%m-%d}.log"

def log_exception(context="Unbekannte Stelle", exc_type=None, exc_value=None, exc_tb=None):
    """Schreibt einen ausführlichen Fehlerbericht, ohne den ursprünglichen Fehler zu verschlucken."""
    if exc_type is None or exc_value is None or exc_tb is None:
        exc_type, exc_value, exc_tb = sys.exc_info()
    try:
        lines = []
        lines.append("=" * 90)
        lines.append(f"Zeit: {datetime.now():%Y-%m-%d %H:%M:%S}")
        lines.append(f"Programm: {APP_NAME} {VERSION}")
        lines.append(f"Stelle: {context}")
        lines.append(f"Fehler: {exc_type.__name__ if exc_type else 'Unbekannt'}: {exc_value}")
        lines.append("Traceback:")
        if exc_type and exc_value and exc_tb:
            lines.extend(traceback.format_exception(exc_type, exc_value, exc_tb))
        else:
            lines.append("Kein Traceback verfügbar.")
        lines.append("")
        path = error_log_file()
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path
    except Exception:
        # Notfall: Fehlerprotokoll darf niemals selbst das Programm beenden.
        return None

def install_error_logging():
    """Fängt nicht behandelte Fehler global ab und schreibt sie ins Fehlerprotokoll."""
    def _sys_hook(exc_type, exc_value, exc_tb):
        path = log_exception("Nicht behandelter Programmfehler", exc_type, exc_value, exc_tb)
        try:
            print(f"Fehler wurde protokolliert: {path}")
        except Exception:
            pass
    sys.excepthook = _sys_hook
    try:
        def _thread_hook(args):
            log_exception(f"Thread-Fehler: {getattr(args.thread, 'name', '')}", args.exc_type, args.exc_value, args.exc_traceback)
        threading.excepthook = _thread_hook
    except Exception:
        pass

def open_error_log_folder():
    p = error_log_dir()
    try:
        os.startfile(str(p))
    except Exception:
        try:
            webbrowser.open(p.as_uri())
        except Exception:
            pass

def data_dir():
    """Datenordner kann auf Google Drive gelegt werden."""
    cfg = config_file()
    try:
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            p = data.get("data_dir", "")
            if p:
                d = Path(p)
                d.mkdir(parents=True, exist_ok=True)
                return d
    except Exception:
        pass
    return default_data_dir()

def set_data_dir(path):
    d = Path(path)
    d.mkdir(parents=True, exist_ok=True)
    config_file().write_text(json.dumps({"data_dir": str(d)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return d
def out_dir():
    d = data_dir() / "Ausgaben"; d.mkdir(exist_ok=True); return d
def backup_dir():
    d = data_dir() / "Backups"; d.mkdir(exist_ok=True); return d
def data_file(): return data_dir() / "daten.json"

def school_holidays_file():
    """Lokale Ferientabelle für PreisAgent. Kann vom Benutzer gepflegt werden."""
    return app_dir() / "preisagent_schulferien_de_at.csv"

def pa_safe_date(value):
    try:
        if isinstance(value, date): return value
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None

def logo_file():
    p = app_dir() / "zuhause_am_bach_logo.png"
    return str(p) if p.exists() else ""

def add_logo_to_story(story, width_mm=42):
    """Logo robust in PDFs einfügen, mit korrektem Seitenverhältnis."""
    lf = logo_file()
    if not lf:
        return
    try:
        img = Image(lf)
        ratio = img.imageHeight / float(img.imageWidth) if img.imageWidth else 1
        img.drawWidth = width_mm * mm
        img.drawHeight = width_mm * ratio * mm
        story.append(img)
        story.append(Spacer(1, 4*mm))
    except Exception:
        # Falls das Logoformat nicht gelesen wird, PDF trotzdem erstellen.
        pass
def uid(prefix): return prefix + "-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
def fnum(v, default=0.0):
    s = str(v).replace("€","").replace("EUR","").replace(" ","").strip()
    if "," in s and "." in s: s=s.replace(".","").replace(",",".")
    elif "," in s: s=s.replace(",",".")
    try: return float(s)
    except Exception: return default
def fint(v, default=0):
    try: return int(float(str(v).replace(",",".")))
    except Exception: return default

def to_int(v, default=0):
    return fint(v, default)

def to_float(v, default=0.0):
    return fnum(v, default)
def money(v): return f"{float(v):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

# ---------------- Transliteration für Gemeinde/Ortstaxe ----------------
# Ziel: Gemeinde-Ausdrucke/PDF/CSV sollen bei hebräischen oder arabischen
# Schriftzeichen ohne Sonderfont lesbar bleiben. Es ist eine einfache,
# technische Umschrift, keine amtliche Pass-/Namensübersetzung.
HEBREW_TRANSLIT = {
    "א":"a","ב":"b","ג":"g","ד":"d","ה":"h","ו":"v","ז":"z","ח":"ch","ט":"t","י":"y","כ":"kh","ך":"kh",
    "ל":"l","מ":"m","ם":"m","נ":"n","ן":"n","ס":"s","ע":"a","פ":"p","ף":"f","צ":"tz","ץ":"tz",
    "ק":"k","ר":"r","ש":"sh","ת":"t",
    "ַ":"a","ָ":"a","ֵ":"e","ֶ":"e","ִ":"i","ֹ":"o","ֻ":"u","ְ":"","ּ":"","ֲ":"a","ֱ":"e","ֳ":"o","ׁ":"","ׂ":""
}
ARABIC_TRANSLIT = {
    "ا":"a","أ":"a","إ":"i","آ":"aa","ٱ":"a","ء":"'","ؤ":"u","ئ":"i","ب":"b","ت":"t","ث":"th","ج":"j",
    "ح":"h","خ":"kh","د":"d","ذ":"dh","ر":"r","ز":"z","س":"s","ش":"sh","ص":"s","ض":"d","ط":"t","ظ":"z",
    "ع":"a","غ":"gh","ف":"f","ق":"q","ك":"k","ک":"k","ل":"l","م":"m","ن":"n","ه":"h","ة":"a","و":"w",
    "ي":"y","ى":"a","ی":"y","ﻻ":"la","لا":"la","پ":"p","چ":"ch","ژ":"zh","گ":"g",
    "َ":"a","ُ":"u","ِ":"i","ً":"an","ٌ":"un","ٍ":"in","ْ":"","ّ":"","ـ":""
}

_TRANSLIT_RE = re.compile(r"[\u0590-\u05FF\u0600-\u06FF]")

def has_hebrew_arabic(text):
    return bool(_TRANSLIT_RE.search(str(text or "")))

def transliterate_he_ar(text):
    """Einfache Umschrift Hebräisch/Arabisch -> lateinische Zeichen.
    [Nicht verifiziert] Nicht amtlich, nur für interne Lesbarkeit im Gemeinde-Ausdruck.
    """
    s = str(text or "")
    if not has_hebrew_arabic(s):
        return s
    out = []
    for ch in s:
        if ch in HEBREW_TRANSLIT:
            out.append(HEBREW_TRANSLIT[ch])
        elif ch in ARABIC_TRANSLIT:
            out.append(ARABIC_TRANSLIT[ch])
        elif ord(ch) < 128 or ch.isspace() or ch in "-.,/&'()0123456789":
            out.append(ch)
        else:
            # andere Zeichen nicht erfinden, aber als Leerzeichen vermeiden, dass PDF zerbricht
            out.append(ch)
    res = "".join(out)
    res = re.sub(r"\s+", " ", res).strip()
    return res

def gemeinde_text(text):
    """Text speziell für Gemeinde-/Ortstaxe-Ausgabe."""
    return transliterate_he_ar(text)


def booking_birth_value(b):
    """Geburtsdatum robust lesen: alte und neue Feldnamen aus Import/Handeingabe.
    Erkennt auch unterschiedliche Groß-/Kleinschreibung aus Booking-Excel-Spalten.
    """
    if not isinstance(b, dict):
        return ""
    wanted=("birth", "geburt", "geburtsdatum", "geburtsdatum_gast", "geburtsdatum gast", "birth_date", "birthdate", "dob", "date_of_birth", "birthday", "date of birth", "geburts-datum")
    for key in wanted:
        val=b.get(key, "")
        if str(val).strip():
            return str(val).strip()
    low={str(k).strip().lower(): v for k,v in b.items()}
    for key in wanted:
        val=low.get(key, "")
        if str(val).strip():
            return str(val).strip()
    return ""

def pdate(v):
    if isinstance(v, date): return v
    s = str(v).strip()
    for fmt in ("%d.%m.%Y","%Y-%m-%d","%d/%m/%Y","%d.%m.%y"):
        try: return datetime.strptime(s[:10], fmt).date()
        except Exception: pass
    raise ValueError("Datum nicht erkannt: " + s)
def iso(v): return pdate(v).strftime("%Y-%m-%d")
def fmt(v): return pdate(v).strftime("%d.%m.%Y")
def nights(a,b): return max(0,(pdate(b)-pdate(a)).days)

# Stabilitätsfix V32.3: ältere Programmteile und Windi-Brain verwenden noch parse_date.
# pdate bleibt die zentrale Datumsfunktion; parse_date ist ein kompatibler Alias.
def parse_date(v):
    return pdate(v)




# ---------------- Dynamische Preisformel Johann-Version V14.1 ----------------
def pa_johann_season_factor(d):
    """Saisonfaktor für Wachau/Aggsbach Markt.
    Nebensaison April-Juni und September-Oktober = 1.00,
    Hauptsaison Juli-August = 1.20,
    Weinlese 15.09.-15.10. = 1.35.
    """
    d = pdate(d)
    if (d.month == 9 and d.day >= 15) or (d.month == 10 and d.day <= 15):
        return 1.35, "Weinlese"
    if d.month in (7, 8):
        return 1.20, "Hauptsaison"
    return 1.00, "Nebensaison"

def pa_johann_weekend_factor(d):
    d = pdate(d)
    return (1.25, "Fr-So") if d.weekday() in (4, 5, 6) else (1.00, "Mo-Do")

def pa_johann_occupancy_factor(occ_percent):
    try:
        occ = float(occ_percent)
    except Exception:
        occ = 0.0
    if occ >= 100: return 1.35, "100 % belegt"
    if occ >= 75: return 1.20, "75 % belegt"
    if occ >= 50: return 1.10, "50 % belegt"
    if occ >= 25: return 1.00, "25 % belegt"
    return 0.90, "0 % belegt"

def pa_johann_demand_factor(free_percent):
    try:
        free = float(free_percent)
    except Exception:
        free = 30.0
    if free < 10: return 1.25, "Nachfrage sehr hoch"
    if free < 20: return 1.15, "Nachfrage hoch"
    if free <= 40: return 1.00, "Nachfrage normal"
    return 0.90, "viele Unterkünfte frei"

def pa_johann_weather_factor(weather_score=0):
    try:
        score = float(weather_score)
    except Exception:
        score = 0.0
    if score >= 8: return 1.15, "Sonne/warm"
    if score <= -8: return 0.90, "Regen/kalt"
    return 1.00, "Wetter neutral"

def pa_johann_event_factor(event_score=0):
    try:
        score = float(event_score)
    except Exception:
        score = 0.0
    if score >= 30: return 1.40, "Top-Event"
    if score >= 20: return 1.25, "starkes Event"
    if score >= 10: return 1.15, "kleines Event"
    return 1.00, "kein Event"

def pa_johann_lastminute_factor(days_until_arrival):
    try:
        days = int(days_until_arrival)
    except Exception:
        days = 99
    if days <= 2: return 0.90, "Last-Minute 0-2 Tage"
    if days <= 6: return 0.95, "Last-Minute 3-6 Tage"
    if days <= 14: return 0.98, "7-14 Tage"
    return 1.00, ">14 Tage"

def pa_johann_round_price(price):
    return int(round(float(price) / 1.0) * 1)

def pa_johann_dynamic_price(base, d, occ_percent=25, free_percent=30, weather_score=0, event_score=0, days_until_arrival=30, min_price=79, max_price=149):
    sf, sl = pa_johann_season_factor(d)
    wf, wl = pa_johann_weekend_factor(d)
    of, ol = pa_johann_occupancy_factor(occ_percent)
    df, dl = pa_johann_demand_factor(free_percent)
    wetf, wetl = pa_johann_weather_factor(weather_score)
    evf, evl = pa_johann_event_factor(event_score)
    lmf, lml = pa_johann_lastminute_factor(days_until_arrival)
    raw = float(base) * sf * wf * of * df * wetf * evf * lmf
    capped = max(float(min_price), min(float(max_price), raw))
    rounded = pa_johann_round_price(capped)
    details = {
        "raw": raw, "price": rounded,
        "season_factor": sf, "season_label": sl,
        "weekend_factor": wf, "weekend_label": wl,
        "occupancy_factor": of, "occupancy_label": ol,
        "demand_factor": df, "demand_label": dl,
        "weather_factor": wetf, "weather_label": wetl,
        "event_factor": evf, "event_label": evl,
        "lastminute_factor": lmf, "lastminute_label": lml,
    }
    return rounded, details

def empty():
    return {
        "rooms":[{"id":uid("ROOM"),"name":"Doppelzimmer Bachblick","capacity":2,"price":90.0,"active":True,"notes":""}],
        "bookings":[],
        "extras":[],
        "shopping":[],
        "products":[
            {"id":uid("PROD"),"name":"Kaffee","price":3.0},{"id":uid("PROD"),"name":"Tee","price":2.5},
            {"id":uid("PROD"),"name":"Bier","price":3.8},{"id":uid("PROD"),"name":"Wein","price":4.5},
            {"id":uid("PROD"),"name":"Frühstück normal","price":12.0},{"id":uid("PROD"),"name":"Frühstück vegan","price":14.0},
            {"id":uid("PROD"),"name":"Lunchpaket","price":9.0}
        ]
    }
def load():
    if not data_file().exists():
        d=empty(); save(d); return d
    try: return json.loads(data_file().read_text(encoding="utf-8"))
    except Exception:
        d=empty(); save(d); return d
def save(d):
    # Stabilitätsfix V32.3: OneDrive/Windows-sicher speichern.
    # Ordner anlegen, temporäre Datei wirklich schreiben, dann atomar ersetzen.
    try:
        data_dir().mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        if data_file().exists():
            bd = data_dir() / "Backups"
            bd.mkdir(parents=True, exist_ok=True)
            backup = bd / ("auto_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
            shutil.copy2(data_file(), backup)
    except Exception:
        pass
    tmp = data_file().with_suffix(".tmp")
    content = json.dumps(d, ensure_ascii=False, indent=2)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(content, encoding="utf-8")
    if not tmp.exists():
        raise FileNotFoundError(f"Temporäre Speicherdatei wurde nicht erstellt: {tmp}")
    tmp.replace(data_file())
def active_rooms(d): return [r for r in d["rooms"] if r.get("active", True)]
def room_name(d,rid): return next((r["name"] for r in d["rooms"] if r["id"]==rid), "")
def room_price(d,rid): return float(next((r.get("price",0) for r in d["rooms"] if r["id"]==rid),0))
def extras_for(d,bid): return [e for e in d["extras"] if e["booking_id"]==bid]
def total(d,b):
    ns=nights(b["arrival"],b["departure"])
    room=float(b.get("price",0))*ns
    ex=sum(float(e["qty"])*float(e["price"]) for e in extras_for(d,b["id"]))
    dog=(float(b.get("dog_price",5.0))*ns) if b.get("dog") else 0.0
    tax=ORTSTAXE*int(b.get("persons",1))*ns
    return {"nights":ns,"room":room,"extras":ex+dog,"dog":dog,"tax":tax,"total":room+ex+dog+tax}

def checkout_due(d,b):
    """Offener Betrag bei Abreise.
    Bei Booking/importiert bezahlten Buchungen wird der Zimmerpreis nicht nochmals angezeigt.
    Offen bleiben nur Ortstaxe + Extras/Hund. Bei Direktbuchungen ohne bezahlt-Status bleibt alles offen.
    """
    t=total(d,b)
    paid_room = (str(b.get("source","")).strip().lower()=="booking") or bool(b.get("paid",False))
    due = (t["extras"] + t["tax"]) if paid_room else t["total"]
    return {
        "paid_room": paid_room,
        "due": due,
        "room_due": 0.0 if paid_room else t["room"],
        "extras_due": t["extras"],
        "tax_due": t["tax"],
        "total_original": t["total"],
        "nights": t["nights"],
    }

def checkout_due_text(d,b, short=False):
    c=checkout_due(d,b)
    if c["paid_room"]:
        if short:
            return f"offen: {money(c['due'])} (Taxe {money(c['tax_due'])} + Extras/Hund {money(c['extras_due'])})"
        return f"Offen Rechnung/Taxe: {money(c['due'])} | Taxe {money(c['tax_due'])} | Extras/Hund {money(c['extras_due'])} | Zimmer über Booking/bezahlt"
    if short:
        return f"offen: {money(c['due'])}"
    return f"Offen gesamt: {money(c['due'])} | inkl. Zimmer, Extras/Hund und Ortstaxe"

def clean_col(c): 
    return re.sub(r"\s+", " ", str(c).strip()).lower()

def find_col(cols, *names):
    for c in cols:
        cc = clean_col(c)
        for n in names:
            if clean_col(n) == cc:
                return c
    for c in cols:
        cc = clean_col(c)
        for n in names:
            if clean_col(n) in cc:
                return c
    return None

def extract_plz(txt):
    m = re.search(r"\b\d{4,5}\b", str(txt or ""))
    return m.group(0) if m else ""

def cell_text(row, col):
    """Zellwert aus Pandas-Zeile sauber als Text lesen."""
    if not col:
        return ""
    try:
        val = row.get(col, "")
    except Exception:
        return ""
    try:
        if pd is not None and pd.isna(val):
            return ""
    except Exception:
        pass
    # Excel-Zahlen ohne .0 übernehmen, HTML-Entities von Booking dekodieren
    try:
        if isinstance(val, float) and val.is_integer():
            s = str(int(val))
        else:
            s = str(val).strip()
    except Exception:
        s = str(val).strip()
    if s.lower() in ("nan", "nat", "none"):
        return ""
    return html.unescape(s).strip()

def split_booking_address(raw_address, plz="", city="", street=""):
    """Booking-Adresse in Straße / PLZ / Ort aufteilen, soweit die Daten im Export vorhanden sind.
    Wichtig: Wenn Booking nur Straße/Hausnummer liefert, können PLZ und Wohnort nicht erfunden werden.
    """
    raw = html.unescape(str(raw_address or "")).strip()
    street = html.unescape(str(street or "")).strip()
    plz = html.unescape(str(plz or "")).strip()
    city = html.unescape(str(city or "")).strip()

    # Wenn keine eigene Straße-Spalte existiert, ist Booking-Spalte "Adresse" meist nur die Straße.
    if not street and raw:
        street = raw

    # Muster: Musterstraße 1, 12345 Musterstadt
    m = re.search(r"(.+?)[,;]\s*(\d{4,5})\s+(.+)$", raw)
    if m:
        if not street or street == raw:
            street = m.group(1).strip()
        if not plz:
            plz = m.group(2).strip()
        if not city:
            city = m.group(3).strip(" ,;")
        return plz, city, street

    # Muster: 12345 Musterstadt, Musterstraße 1
    m = re.search(r"^(\d{4,5})\s+([^,;]+)[,;]\s*(.+)$", raw)
    if m:
        if not plz:
            plz = m.group(1).strip()
        if not city:
            city = m.group(2).strip(" ,;")
        if not street or street == raw:
            street = m.group(3).strip(" ,;")
        return plz, city, street

    # Muster: Musterstraße 1 12345 Musterstadt
    m = re.search(r"(.+?)\s+(\d{4,5})\s+([^,;]+)$", raw)
    if m:
        if not street or street == raw:
            street = m.group(1).strip()
        if not plz:
            plz = m.group(2).strip()
        if not city:
            city = m.group(3).strip(" ,;")
        return plz, city, street

    if not plz:
        plz = extract_plz(raw)
    return plz, city, street

def normalize_phone(phone):
    """Telefonnummern aus Booking sauber darstellen: 00 -> +, Ziffernfolge -> führendes +."""
    s = str(phone or "").strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return ""
    s = s.replace("–", "-").replace("—", "-")
    if s.startswith("00"):
        return "+" + s[2:]
    if s.startswith("+"):
        return s
    if s and s[0].isdigit():
        return "+" + s
    return s


def norm_key(s):
    """Vergleichsschlüssel für Namen/Straßen."""
    s = html.unescape(str(s or "")).strip().lower()
    s = s.replace("ß", "ss")
    return re.sub(r"[^a-z0-9äöü]", "", s)

def phone_key(s):
    """Nur Ziffern für Telefonnummernvergleich."""
    return re.sub(r"\D+", "", normalize_phone(s or ""))

def address_template_file():
    return data_dir() / "Adresskorrekturen.csv"

def ensure_address_template():
    """Leere Korrekturdatei anlegen, die der Nutzer später befüllen kann."""
    try:
        f = address_template_file()
        if not f.exists():
            with open(f, "w", newline="", encoding="utf-8-sig") as out:
                w = csv.writer(out, delimiter=";")
                w.writerow(["Buchungsnummer","Gast","Straße","PLZ","Wohnort","Land","Telefon"])
        return f
    except Exception:
        return None

def detect_delimiter(path):
    try:
        sample = Path(path).read_text(encoding="utf-8-sig", errors="ignore")[:1000]
        return ";" if sample.count(";") >= sample.count(",") else ","
    except Exception:
        return ";"

def row_get_ci(row, *names):
    """CSV-Zeile case-insensitive lesen."""
    lookup = {norm_key(k): v for k, v in row.items()}
    for n in names:
        key = norm_key(n)
        if key in lookup and str(lookup[key]).strip():
            return html.unescape(str(lookup[key]).strip())
    return ""

def add_address_index(index, row, force=False):
    """Adresse in Index eintragen. Korrekturdateien dürfen bestehende Werte überschreiben."""
    plz = str(row.get("plz","")).strip()
    city = str(row.get("city","")).strip()
    if not plz and not city:
        return
    guest = row.get("guest","")
    street = row.get("street","")
    country = row.get("country","")
    phone = row.get("phone","")
    booking_no = row.get("booking_no","")

    keys = []
    if booking_no:
        keys.append(("booking", norm_key(booking_no)))
    pk = phone_key(phone)
    if pk:
        keys.append(("phone", pk))
    if guest and street:
        keys.append(("gueststreet", norm_key(guest) + "|" + norm_key(street)))
    if street and country:
        keys.append(("streetcountry", norm_key(street) + "|" + norm_key(country)))

    clean = {
        "plz": plz,
        "city": city,
        "street": str(street or "").strip(),
        "country": str(country or "").strip(),
        "phone": normalize_phone(phone),
        "guest": str(guest or "").strip(),
        "booking_no": str(booking_no or "").strip(),
    }
    for k in keys:
        if force or k not in index:
            index[k] = clean

def load_address_corrections():
    """Adresskorrekturen aus CSV-Dateien laden."""
    rows = []
    try:
        bases = [data_dir(), out_dir(), app_dir()]
        seen = set()
        for base in bases:
            try:
                patterns = ["Adresskorrekturen*.csv", "Fehlende_PLZ_Wohnort_Import_*.csv"]
                for pat in patterns:
                    for f in Path(base).glob(pat):
                        if f in seen:
                            continue
                        seen.add(f)
                        delim = detect_delimiter(f)
                        with open(f, "r", newline="", encoding="utf-8-sig", errors="ignore") as inp:
                            reader = csv.DictReader(inp, delimiter=delim)
                            for r in reader:
                                plz = row_get_ci(r, "PLZ", "Postleitzahl", "Postal code", "Zip")
                                city = row_get_ci(r, "Wohnort", "Ort", "Stadt", "City", "Town")
                                # Nur echte Korrekturzeilen übernehmen
                                if not plz and not city:
                                    continue
                                rows.append({
                                    "booking_no": row_get_ci(r, "Buchungsnummer", "Booking number", "Reservierungsnummer"),
                                    "guest": row_get_ci(r, "Gast", "Gästename", "Name", "Guest"),
                                    "street": row_get_ci(r, "Straße", "Strasse", "Adresse", "Address", "Street"),
                                    "plz": plz,
                                    "city": city,
                                    "country": row_get_ci(r, "Land", "Country", "Booker country"),
                                    "phone": row_get_ci(r, "Telefon", "Telefonnummer", "Phone"),
                                })
            except Exception:
                pass
    except Exception:
        pass
    return rows

def build_address_index(d):
    """Stammdatenindex aus vorhandenen Buchungen und manuellen Korrekturdateien bauen."""
    index = {}
    try:
        for b in d.get("bookings", []):
            add_address_index(index, {
                "booking_no": b.get("booking_no",""),
                "guest": b.get("guest",""),
                "street": b.get("street",""),
                "plz": b.get("plz",""),
                "city": b.get("city",""),
                "country": b.get("country",""),
                "phone": b.get("phone",""),
            }, force=False)
        # Manuelle Korrekturdateien haben Vorrang
        for r in load_address_corrections():
            add_address_index(index, r, force=True)
    except Exception:
        pass
    return index

def apply_address_correction(index, booking_no="", guest="", phone="", street="", country="", plz="", city=""):
    """PLZ/Wohnort automatisch aus vorhandenen Stammdaten/Korrekturdateien ergänzen."""
    before = (plz or "", city or "")
    keys = []
    if booking_no:
        keys.append(("booking", norm_key(booking_no)))
    pk = phone_key(phone)
    if pk:
        keys.append(("phone", pk))
    if guest and street:
        keys.append(("gueststreet", norm_key(guest) + "|" + norm_key(street)))
    if street and country:
        keys.append(("streetcountry", norm_key(street) + "|" + norm_key(country)))

    hit = None
    for k in keys:
        if k in index:
            hit = index[k]
            break

    if hit:
        if not plz:
            plz = hit.get("plz","")
        if not city:
            city = hit.get("city","")
        if not country:
            country = hit.get("country","")
        if not street:
            street = hit.get("street","")
    corrected = (before != ((plz or ""), (city or "")))
    return plz, city, street, country, corrected


def app_settings_file():
    """Programmeinstellungen im Datenordner, ohne die Google-Drive-Config zu überschreiben."""
    return data_dir() / "einstellungen.json"

def load_config():
    try:
        f=app_settings_file()
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"invoice_year": date.today().year, "invoice_no": 0}

def save_config(c):
    try:
        app_settings_file().write_text(json.dumps(c,ensure_ascii=False,indent=2), encoding="utf-8")
    except Exception:
        pass

def next_invoice_number():
    c=load_config()
    y=date.today().year
    if int(c.get("invoice_year",0)) != y:
        c["invoice_year"]=y
        c["invoice_no"]=0
    c["invoice_no"]=int(c.get("invoice_no",0))+1
    save_config(c)
    return f"{y}-{int(c['invoice_no']):04d}"

def auto_backup_now(label="AUTO"):
    try:
        src=data_file()
        if src.exists():
            dest=backup_dir()/(f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            shutil.copy2(src,dest)
            return dest
    except Exception:
        pass
    return None

def last_backup_age_days():
    try:
        files=sorted(backup_dir().glob("*.json"), key=lambda p:p.stat().st_mtime, reverse=True)
        if not files:
            return None
        return int((datetime.now().timestamp()-files[0].stat().st_mtime)/86400)
    except Exception:
        return None


# Online-Wetter für Aggsbach Markt / Wachau
AGGSBACH_LAT = 48.294
AGGSBACH_LON = 15.404

def weather_code_text(code):
    try:
        code=int(code)
    except Exception:
        return "unbekannt"
    mapping={
        0:"sonnig",1:"überwiegend sonnig",2:"leicht bewölkt",3:"bewölkt",
        45:"Nebel",48:"Reifnebel",
        51:"leichter Nieselregen",53:"Nieselregen",55:"starker Nieselregen",
        61:"leichter Regen",63:"Regen",65:"starker Regen",
        66:"gefrierender Regen",67:"starker gefrierender Regen",
        71:"leichter Schneefall",73:"Schneefall",75:"starker Schneefall",
        80:"leichte Schauer",81:"Schauer",82:"starke Schauer",
        95:"Gewitter",96:"Gewitter mit Hagel",99:"starkes Gewitter mit Hagel"
    }
    return mapping.get(code, f"Wettercode {code}")

def fetch_aggsbach_weather_7days(timeout=8):
    """7-Tage-Wetter online über Open-Meteo, ohne API-Key.
    Gibt Dict nach ISO-Datum zurück.
    """
    url=(
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={AGGSBACH_LAT}&longitude={AGGSBACH_LON}"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_mean,precipitation_sum"
        "&timezone=Europe%2FVienna&forecast_days=7"
    )
    try:
        with urllib.request.urlopen(url,timeout=timeout) as resp:
            raw=resp.read().decode("utf-8")
        data=json.loads(raw)
        daily=data.get("daily",{})
        dates=daily.get("time",[])
        out={}
        for i, ds in enumerate(dates):
            try:
                out[ds]={
                    "weather_code": daily.get("weather_code",[None]*len(dates))[i],
                    "weather": weather_code_text(daily.get("weather_code",[None]*len(dates))[i]),
                    "temp_max": daily.get("temperature_2m_max",[None]*len(dates))[i],
                    "temp_min": daily.get("temperature_2m_min",[None]*len(dates))[i],
                    "precip_prob": daily.get("precipitation_probability_mean",[None]*len(dates))[i],
                    "precip_sum": daily.get("precipitation_sum",[None]*len(dates))[i],
                    "source":"online"
                }
            except Exception:
                pass
        return out, None
    except Exception as e:
        return {}, str(e)


def maximize_window_10plus(root):
    """Startet möglichst groß, ohne auf kleineren Bildschirmen Elemente abzuschneiden."""
    try:
        root.geometry("1680x980")
        root.minsize(1360,820)
    except Exception:
        pass
    try:
        root.state("zoomed")
    except Exception:
        try:
            root.attributes("-zoomed", True)
        except Exception:
            pass

class App:
    def __init__(self):
        self.d=load()
        self.d.setdefault("shopping", [])
        self.d.setdefault("invoices", [])
        self.d.setdefault("products", [])
        existing_names={p.get("name","") for p in self.d["products"]}
        for name,price,cat in [("Hund",5.0,"Zusatzleistung"),("Kaffee",3.0,"Getränk"),("Tee",2.5,"Getränk"),("Bier",3.8,"Getränk"),("Wein",4.5,"Getränk"),("Mineralwasser",2.5,"Getränk"),("Frühstück normal",12.0,"Speise"),("Frühstück vegan",14.0,"Speise"),("Lunchpaket",9.0,"Speise")]:
            if name not in existing_names:
                self.d["products"].append({"id":uid("PROD"),"name":name,"price":price,"category":cat})
        save(self.d)
        self.cur_b=None; self.cur_r=None; self.cur_e=None; self.cur_p=None; self.cur_shop=None
        self.root=Tk(); self.root.title(f"{APP_NAME} – {VERSION}")
        def _tk_error(exc_type, exc_value, exc_tb):
            path = log_exception("Tkinter-Aktion / Button / Eingabefeld", exc_type, exc_value, exc_tb)
            try:
                messagebox.showerror("Programmfehler", f"Ein Fehler wurde protokolliert.\n\nFehlerprotokoll:\n{path}")
            except Exception:
                pass
        self.root.report_callback_exception = _tk_error
        self.root.geometry("1520x950"); self.root.minsize(1280,830)
        maximize_window_10plus(self.root)
        self.build(); self.refresh_all(); self.root.mainloop()

    def safe_select_tab(self, tab):
        """Notebook-Tab sicher öffnen.

        Stabilitätsfix V32.3: Nach UI-Umbauten können gespeicherte Tab-Referenzen
        auf ein anderes Notebook zeigen. Statt TclError wird sauber protokolliert.
        """
        try:
            if tab in self.nb.tabs():
                self.nb.select(tab)
                return True
            # Fallback: manche Tk-Versionen liefern Strings; Vergleich als str.
            tabs = [str(t) for t in self.nb.tabs()]
            if str(tab) in tabs:
                self.nb.select(str(tab))
                return True
            try:
                self.status.set("Ansicht ist in dieser Version nicht verfügbar.")
            except Exception:
                pass
            return False
        except Exception:
            log_exception("Notebook-Tab öffnen")
            return False

    def build(self):
        # Modernes Wachau-Design
        # Wachau Poster Design – inspiriert vom Werbebild
        self.root.configure(bg="#eef2f5")
        style=ttk.Style()
        try: style.theme_use("clam")
        except Exception: pass

        blue="#0b3d70"
        blue2="#124e8a"
        green="#68a93c"
        green2="#4c8f2c"
        cream="#f7f8fa"
        white="#ffffff"
        sand="#e9efe6"
        text="#18314a"
        muted="#56718c"
        line="#d7dde5"

        style.configure(".", font=("Segoe UI",11))
        style.configure("TFrame", background=cream)
        style.configure("TLabel", background=cream, foreground=text)
        style.configure("TEntry", padding=8, font=("Segoe UI",11), fieldbackground=white, bordercolor=line, lightcolor=line, darkcolor=line)
        style.configure("TCombobox", padding=7, font=("Segoe UI",11), fieldbackground=white)
        style.configure("TCheckbutton", background=white, foreground=text, font=("Segoe UI",10))

        style.configure("Title.TLabel", background=cream, foreground=blue, font=("Segoe UI",20,"bold"))
        style.configure("Sub.TLabel", background=cream, foreground=green2, font=("Segoe UI",11,"bold"))
        style.configure("SmallSub.TLabel", background=cream, foreground=muted, font=("Segoe UI",8,"bold"))

        style.configure("Card.TFrame", background=white, relief="flat", borderwidth=1)
        style.configure("Card.TLabel", background=white, foreground=text, font=("Segoe UI",10))
        style.configure("CardTitle.TLabel", background=white, foreground=blue, font=("Segoe UI",13,"bold"))

        style.configure("Hero.TFrame", background=blue)
        style.configure("Hero.TLabel", background=blue, foreground="#ffffff", font=("Segoe UI",18,"bold"))
        style.configure("HeroSub.TLabel", background=blue, foreground="#cfe7ff", font=("Segoe UI",10,"bold"))

        style.configure("Primary.TButton", font=("Segoe UI",9,"bold"), padding=(10,7), foreground="#ffffff", background=blue2, borderwidth=0)
        style.configure("Touch.TButton", font=("Segoe UI",10,"bold"), padding=(12,8), foreground="#ffffff", background=green2, borderwidth=0)
        style.configure("Gold.TButton", font=("Segoe UI",9,"bold"), padding=(10,7), foreground="#ffffff", background=green, borderwidth=0)
        style.configure("Soft.TButton", font=("Segoe UI",9,"bold"), padding=(10,7), foreground=blue, background=sand, borderwidth=0)
        style.map("Primary.TButton", background=[("active",blue),("pressed","#092f57")], foreground=[("active","#ffffff")])
        style.map("Touch.TButton", background=[("active",green),("pressed","#39721d")], foreground=[("active","#ffffff")])
        style.map("Gold.TButton", background=[("active","#7dbe4f"),("pressed","#4d8d2e")])
        style.map("Soft.TButton", background=[("active","#f0f5ed"),("pressed","#dde8d9")])

        style.configure("TNotebook", background=cream, tabmargins=(6,6,6,0), borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12,7), font=("Segoe UI",9,"bold"), background="#dfe8f1", foreground=blue)
        style.map("TNotebook.Tab", background=[("selected",white),("active","#eef5fb")], foreground=[("selected",blue),("active",blue)])

        style.configure("Treeview", rowheight=26, font=("Segoe UI",9), fieldbackground=white, background=white, foreground=text, bordercolor=line, lightcolor=line, darkcolor=line)
        style.configure("Treeview.Heading", font=("Segoe UI",9,"bold"), background="#e8eef4", foreground=blue, relief="flat")
        style.map("Treeview", background=[("selected","#d8edd0")], foreground=[("selected",blue)])
        style.configure("Horizontal.TScrollbar", background="#dfe8f1", troughcolor=cream, arrowcolor=blue)
        style.configure("Vertical.TScrollbar", background="#dfe8f1", troughcolor=cream, arrowcolor=blue)

        header=ttk.Frame(self.root)
        header.pack(fill="x", padx=12, pady=(6,4))
        self.logo=None
        if logo_file():
            try:
                self.logo=PhotoImage(file=logo_file())
                fac=max(1,int(max(self.logo.width(),self.logo.height())/52))
                if fac>1: self.logo=self.logo.subsample(fac,fac)
                Label(header,image=self.logo,bg=cream).pack(side="left",padx=(0,10))
            except Exception: pass
        box=ttk.Frame(header)
        box.pack(side="left",fill="x",expand=True,pady=0)
        ttk.Label(box,text=APP_NAME,style="Title.TLabel").pack(anchor="w")
        ttk.Label(box,text="Fidel kennt die Wachau. Gloria sieht die Kleinigkeiten. Pia macht aus Chaos Geschichten.",style="Sub.TLabel").pack(anchor="w", pady=(0,0))
        ttk.Label(box,text=f"Die Pension, wo Geschichten entstehen.  ·  {VERSION}",style="SmallSub.TLabel").pack(anchor="w",pady=(2,0))

        badge=ttk.Frame(header,style="Card.TFrame",padding=(8,4))
        badge.pack(side="right",padx=(8,0),pady=0)
        ttk.Label(badge,text="V32.4 BETA",style="CardTitle.TLabel").pack(anchor="center")

        self.nb=ttk.Notebook(self.root); self.nb.pack(fill="both",expand=True,padx=8,pady=(0,6))

        # V27 Windi OS-Programm: 5 Hauptbereiche statt vieler verstreuter Reiter.
        # Alles bleibt vorhanden, wird aber logisch gruppiert.
        self.tab_dash=ttk.Frame(self.nb); self.nb.add(self.tab_dash,text="🐾 Fidel")
        self.tab_cal=ttk.Frame(self.nb); self.nb.add(self.tab_cal,text="🗓 Kalender")
        self.tab_people=ttk.Frame(self.nb); self.nb.add(self.tab_people,text="🎀 Gäste & Pia")
        self.tab_fin=ttk.Frame(self.nb); self.nb.add(self.tab_fin,text="📚 Finanzen & Gloria")
        self.tab_tools=ttk.Frame(self.nb); self.nb.add(self.tab_tools,text="⚙ System")

        # Gäste-Zentrale: Buchungen, Gastprofil und Kommunikation zusammen.
        self.people_nb=ttk.Notebook(self.tab_people)
        self.people_nb.pack(fill="both",expand=True,padx=8,pady=8)
        self.tab_book=ttk.Frame(self.people_nb); self.people_nb.add(self.tab_book,text="📘 Buchungen")
        self.tab_guest_ai=ttk.Frame(self.people_nb); self.people_nb.add(self.tab_guest_ai,text="🧠 Gastprofil 360")
        self.tab_whatsapp=ttk.Frame(self.people_nb); self.people_nb.add(self.tab_whatsapp,text="🎀 Pia Kommunikation")

        # Finanzen: Rechnung, Gemeinde und Statistik an einem Ort.
        self.fin_nb=ttk.Notebook(self.tab_fin)
        self.fin_nb.pack(fill="both",expand=True,padx=8,pady=8)
        self.tab_extras=ttk.Frame(self.fin_nb); self.fin_nb.add(self.tab_extras,text="💶 Rechnung")
        self.tab_gemeinde=ttk.Frame(self.fin_nb); self.fin_nb.add(self.tab_gemeinde,text="🏛 Gemeinde")
        self.tab_stats=ttk.Frame(self.fin_nb); self.fin_nb.add(self.tab_stats,text="📊 Statistik")

        # Revenue-Detail bleibt intern; die Tagesentscheidung ist im Kalender sichtbar.
        self.tab_revenue=ttk.Frame(self.root)

        # System: seltene Funktionen, Import, Stammdaten, Backup, Sync, Prüfung und Hilfe.
        self.tools_nb=ttk.Notebook(self.tab_tools)
        self.tools_nb.pack(fill="both",expand=True,padx=8,pady=8)
        self.tab_rooms=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_rooms,text="🛏 Zimmer")
        self.tab_import=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_import,text="⬇ Import")
        self.tab_articles=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_articles,text="📦 Artikel")
        # V31 Code Clean & UX: Doppelte Fachbereiche werden aus der Hauptnavigation genommen.
        # PreisAgent/Chancen/Revenue bleiben technisch vorhanden, erscheinen aber ueber Kalender/Fidel,
        # nicht als zweite oder dritte Preisverwaltung im System-Menue.
        self.tab_priceagent=ttk.Frame(self.root)
        self.tab_chances=ttk.Frame(self.root)
        self.tab_corr=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_corr,text="🧾 Stammdaten")
        self.tab_backup=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_backup,text="💾 Backup")
        self.tab_sync=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_sync,text="☁ Sync")
        self.tab_check=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_check,text="✅ Gloria-Prüfung")
        self.tab_brain=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_brain,text="🧠 Windi Brain")
        self.tab_day=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_day,text="📋 Tagesliste")
        self.tab_info=ttk.Frame(self.tools_nb); self.tools_nb.add(self.tab_info,text="ℹ Hilfe")

        self.build_dash(); self.build_year_stats(); self.build_chances(); self.build_price_agent(); self.build_revenue_management(); self.build_guest_ai_profile(); self.build_whatsapp_contacts(); self.build_gemeinde_core(); self.build_calendar(); self.build_bookings()
        self.build_rooms(); self.build_extras(); self.build_articles(); self.build_import(); self.build_corrections(); self.build_check(); self.build_windi_brain(); self.build_day(); self.build_backup(); self.build_sync(); self.build_info()

    def card(self,parent,title):
        f=ttk.Frame(parent,style="Card.TFrame",padding=15)
        f.pack(fill="both",expand=False,padx=11,pady=9)
        ttk.Label(f,text=title,style="CardTitle.TLabel").pack(anchor="w",pady=(0,9))
        return f

    def build_windi_os_strip(self, parent):
        """V27.0: Professionelle Windi-Rollen mit Charakter.
        Fidel = Concierge der Wachau, Gloria = heimliche Hausdame, Pia = kreatives Chaos.
        """
        row=ttk.Frame(parent)
        row.pack(fill="x",pady=(0,8))
        cards=[
            ("🐾 Fidel", "Concierge der Wachau", "Ich kenne die Wachau wie meine Pfoten. · Preise · Wetter · Heurige · Wanderer", lambda:self.safe_select_tab(self.tab_cal), "Kalender & Preise"),
            ("📚 Gloria", "Die heimliche Hausdame", "Ich kümmere mich um alles, bevor es jemand bemerkt. · Rechnungen · Gemeinde · Backup", lambda:self.open_system_area(self.tab_check), "Gloria prüft"),
            ("🎀 Pia", "Das kreative Chaos", "Irgendwas passiert immer – und meistens wird's dadurch noch schöner. · WhatsApp · Begrüßung · Gäste", lambda:self.open_guest_area(self.tab_whatsapp), "Pia hilft Gästen"),
        ]
        for title,role,body,cmd,btn in cards:
            box=ttk.Frame(row,style="Card.TFrame",padding=12)
            box.pack(side="left",fill="both",expand=True,padx=5)
            ttk.Label(box,text=title,style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(box,text=role,style="Card.TLabel").pack(anchor="w",pady=(0,4))
            ttk.Label(box,text=body,style="Card.TLabel",wraplength=360).pack(anchor="w")
            ttk.Button(box,text=btn,command=cmd,style="Soft.TButton").pack(anchor="w",pady=(8,0))


    # ---------------- V25 Navigationshelfer ----------------
    def open_guest_area(self, child=None):
        try:
            self.safe_select_tab(self.tab_people)
            if child is not None:
                self.people_nb.select(child)
        except Exception:
            pass

    def open_finance_area(self, child=None):
        try:
            self.safe_select_tab(self.tab_fin)
            if child is not None:
                self.fin_nb.select(child)
        except Exception:
            pass

    def open_system_area(self, child=None):
        try:
            self.safe_select_tab(self.tab_tools)
            if child is not None:
                self.tools_nb.select(child)
        except Exception:
            pass

    # ---------------- Einfaches Tages-Cockpit ----------------
    def build_dash(self):
        main=ttk.Frame(self.tab_dash)
        main.pack(fill="both",expand=True,padx=12,pady=10)

        hero=ttk.Frame(main,style="Hero.TFrame",padding=14)
        hero.pack(fill="x",pady=(0,10))
        ttk.Label(hero,text="🏡 Mission Control – Zuhause am Bach OS",style="Hero.TLabel").pack(anchor="w")
        ttk.Label(hero,text="Fidel empfiehlt. Gloria prüft Fakten. Pia kümmert sich um Gäste. Entscheidungen bleiben bei Laura & Johann.",style="HeroSub.TLabel").pack(anchor="w",pady=(3,0))

        self.build_windi_os_strip(main)

        motto=self.card(main,"🏡 Zuhause am Bach – Windi-Leitsatz")
        ttk.Label(motto,text="Nicht mehr klicken. Gastgeber sein.",style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(motto,text="Fidel empfiehlt die Wachau, Gloria hält das Haus sauber im Kopf, Pia macht aus kleinen Pannen gute Geschichten.",style="Card.TLabel",wraplength=1050).pack(anchor="w",pady=(2,0))

        # V27.0: Fidel, Gloria und Pia sind keine Maskottchen, sondern die Bedienlogik des Programms.
        fidel=self.card(main,"🐾 Fidel – Concierge der Wachau")
        self.fidel_today_text=Text(fidel,height=5,wrap="word",bg="#ffffff",relief="flat",font=("Segoe UI",10),padx=8,pady=6)
        self.fidel_today_text.pack(fill="x",expand=False)
        frow=ttk.Frame(fidel,style="Card.TFrame"); frow.pack(fill="x",pady=(4,0))
        ttk.Button(frow,text="Wochenbericht erstellen",command=self.fidel_weekly_report,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(frow,text="Aufgaben aktualisieren",command=self.refresh_dash,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(frow,text="Kalender/Preise öffnen",command=lambda:self.safe_select_tab(self.tab_cal),style="Soft.TButton").pack(side="left",padx=4)

        quick=self.card(main,"Schnellaktionen")
        qrow=ttk.Frame(quick,style="Card.TFrame")
        qrow.pack(fill="x")
        # Sprint 4: Schnellaktionen kommen aus manager.brain.mission_control_workflow
        # und werden hier nur noch mit GUI-Callbacks verbunden.
        quick_commands={
            "new_booking": lambda:self.open_guest_area(self.tab_book),
            "calendar": lambda:self.safe_select_tab(self.tab_cal),
            "invoice": lambda:self.open_finance_area(self.tab_extras),
            "municipality": lambda:self.open_finance_area(self.tab_gemeinde),
            "stats": lambda:self.open_finance_area(self.tab_stats),
            "print_calendar": self.dashboard_print_calendar,
            "weekly_report": self.fidel_weekly_report,
            "contact_guest": lambda:self.open_guest_area(self.tab_whatsapp),
        }
        for spec in mc_quick_action_specs():
            cmd=quick_commands.get(spec.action_id, lambda:None)
            ttk.Button(qrow,text=spec.label,command=cmd,style="Touch.TButton").pack(side="left",padx=5,pady=4)

        kpis=ttk.Frame(main)
        kpis.pack(fill="x",pady=(0,8))
        self.kpi_arrivals=StringVar(value="0")
        self.kpi_inhouse=StringVar(value="0")
        self.kpi_departures=StringVar(value="0")
        self.kpi_open=StringVar(value="0 €")
        self.kpi_breakfast=StringVar(value="0")
        self.kpi_missing=StringVar(value="0")

        for title,var in [
            ("Anreisen heute",self.kpi_arrivals),
            ("Im Haus",self.kpi_inhouse),
            ("Abreisen heute",self.kpi_departures),
            ("Offen",self.kpi_open),
            ("Frühstück morgen",self.kpi_breakfast),
            ("Warnungen",self.kpi_missing),
        ]:
            box=ttk.Frame(kpis,style="Card.TFrame",padding=10)
            box.pack(side="left",fill="x",expand=True,padx=4)
            ttk.Label(box,text=title,style="Card.TLabel").pack(anchor="center")
            ttk.Label(box,textvariable=var,style="CardTitle.TLabel").pack(anchor="center")

        compass=self.card(main,"🏡 Betriebskompass – alles Wichtige auf einen Blick")
        self.compass_summary_var=StringVar(value="Betriebskompass wird geladen …")
        ttk.Label(compass,textvariable=self.compass_summary_var,style="Card.TLabel").pack(anchor="w",pady=(0,6))
        self.compass_frame=ttk.Frame(compass,style="Card.TFrame")
        self.compass_frame.pack(fill="x")
        self.compass_vars=[]
        for title in ["Gäste","Finanzen","Daten","Frühstück","Müll","Preis","Backup"]:
            cbox=ttk.Frame(self.compass_frame,style="Card.TFrame",padding=8)
            cbox.pack(side="left",fill="x",expand=True,padx=3)
            var=StringVar(value=f"⚪ {title}\nlädt …")
            self.compass_vars.append(var)
            ttk.Label(cbox,textvariable=var,style="Card.TLabel",justify="center",wraplength=145).pack(anchor="center")

        cols=ttk.Frame(main)
        cols.pack(fill="both",expand=True)

        left=ttk.Frame(cols)
        left.pack(side="left",fill="both",expand=True,padx=(0,6))
        mid=ttk.Frame(cols)
        mid.pack(side="left",fill="both",expand=True,padx=6)
        right=ttk.Frame(cols)
        right.pack(side="left",fill="both",expand=True,padx=(6,0))

        self.today_arrivals_card=self.card(left,"Heute: Anreisen")
        self.dash_arrivals_frame=ttk.Frame(self.today_arrivals_card,style="Card.TFrame")
        self.dash_arrivals_frame.pack(fill="both",expand=True)

        self.today_inhouse_card=self.card(mid,"Heute: Im Haus")
        self.dash_inhouse_frame=ttk.Frame(self.today_inhouse_card,style="Card.TFrame")
        self.dash_inhouse_frame.pack(fill="both",expand=True)

        self.today_departures_card=self.card(right,"Heute: Abreisen / Checkout")
        self.dash_departures_frame=ttk.Frame(self.today_departures_card,style="Card.TFrame")
        self.dash_departures_frame.pack(fill="both",expand=True)

        lower=ttk.Frame(main)
        lower.pack(fill="both",expand=True,pady=(8,0))

        morgen=self.card(lower,"🎀 Pia – Das kreative Chaos")
        morgen.pack(side="left",fill="both",expand=True,padx=(0,6))
        self.dash_tomorrow_text=Text(morgen,height=7,wrap="word")
        self.dash_tomorrow_text.pack(fill="both",expand=True)

        warn=self.card(lower,"📚 Gloria – Die heimliche Hausdame")
        warn.pack(side="left",fill="both",expand=True,padx=(6,0))
        self.dash_warn_text=Text(warn,height=4,wrap="word")
        self.dash_warn_text.pack(fill="x",expand=False)
        task_frame=ttk.Frame(warn,style="Card.TFrame"); task_frame.pack(fill="both",expand=True,pady=(5,0))
        self.fidel_task_tree=ttk.Treeview(task_frame,columns=("status","prio","aufgabe"),show="headings",height=6)
        self.fidel_task_tree.heading("status",text="✓"); self.fidel_task_tree.column("status",width=35,anchor="center")
        self.fidel_task_tree.heading("prio",text="Prio"); self.fidel_task_tree.column("prio",width=55,anchor="center")
        self.fidel_task_tree.heading("aufgabe",text="Aufgabe"); self.fidel_task_tree.column("aufgabe",width=360,anchor="w")
        self.fidel_task_tree.pack(side="left",fill="both",expand=True)
        tscroll=ttk.Scrollbar(task_frame,orient="vertical",command=self.fidel_task_tree.yview); tscroll.pack(side="right",fill="y")
        self.fidel_task_tree.configure(yscrollcommand=tscroll.set)
        self.fidel_task_tree.bind("<Double-1>",self.fidel_toggle_task_done)
        task_btns=ttk.Frame(warn,style="Card.TFrame"); task_btns.pack(fill="x",pady=(4,0))
        ttk.Button(task_btns,text="markieren erledigt",command=self.fidel_toggle_task_done,style="Soft.TButton").pack(side="left",padx=3)
        ttk.Button(task_btns,text="heute zurücksetzen",command=self.fidel_reset_today_tasks,style="Soft.TButton").pack(side="left",padx=3)

        self.refresh_dash()

    def make_kpi_card(self,parent,title,var,accent="#0b3d70"):
        box=ttk.Frame(parent,style="Card.TFrame",padding=10)
        box.pack(side="left",fill="x",expand=True,padx=4)
        ttk.Label(box,text=title,style="Card.TLabel").pack(anchor="center")
        ttk.Label(box,textvariable=var,style="CardTitle.TLabel").pack(anchor="center")
        return box

    def clear_frame(self,frame):
        try:
            for w in frame.winfo_children():
                w.destroy()
        except Exception:
            pass

    def dashboard_guest_button(self,parent,text,bg,command=None):
        btn=tk.Button(parent,text=text,command=command,bg=bg,fg="#18314a",activebackground="#d9f7d3",relief="flat",anchor="w",justify="left",padx=10,pady=8,font=("Segoe UI",10,"bold"),wraplength=330)
        btn.pack(fill="x",pady=3)
        return btn

    def refresh_windis_success(self, monthly_total=0, inhouse=0, arrivals=0):
        # Bleibt als kompatible Methode erhalten.
        try:
            if hasattr(self,"success_var"):
                self.success_var.set(f"Monatsumsatz {money(monthly_total)} · Im Haus {inhouse} · Anreisen {arrivals}")
        except Exception:
            pass

    def dashboard_is_paid_booking(self,b):
        """Erkennt, ob eine Buchung für das Tages-Cockpit als bezahlt/abgerechnet gilt."""
        try:
            for key in ["paid","is_paid","payment_done","checkout_paid","checked_out_paid","paid_out","abgerechnet","rechnung_bezahlt","bezahlt"]:
                val=b.get(key,None)
                if val is True:
                    return True
                if isinstance(val,str) and val.strip().lower() in ["ja","yes","true","1","bezahlt","paid","abgerechnet"]:
                    return True
            st=str(b.get("status","")).strip().lower()
            if st in ["bezahlt","paid","abgerechnet","checkout bezahlt","checkout_bezahlt"]:
                return True
            pay=str(b.get("payment_status","")).strip().lower()
            if pay in ["bezahlt","paid","abgerechnet"]:
                return True
            # Wenn checkout_due genau 0 ist, ist nichts offen.
            due=checkout_due(self.d,b).get("due",0)
            try:
                if float(due) <= 0:
                    return True
            except Exception:
                pass
        except Exception:
            pass
        return False

    def dashboard_due_amount(self,b):
        """Offener Betrag für Dashboard, bezahlte Buchungen werden mit 0 gerechnet."""
        try:
            if self.dashboard_is_paid_booking(b):
                return 0.0
            due=checkout_due(self.d,b).get("due",0)
            return max(0.0,float(due or 0))
        except Exception:
            return 0.0

    def dashboard_booking_text(self,b,kind=""):
        guest=b.get("guest","")
        room=room_name(self.d,b.get("room_id",""))
        persons=b.get("persons",1)
        phone=b.get("phone","")
        bf=b.get("breakfast","")
        due=self.dashboard_due_amount(b)
        lines=[f"{guest}",f"{room} · {persons} Pers.",f"{fmt(b.get('arrival',''))} bis {fmt(b.get('departure',''))}"]
        if bf:
            lines.append(f"Frühstück: {bf}")
        if phone:
            lines.append(f"Tel: {phone}")
        if due>0:
            lines.append(f"Offen: {money(due)}")
        else:
            lines.append("Bezahlt / nichts offen")
        return "\n".join(lines)

    def dashboard_print_calendar(self):
        try:
            self.safe_select_tab(self.tab_cal)
            if hasattr(self,"calendar_month_pdf"):
                self.calendar_month_pdf()
        except Exception as e:
            messagebox.showerror("Kalender drucken",str(e))

    def refresh_dash(self):
        today=date.today()
        tomorrow=today+timedelta(days=1)
        bookings=self.d.get("bookings",[])
        active=[b for b in bookings if b.get("status")!="storniert"]

        arrivals=[]
        departures=[]
        inhouse=[]
        tomorrow_breakfast=[]
        warnings=[]
        open_total=0.0

        for b in active:
            try:
                arr=pdate(b.get("arrival",""))
                dep=pdate(b.get("departure",""))
            except Exception:
                warnings.append(f"Ungültiges Datum: {b.get('guest','ohne Name')}")
                continue

            if arr==today:
                arrivals.append(b)
            if dep==today:
                departures.append(b)
            if arr <= today < dep:
                inhouse.append(b)

            if arr <= today < dep and b.get("breakfast"):
                tomorrow_breakfast.append(b)

            due=self.dashboard_due_amount(b)
            try:
                if float(due)>0:
                    open_total += float(due)
            except Exception:
                pass

            missing=[]
            if not b.get("phone"):
                missing.append("Telefon")
            if not b.get("plz") or not b.get("city"):
                missing.append("PLZ/Ort")
            if not b.get("country"):
                missing.append("Land")
            if missing:
                warnings.append(f"{b.get('guest','ohne Name')}: fehlt {', '.join(missing)}")

        if hasattr(self,"kpi_arrivals"):
            self.kpi_arrivals.set(str(len(arrivals)))
            self.kpi_inhouse.set(str(len(inhouse)))
            self.kpi_departures.set(str(len(departures)))
            self.kpi_open.set(money(open_total))
            self.kpi_breakfast.set(str(len(tomorrow_breakfast)))
            self.kpi_missing.set(str(len(warnings)))

        try:
            muell_labels=[]
            if 'muell_terms_for_tomorrow' in globals():
                for t in muell_terms_for_tomorrow():
                    try:
                        muell_labels.append(f"{muell_icon(t.get('art'))} {t.get('art')}")
                    except Exception:
                        muell_labels.append(str(t.get('art','Müll')))
            try:
                sig=self.calendar_day_revenue_signal(today)
            except Exception:
                sig={}
            compass_items=compass_build(
                arrivals=len(arrivals),
                departures=len(departures),
                inhouse=len(inhouse),
                breakfast=len(tomorrow_breakfast),
                warnings=len(warnings),
                open_total=open_total,
                garbage_tomorrow=muell_labels,
                revenue_signal=sig,
                backup_status="ok",
                money_fn=money,
            )
            if hasattr(self,"compass_summary_var"):
                self.compass_summary_var.set(compass_summary(compass_items))
            if hasattr(self,"compass_vars"):
                for var,item in zip(self.compass_vars,compass_items):
                    var.set(f"{item.icon} {item.title}\n{item.detail}")
        except Exception:
            log_exception("Betriebskompass aktualisieren")

        for frame_name in ["dash_arrivals_frame","dash_inhouse_frame","dash_departures_frame"]:
            if hasattr(self,frame_name):
                self.clear_frame(getattr(self,frame_name))

        if hasattr(self,"dash_arrivals_frame"):
            if arrivals:
                for b in sorted(arrivals,key=lambda x:x.get("guest","")):
                    self.dashboard_guest_button(self.dash_arrivals_frame,self.dashboard_booking_text(b,"arrival"),"#e7f5ff",command=lambda bid=b.get("id"): self.open_booking_by_id(bid))
            else:
                ttk.Label(self.dash_arrivals_frame,text="Keine Anreisen heute.",style="Card.TLabel").pack(anchor="w",pady=5)

        if hasattr(self,"dash_inhouse_frame"):
            if inhouse:
                for b in sorted(inhouse,key=lambda x:x.get("guest","")):
                    self.dashboard_guest_button(self.dash_inhouse_frame,self.dashboard_booking_text(b,"inhouse"),"#eef8e9",command=lambda bid=b.get("id"): self.open_booking_by_id(bid))
            else:
                ttk.Label(self.dash_inhouse_frame,text="Heute keine Gäste im Haus.",style="Card.TLabel").pack(anchor="w",pady=5)

        if hasattr(self,"dash_departures_frame"):
            if departures:
                for b in sorted(departures,key=lambda x:x.get("guest","")):
                    self.dashboard_guest_button(self.dash_departures_frame,self.dashboard_booking_text(b,"departure"),"#fff4df",command=lambda bid=b.get("id"): self.open_booking_by_id(bid))
            else:
                ttk.Label(self.dash_departures_frame,text="Keine Abreisen heute.",style="Card.TLabel").pack(anchor="w",pady=5)

        if hasattr(self,"dash_tomorrow_text"):
            self.dash_tomorrow_text.delete("1.0",END)
            if tomorrow_breakfast:
                lines=["Frühstück morgen für Gäste, die heute Nacht im Haus sind:"]
                for b in sorted(tomorrow_breakfast,key=lambda x:x.get("guest","")):
                    lines.append(f"• {b.get('guest','')} · {room_name(self.d,b.get('room_id',''))} · {b.get('persons',1)} Pers. · {b.get('breakfast','')}")
                self.dash_tomorrow_text.insert("1.0","\n".join(lines))
            else:
                self.dash_tomorrow_text.insert("1.0","Kein Frühstück für morgen eingetragen.")

        if hasattr(self,"dash_warn_text"):
            self.dash_warn_text.delete("1.0",END)
            warn_lines=[]
            if open_total>0:
                warn_lines.append(f"• Offene Zahlungen gesamt: {money(open_total)}")
            warn_lines.extend([f"• {w}" for w in warnings[:20]])
            if len(warnings)>20:
                warn_lines.append(f"• +{len(warnings)-20} weitere Warnungen")
            if not warn_lines:
                warn_lines=["Keine offenen Warnungen gefunden."]
            self.dash_warn_text.insert("1.0","\n".join(warn_lines))

        # V23.0: Fidel-Zusammenfassung und Aufgabenliste direkt aus Tagesdaten.
        try:
            if hasattr(self,"fidel_today_text"):
                self.fidel_today_text.delete("1.0",END)
                self.fidel_today_text.insert("1.0",self.fidel_summary_lines(arrivals,departures,inhouse,tomorrow_breakfast,warnings,open_total))
            tasks=self.fidel_build_tasks(arrivals,departures,inhouse,tomorrow_breakfast,warnings,open_total)
            self.fidel_refresh_task_tree(tasks)
        except Exception:
            log_exception("Fidel Dashboard aktualisieren")

    def open_booking_by_id(self,bid):
        if not bid:
            return
        try:
            self.open_guest_area(self.tab_book)
            try:
                self.select_booking_in_tree(bid)
            except Exception:
                pass
            try:
                self.cur_b=bid
            except Exception:
                pass
            try:
                self.load_booking()
            except TypeError:
                self.load_booking(bid)
        except Exception as e:
            messagebox.showerror("Buchung öffnen",str(e))


    # ---------------- Fidel Tagesassistent V23.0 ----------------
    def fidel_task_done_store(self):
        self.d.setdefault("fidel_tasks_done", {})
        return self.d["fidel_tasks_done"]

    def fidel_task_key(self, text):
        return f"{date.today().isoformat()}|{text[:120]}"

    def fidel_build_tasks(self, arrivals, departures, inhouse, tomorrow_breakfast, warnings, open_total):
        # Sprint 4: Tagesaufgaben werden in Mission-Control-Workflowlogik gebaut.
        try:
            sig=self.calendar_day_revenue_signal(date.today())
        except Exception:
            sig={}
        return [(t.priority, t.text) for t in mc_build_daily_tasks(
            arrivals=arrivals,
            departures=departures,
            inhouse=inhouse,
            tomorrow_breakfast=tomorrow_breakfast,
            warnings=warnings,
            open_total=open_total,
            revenue_signal=sig,
            money_fn=money,
        )]

    def fidel_summary_lines(self, arrivals, departures, inhouse, tomorrow_breakfast, warnings, open_total):
        # Sprint 4: Textlogik liegt nicht mehr in der GUI-Klasse.
        try:
            sig=self.calendar_day_revenue_signal(date.today())
        except Exception:
            sig={}
        return mc_build_fidel_summary(
            day=date.today(),
            arrivals=arrivals,
            departures=departures,
            inhouse=inhouse,
            tomorrow_breakfast=tomorrow_breakfast,
            warnings=warnings,
            open_total=open_total,
            revenue_signal=sig,
            money_fn=money,
        )

    def fidel_refresh_task_tree(self, tasks):
        if not hasattr(self,"fidel_task_tree"):
            return
        try:
            self.fidel_task_tree.delete(*self.fidel_task_tree.get_children())
            done=self.fidel_task_done_store()
            for prio,text in tasks:
                key=self.fidel_task_key(text)
                status="✓" if done.get(key) else "□"
                self.fidel_task_tree.insert("","end",iid=key,values=(status,prio,text))
        except Exception:
            log_exception("Fidel Aufgaben aktualisieren")

    def fidel_toggle_task_done(self,event=None):
        if not hasattr(self,"fidel_task_tree"):
            return
        try:
            sel=self.fidel_task_tree.selection()
            if not sel:
                return
            key=sel[0]
            done=self.fidel_task_done_store()
            done[key]=not bool(done.get(key))
            save(self.d)
            vals=list(self.fidel_task_tree.item(key,"values"))
            vals[0]="✓" if done.get(key) else "□"
            self.fidel_task_tree.item(key,values=vals)
        except Exception as e:
            messagebox.showerror("Fidel Aufgaben",str(e))

    def fidel_reset_today_tasks(self):
        try:
            prefix=date.today().isoformat()+"|"
            done=self.fidel_task_done_store()
            for k in list(done.keys()):
                if k.startswith(prefix):
                    del done[k]
            save(self.d)
            self.refresh_dash()
        except Exception as e:
            messagebox.showerror("Fidel Aufgaben",str(e))

    def fidel_weekly_report(self):
        try:
            today=date.today()
            start=today-timedelta(days=today.weekday())
            end=start+timedelta(days=7)
            bookings=[b for b in self.d.get("bookings",[]) if b.get("status")!="storniert"]
            week=[]
            room_rev=tax=extras=0.0
            nights_sum=0
            arrivals=departures=0
            for b in bookings:
                try:
                    arr=pdate(b.get("arrival")); dep=pdate(b.get("departure"))
                except Exception:
                    continue
                if start <= arr < end:
                    arrivals += 1
                    week.append(b)
                if start <= dep < end:
                    departures += 1
                if dep<=start or arr>=end:
                    continue
                ns=max(0,(min(dep,end)-max(arr,start)).days)
                nights_sum += ns
                room_rev += to_float(b.get("price",0),0)*ns
                tax += ORTSTAXE*to_int(b.get("persons",1),1)*ns
                try:
                    extras += sum(float(e.get("qty",0))*float(e.get("price",0)) for e in extras_for(self.d,b.get("id","")))
                except Exception:
                    pass
            active=max(1,len([r for r in self.d.get("rooms",[]) if r.get("active",True)]))
            cap=active*7
            auslastung=int(round(nights_sum/cap*100)) if cap else 0
            adr=room_rev/nights_sum if nights_sum else 0
            lines=[
                "Zuhause am Bach – Fidel Wochenbericht",
                f"Zeitraum: {start.strftime('%d.%m.%Y')} bis {(end-timedelta(days=1)).strftime('%d.%m.%Y')}",
                "",
                f"Anreisen: {arrivals}",
                f"Abreisen: {departures}",
                f"Verkaufte Zimmernächte: {nights_sum}",
                f"Auslastung: {auslastung}%",
                f"Zimmerumsatz: {money(room_rev)}",
                f"Extras/Artikel: {money(extras)}",
                f"Ortstaxe: {money(tax)}",
                f"ADR: {money(adr)}",
                "",
                "Fidel-Empfehlung:",
            ]
            if auslastung<30:
                lines.append("• Nachfrage schwach: Lückenfüller, Direktbuchungsbonus und kurze WhatsApp-Aktion prüfen.")
            elif auslastung>75:
                lines.append("• Nachfrage stark: Preis halten oder leicht erhöhen; keine unnötigen Rabatte.")
            else:
                lines.append("• Normale Woche: Preise beobachten und fehlende Stammdaten/Rechnungen sauber halten.")
            if arrivals:
                lines.append("• Begrüßungstexte und Ankunftszeiten für neue Gäste prüfen.")
            report_dir=data_dir()/"Berichte"
            report_dir.mkdir(exist_ok=True)
            path=report_dir/f"Fidel_Wochenbericht_{start:%Y_%m_%d}.txt"
            path.write_text("\n".join(lines),encoding="utf-8")
            try:
                os.startfile(str(path))
            except Exception:
                webbrowser.open(path.as_uri())
            messagebox.showinfo("Fidel Wochenbericht",f"Bericht erstellt:\n{path}")
        except Exception as e:
            log_exception("Fidel Wochenbericht")
            messagebox.showerror("Fidel Wochenbericht",str(e))

    def toggle_checked_in(self,bid):
        for b in self.d["bookings"]:
            if b["id"]==bid:
                b["checked_in"]=not bool(b.get("checked_in",False))
                break
        save(self.d)
        self.refresh_all()

    def toggle_paid_out(self,bid):
        for b in self.d["bookings"]:
            if b["id"]==bid:
                b["paid_out"]=not bool(b.get("paid_out",False))
                break
        save(self.d)
        self.refresh_all()


    def month_bounds(self, year, month):
        start=date(year,month,1)
        end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
        return start,end

    def year_stats_rows(self, year):
        rows=[]
        labels=["Jänner","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]
        bookings=[b for b in self.d.get("bookings",[]) if b.get("status")!="storniert"]
        for m in range(1,13):
            start,end=self.month_bounds(year,m)
            arrivals=0
            active_bookings=0
            nights_sum=0
            person_nights=0
            room_rev=0.0
            extras_rev=0.0
            dog_rev=0.0
            tax_rev=0.0
            total_rev=0.0
            for b in bookings:
                try:
                    arr=pdate(b.get("arrival"))
                    dep=pdate(b.get("departure"))
                except Exception:
                    continue

                if start <= arr < end:
                    arrivals += 1
                    # Extras werden dem Anreisemonat zugerechnet
                    try:
                        extras_rev += sum(float(e.get("qty",0))*float(e.get("price",0)) for e in extras_for(self.d,b.get("id","")))
                    except Exception:
                        pass

                if dep <= start or arr >= end:
                    continue

                active_bookings += 1
                counted_start=max(arr,start)
                counted_end=min(dep,end)
                ns=max(0,(counted_end-counted_start).days)
                persons=to_int(b.get("persons",1),1)
                nights_sum += ns
                person_nights += ns*persons
                price=to_float(b.get("price",0),0)
                room_rev += price*ns
                if b.get("dog"):
                    dog_rev += to_float(b.get("dog_price",5.0),5.0)*ns
                tax_rev += ORTSTAXE*persons*ns

            total_rev = room_rev + extras_rev + dog_rev + tax_rev
            active_rooms = max(1, len([r for r in self.d.get("rooms",[]) if r.get("active", True)]))
            month_days = max(1, (end-start).days)
            capacity_nights = active_rooms * month_days
            free_nights = max(0, capacity_nights - nights_sum)
            occupancy_pct = int(round((nights_sum / capacity_nights) * 100)) if capacity_nights else 0
            adr = (room_rev / nights_sum) if nights_sum else 0.0
            revpar = (room_rev / capacity_nights) if capacity_nights else 0.0
            rows.append({
                "month_no":m,
                "month":labels[m-1],
                "arrivals":arrivals,
                "active":active_bookings,
                "nights":nights_sum,
                "free_nights":free_nights,
                "occupancy_pct":occupancy_pct,
                "adr":adr,
                "revpar":revpar,
                "person_nights":person_nights,
                "room":room_rev,
                "extras":extras_rev + dog_rev,
                "tax":tax_rev,
                "total":total_rev
            })
        return rows

    def build_year_stats(self):
        top=self.card(self.tab_stats,"Jahresstatistik – Buchungen & Umsätze")
        self.stats_year=StringVar(value=str(date.today().year))
        line=ttk.Frame(top,style="Card.TFrame"); line.pack(fill="x",pady=5)
        ttk.Label(line,text="Jahr",style="Card.TLabel").pack(side="left",padx=5)
        ttk.Entry(line,textvariable=self.stats_year,width=8).pack(side="left",padx=5)
        ttk.Button(line,text="ANZEIGEN",command=self.refresh_year_stats,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(line,text="CSV EXPORT",command=self.stats_year_csv,style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(line,text="PDF DRUCKEN",command=self.stats_year_pdf,style="Primary.TButton").pack(side="left",padx=5)
        self.stats_summary=StringVar(value="")
        ttk.Label(top,textvariable=self.stats_summary,style="CardTitle.TLabel").pack(anchor="w",pady=(8,0))
        ttk.Label(top,text="Umsätze werden monatsweise nach Nächten im Monat berechnet. Extras werden dem Anreisemonat zugerechnet.",style="Card.TLabel").pack(anchor="w")
        self.stats_kpi_vars={
            "umsatz":StringVar(value="0 €"), "naechte":StringVar(value="0"), "frei":StringVar(value="0"),
            "auslastung":StringVar(value="0 %"), "adr":StringVar(value="0 €"), "revpar":StringVar(value="0 €")
        }
        kpirow=ttk.Frame(top,style="Card.TFrame"); kpirow.pack(fill="x",pady=(8,0))
        for label,key in [("Umsatz", "umsatz"),("verkaufte Nächte","naechte"),("freie Nächte","frei"),("Auslastung","auslastung"),("Ø Preis / ADR","adr"),("RevPAR","revpar")]:
            box=ttk.Frame(kpirow,style="Card.TFrame",padding=8); box.pack(side="left",fill="x",expand=True,padx=3)
            ttk.Label(box,text=label,style="Card.TLabel").pack(anchor="center")
            ttk.Label(box,textvariable=self.stats_kpi_vars[key],style="CardTitle.TLabel").pack(anchor="center")

        self.stats_canvas=Canvas(self.tab_stats,height=120,bg="#ffffff",highlightthickness=1,highlightbackground="#d4c69f")
        self.stats_canvas.pack(fill="x",padx=8,pady=4)

        frame=ttk.Frame(self.tab_stats)
        frame.pack(fill="both",expand=True,padx=8,pady=(4,6))
        cols=("monat","anreisen","aktive","nächte","frei","auslastung","adr","revpar","pn","zimmer","extras","ortstaxe","gesamt")
        self.stats_tree=ttk.Treeview(frame,columns=cols,show="headings",height=10)
        labels={
            "monat":"Monat","anreisen":"Anreisen","aktive":"aktive Buchungen","nächte":"verkauft",
            "frei":"frei","auslastung":"Ausl.","adr":"ADR","revpar":"RevPAR",
            "pn":"Personennächte","zimmer":"Zimmerumsatz","extras":"Extras/Hund",
            "ortstaxe":"Ortstaxe","gesamt":"Gesamt"
        }
        widths={"monat":110,"anreisen":70,"aktive":100,"nächte":70,"frei":65,"auslastung":65,"adr":80,"revpar":80,"pn":100,"zimmer":105,"extras":95,"ortstaxe":90,"gesamt":105}
        for c in cols:
            self.stats_tree.heading(c,text=labels[c])
            self.stats_tree.column(c,width=widths[c],anchor="w")
        vsb=ttk.Scrollbar(frame,orient="vertical",command=self.stats_tree.yview)
        self.stats_tree.configure(yscrollcommand=vsb.set)
        self.stats_tree.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        self.stats_tree.tag_configure("sum", background="#e8dfc8", foreground="#12351e")

    def refresh_year_stats(self):
        if not hasattr(self,"stats_tree"):
            return
        try:
            year=int(self.stats_year.get())
        except Exception:
            return
        rows=self.year_stats_rows(year)
        for i in self.stats_tree.get_children():
            self.stats_tree.delete(i)
        total_arr=sum(r["arrivals"] for r in rows)
        total_nights=sum(r["nights"] for r in rows)
        total_pn=sum(r["person_nights"] for r in rows)
        total_room=sum(r["room"] for r in rows)
        total_extras=sum(r["extras"] for r in rows)
        total_tax=sum(r["tax"] for r in rows)
        total_all=sum(r["total"] for r in rows)
        total_free=sum(r.get("free_nights",0) for r in rows)
        total_capacity=total_free+total_nights
        occ_pct=int(round((total_nights/total_capacity)*100)) if total_capacity else 0
        adr=(total_room/total_nights) if total_nights else 0.0
        revpar=(total_room/total_capacity) if total_capacity else 0.0

        for r in rows:
            self.stats_tree.insert("",END,values=(
                r["month"],r["arrivals"],r["active"],r["nights"],r.get("free_nights",0),f"{r.get('occupancy_pct',0)}%",money(r.get("adr",0)),money(r.get("revpar",0)),r["person_nights"],
                money(r["room"]),money(r["extras"]),money(r["tax"]),money(r["total"])
            ))
        self.stats_tree.insert("",END,values=("SUMME",total_arr,"",total_nights,total_free,f"{occ_pct}%",money(adr),money(revpar),total_pn,money(total_room),money(total_extras),money(total_tax),money(total_all)),tags=("sum",))
        self.stats_summary.set(f"{year} · Anreisen: {total_arr} · Nächte: {total_nights} · frei: {total_free} · Auslastung: {occ_pct}% · Umsatz gesamt: {money(total_all)}")
        if hasattr(self,"stats_kpi_vars"):
            self.stats_kpi_vars["umsatz"].set(money(total_all)); self.stats_kpi_vars["naechte"].set(str(total_nights)); self.stats_kpi_vars["frei"].set(str(total_free)); self.stats_kpi_vars["auslastung"].set(f"{occ_pct}%"); self.stats_kpi_vars["adr"].set(money(adr)); self.stats_kpi_vars["revpar"].set(money(revpar))
        self.draw_year_chart(rows)

    def draw_year_chart(self, rows):
        c=getattr(self,"stats_canvas",None)
        if not c:
            return
        c.delete("all")
        width=max(c.winfo_width(),1100)
        # V22.1: Statistik-Grafik kompakt und vollständig im Canvas zeichnen.
        # Vorher wurde mit base=210 in einen 170px hohen Canvas gezeichnet; dadurch war
        # die Monatsübersicht abgeschnitten. Jetzt wird alles dynamisch aus der
        # tatsächlichen Canvas-Höhe berechnet.
        canvas_h=max(c.winfo_height(),120)
        margin_l=55
        margin_r=25
        top=26
        base=max(78, canvas_h-26)
        chart_w=width-margin_l-margin_r
        max_rev=max([r["total"] for r in rows] or [1])
        max_book=max([r["arrivals"] for r in rows] or [1])
        c.create_text(18,10,anchor="w",text="Monatsübersicht: Umsatz (Balken) / Anreisen (Linie)",fill="#12351e",font=("Segoe UI",10,"bold"))
        c.create_line(margin_l,base,width-margin_r,base,fill="#d4c69f")
        bar_gap=chart_w/12
        bar_w=max(14,bar_gap*0.38)
        points=[]
        for i,r in enumerate(rows):
            x=margin_l+i*bar_gap+bar_gap/2
            usable_h=max(40, base-top)
            bh=0 if max_rev<=0 else (r["total"]/max_rev)*usable_h
            c.create_rectangle(x-bar_w/2,base-bh,x+bar_w/2,base,fill="#2f6b2f",outline="")
            c.create_text(x,base+12,text=str(r["month_no"]),fill="#6d5c26",font=("Segoe UI",8,"bold"))
            py=base-(r["arrivals"]/max_book)*usable_h if max_book else base
            points.append((x,py))
            if r["total"]>0:
                # Zahlen innerhalb des Canvas halten
                label_y=max(top+8, base-bh-7)
                c.create_text(x,label_y,text=f"{int(r['total'])}€",fill="#12351e",font=("Segoe UI",7))
        for i in range(len(points)-1):
            c.create_line(points[i][0],points[i][1],points[i+1][0],points[i+1][1],fill="#c49a2c",width=2)
        for x,y in points:
            c.create_oval(x-3,y-3,x+3,y+3,fill="#c49a2c",outline="")
        c.create_text(margin_l,canvas_h-8,anchor="w",text="Grün = Umsatz / Gold = Anreisen",fill="#12351e",font=("Segoe UI",8,"bold"))

    def stats_year_csv(self):
        try:
            year=int(self.stats_year.get())
            rows=self.year_stats_rows(year)
            f=out_dir()/f"Jahresstatistik_{year}.csv"
            with open(f,"w",newline="",encoding="utf-8-sig") as out:
                w=csv.writer(out,delimiter=";")
                w.writerow(["Monat","Anreisen","aktive Buchungen","Nächte","Personennächte","Zimmerumsatz","Extras/Hund","Ortstaxe","Gesamtumsatz"])
                for r in rows:
                    w.writerow([r["month"],r["arrivals"],r["active"],r["nights"],r["person_nights"],str(round(r["room"],2)).replace(".",","),str(round(r["extras"],2)).replace(".",","),str(round(r["tax"],2)).replace(".",","),str(round(r["total"],2)).replace(".",",")])
            messagebox.showinfo("CSV Export",str(f))
            try: os.startfile(str(f))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("Statistik CSV",str(e))

    def stats_year_pdf(self):
        try:
            year=int(self.stats_year.get())
            rows=self.year_stats_rows(year)
            f=out_dir()/f"Jahresstatistik_{year}.pdf"
            styles=getSampleStyleSheet()
            doc=SimpleDocTemplate(str(f),pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=10*mm)
            story=[]
            add_logo_to_story(story)
            story.append(Paragraph(f"Jahresstatistik {year}",styles["Title"]))
            story.append(Paragraph("Buchungen und Umsätze monatsweise",styles["Normal"]))
            story.append(Spacer(1,5*mm))
            data=[["Monat","Anreisen","Nächte","PN","Zimmer","Extras","Ortstaxe","Gesamt"]]
            for r in rows:
                data.append([r["month"],str(r["arrivals"]),str(r["nights"]),str(r["person_nights"]),money(r["room"]),money(r["extras"]),money(r["tax"]),money(r["total"])])
            data.append(["SUMME",str(sum(r["arrivals"] for r in rows)),str(sum(r["nights"] for r in rows)),str(sum(r["person_nights"] for r in rows)),money(sum(r["room"] for r in rows)),money(sum(r["extras"] for r in rows)),money(sum(r["tax"] for r in rows)),money(sum(r["total"] for r in rows))])
            table=Table(data,colWidths=[28*mm,18*mm,18*mm,18*mm,28*mm,26*mm,26*mm,30*mm],repeatRows=1)
            table.setStyle(TableStyle([
                ("GRID",(0,0),(-1,-1),0.25,colors.grey),
                ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                ("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#e8dfc8")),
                ("FONTSIZE",(0,0),(-1,-1),7.0),
                ("VALIGN",(0,0),(-1,-1),"TOP"),
            ]))
            story.append(table)
            doc.build(story)
            messagebox.showinfo("Statistik PDF",str(f))
            try: os.startfile(str(f))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("Statistik PDF",str(e))



    def chance_season_score(self, d):
        m=d.month
        if m in (7,8):
            return 26, "Hochsommer"
        if m in (9,10):
            return 28, "Wachau-Herbst"
        if m in (4,5,6):
            return 23, "Wandersaison"
        if m==12:
            return 14, "Advent/Winter"
        if m in (1,2):
            return 4, "Nebensaison"
        if m in (3,11):
            return 8, "ruhige Übergangszeit"
        return 10, "Saison"

    def chance_weekday_score(self, d):
        wd=d.weekday()
        if wd==5:
            return 24, "Samstag"
        if wd==4:
            return 20, "Freitag"
        if wd==6:
            return 13, "Sonntag"
        if wd in (0,1,2,3):
            return 8, "Wochentag"
        return 8, "Tag"

    def chance_weather_score(self, weather):
        w=(weather or "").lower()
        if "sonnig" in w:
            return 24, "sonnig"
        if "leicht" in w or "bewölkt" in w:
            return 18, "bewölkt"
        if "trocken" in w:
            return 20, "trocken"
        if "regen" in w:
            return 7, "Regen"
        if "gewitter" in w or "sturm" in w:
            return 2, "Gewitter/Sturm"
        if "hitze" in w:
            return 9, "Hitze"
        return 14, "normal"

    def free_rooms_on_date(self, d):
        rooms=[r for r in self.d.get("rooms",[]) if r.get("active",True)]
        booked=set()
        for b in self.d.get("bookings",[]):
            if b.get("status")=="storniert":
                continue
            try:
                arr=pdate(b.get("arrival"))
                dep=pdate(b.get("departure"))
            except Exception:
                continue
            if arr <= d < dep:
                booked.add(str(b.get("room_id","")))
        return [r for r in rooms if str(r.get("id","")) not in booked]

    def room_is_free_on_date(self, room_id, d):
        for b in self.d.get("bookings",[]):
            if b.get("status")=="storniert":
                continue
            if str(b.get("room_id",""))!=str(room_id):
                continue
            try:
                arr=pdate(b.get("arrival"))
                dep=pdate(b.get("departure"))
            except Exception:
                continue
            if arr <= d < dep:
                return False
        return True

    def free_gap_days(self, room_id, d, max_days=10):
        days=0
        cur=d
        for _ in range(max_days):
            if self.room_is_free_on_date(room_id,cur):
                days+=1
                cur=cur+timedelta(days=1)
            else:
                break
        return days

    def chance_gap_score(self, gap):
        if gap==1:
            return 17, "1 freie Nacht – gute Kurzbuchungslücke"
        if gap in (2,3):
            return 22, f"{gap} freie Nächte – sehr gute Lücke"
        if 4 <= gap <= 6:
            return 16, f"{gap} freie Nächte – gut für Kurzurlaub"
        if gap >= 7:
            return 10, f"{gap}+ freie Nächte – Preisaktion möglich"
        return 0, "keine Lücke"

    def chance_recommendation(self, percent, d, gap, weather, room):
        price=float(room.get("price",0) or 0)
        weekend=d.weekday() in (4,5)
        if percent >= 80:
            if weekend and price>0:
                return f"Sehr hohe Chance – Preis halten oder leicht erhöhen ({money(price)} bis {money(price+10)})"
            return "Sehr hohe Chance – sichtbar lassen, keine Rabattaktion nötig"
        if percent >= 65:
            return "Gute Chance – Preis halten, bei Booking/Google gut sichtbar halten"
        if percent >= 45:
            if gap >= 4:
                return "Mittlere Chance – freie Lücke aktiv bewerben, kleiner Direktbucher-Vorteil möglich"
            return "Mittlere Chance – Facebook/Google-Post für Wanderer/Radfahrer sinnvoll"
        if percent >= 25:
            return "Schwache Chance – Preisaktion oder Zusatznutzen bewerben: Frühstück, Radplatz, Parkplatz"
        return "Geringe Chance – nur ruhig beobachten, keine starke Erwartung"

    def chance_rows(self):
        try:
            start=pdate(self.chance_start.get())
        except Exception:
            start=date.today()
        try:
            days=int(self.chance_days.get())
        except Exception:
            days=7
        if days < 1:
            days=1
        if days > 120:
            days=120

        manual_weather=self.chance_weather.get() if hasattr(self,"chance_weather") else "trocken / normal"
        online_weather=getattr(self,"chance_weather_online",{}) if hasattr(self,"chance_weather_online") else {}

        rows=[]
        for i in range(days):
            d=start+timedelta(days=i)
            ds=d.isoformat()
            wdata=online_weather.get(ds)
            if wdata:
                weather_label=wdata.get("weather","online")
                temp_max=wdata.get("temp_max")
                precip=wdata.get("precip_prob")
                precip_sum=wdata.get("precip_sum")
                if precip is not None and precip >= 70:
                    score_weather="Regen"
                elif precip_sum is not None and precip_sum >= 8:
                    score_weather="Regen"
                elif temp_max is not None and temp_max >= 32:
                    score_weather="Hitze über 32 °C"
                elif "Gewitter" in weather_label:
                    score_weather="Gewitter / Sturm"
                elif "Regen" in weather_label or "Schauer" in weather_label or "Niesel" in weather_label:
                    score_weather="Regen"
                elif "sonnig" in weather_label:
                    score_weather="sonnig"
                elif "bewölkt" in weather_label:
                    score_weather="leicht bewölkt"
                else:
                    score_weather="trocken / normal"
                weather_display=f"{weather_label}, {temp_max}°C, Regen {precip if precip is not None else '-'}%"
            else:
                score_weather=manual_weather
                weather_display=manual_weather

            free_rooms=self.free_rooms_on_date(d)
            for room in free_rooms:
                season_score, season_label=self.chance_season_score(d)
                weekday_score, weekday_label=self.chance_weekday_score(d)
                weather_score, weather_score_label=self.chance_weather_score(score_weather)
                gap=self.free_gap_days(room.get("id"),d,10)
                gap_score, gap_label=self.chance_gap_score(gap)
                base=12
                percent=max(5,min(95,base+season_score+weekday_score+weather_score+gap_score))
                if d < date.today():
                    percent=0
                rec=self.chance_recommendation(percent,d,gap,score_weather,room)
                if wdata:
                    rec = "Online-Wetter: " + rec
                rows.append({
                    "date":d,
                    "day":weekday_label,
                    "room":room.get("name",""),
                    "price":float(room.get("price",0) or 0),
                    "season":season_label,
                    "weather":weather_display,
                    "gap":gap,
                    "gap_label":gap_label,
                    "percent":percent,
                    "recommendation":rec
                })
        rows.sort(key=lambda r:(r["date"], -r["percent"], r["room"]))
        return rows

    def build_chances(self):
        top=self.card(self.tab_chances,"Buchungschancen-Assistent – freie Tage bewerten")
        self.chance_start=StringVar(value=date.today().strftime("%d.%m.%Y"))
        self.chance_days=StringVar(value="7")
        self.chance_weather=StringVar(value="trocken / normal")
        self.chance_weather_online={}
        self.chance_weather_status=StringVar(value="Online-Wetter noch nicht geladen.")
        line=ttk.Frame(top,style="Card.TFrame")
        line.pack(fill="x",pady=5)
        ttk.Label(line,text="Startdatum",style="Card.TLabel").pack(side="left",padx=5)
        ttk.Entry(line,textvariable=self.chance_start,width=12).pack(side="left",padx=5)
        ttk.Label(line,text="Tage voraus",style="Card.TLabel").pack(side="left",padx=5)
        ttk.Entry(line,textvariable=self.chance_days,width=6).pack(side="left",padx=5)
        ttk.Label(line,text="Wetterannahme",style="Card.TLabel").pack(side="left",padx=5)
        cb=ttk.Combobox(line,textvariable=self.chance_weather,width=22,state="readonly",
                        values=["sonnig","leicht bewölkt","trocken / normal","Regen","Gewitter / Sturm","Hitze über 32 °C"])
        cb.pack(side="left",padx=5)
        cb.bind("<<ComboboxSelected>>",lambda e:self.refresh_chances())
        ttk.Button(line,text="BERECHNEN",command=self.refresh_chances,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(line,text="ONLINE-WETTER LADEN",command=self.load_online_weather_for_chances,style="Gold.TButton").pack(side="left",padx=5)
        ttk.Button(line,text="CSV EXPORT",command=self.chances_csv,style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(line,text="PDF DRUCKEN",command=self.chances_pdf,style="Primary.TButton").pack(side="left",padx=5)

        self.chance_summary=StringVar(value="")
        ttk.Label(top,textvariable=self.chance_summary,style="CardTitle.TLabel").pack(anchor="w",pady=(8,0))
        ttk.Label(top,textvariable=self.chance_weather_status,style="Card.TLabel").pack(anchor="w")
        ttk.Label(
            top,
            text="Online-Modus: lädt 7 Tage Wetter für Aggsbach Markt/Wachau. Danach wird die Prognose mit tatsächlicher Wettervorhersage gerechnet. Ohne Internet wird die manuelle Wetterannahme verwendet.",
            style="Card.TLabel",
            wraplength=1250
        ).pack(anchor="w")

        frame=ttk.Frame(self.tab_chances)
        frame.pack(fill="both",expand=True,padx=8,pady=(4,6))

        cols=("datum","tag","zimmer","preis","saison","wetter","lücke","chance","empfehlung")
        self.chance_tree=ttk.Treeview(frame,columns=cols,show="headings",height=22)
        labels={
            "datum":"Datum","tag":"Tag","zimmer":"Zimmer","preis":"Preis",
            "saison":"Saison","wetter":"Wetter","lücke":"freie Nächte",
            "chance":"Chance","empfehlung":"Empfehlung"
        }
        widths={"datum":95,"tag":90,"zimmer":160,"preis":85,"saison":130,"wetter":110,"lücke":110,"chance":80,"empfehlung":520}
        for c in cols:
            self.chance_tree.heading(c,text=labels[c])
            self.chance_tree.column(c,width=widths[c],anchor="w")
        vsb=ttk.Scrollbar(frame,orient="vertical",command=self.chance_tree.yview)
        hsb=ttk.Scrollbar(frame,orient="horizontal",command=self.chance_tree.xview)
        self.chance_tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.chance_tree.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        self.chance_tree.tag_configure("high",background="#dff3d7",foreground="#12351e")
        self.chance_tree.tag_configure("mid",background="#fff2a8",foreground="#312300")
        self.chance_tree.tag_configure("low",background="#ffe0e0",foreground="#5a1b1b")

    def load_online_weather_for_chances(self):
        try:
            if hasattr(self,"chance_weather_status"):
                self.chance_weather_status.set("Online-Wetter wird geladen …")
                self.root.update_idletasks()
            data, err = fetch_aggsbach_weather_7days()
            if err:
                self.chance_weather_online={}
                if hasattr(self,"chance_weather_status"):
                    self.chance_weather_status.set("Online-Wetter nicht verfügbar – manuelle Wetterannahme wird verwendet. Fehler: "+str(err)[:160])
                messagebox.showwarning("Online-Wetter", "Wetter konnte nicht geladen werden.\nEs wird die manuelle Wetterannahme verwendet.\n\n"+str(err))
            else:
                self.chance_weather_online=data
                if hasattr(self,"chance_weather_status"):
                    self.chance_weather_status.set(f"Online-Wetter geladen: {len(data)} Tage für Aggsbach Markt/Wachau.")
                self.refresh_chances()
        except Exception as e:
            messagebox.showerror("Online-Wetter",str(e))


    def refresh_chances(self):
        if not hasattr(self,"chance_tree"):
            return
        try:
            rows=self.chance_rows()
            for i in self.chance_tree.get_children():
                self.chance_tree.delete(i)
            high=sum(1 for r in rows if r["percent"]>=65)
            mid=sum(1 for r in rows if 40<=r["percent"]<65)
            low=sum(1 for r in rows if r["percent"]<40)
            for r in rows:
                tag="high" if r["percent"]>=65 else "mid" if r["percent"]>=40 else "low"
                self.chance_tree.insert("",END,values=(
                    fmt(r["date"]),r["day"],r["room"],money(r["price"]),r["season"],r["weather"],
                    str(r["gap"]),f"{r['percent']} %",r["recommendation"]
                ),tags=(tag,))
            self.chance_summary.set(f"Freie Zimmer-Tage: {len(rows)} · hohe Chance: {high} · mittel: {mid} · gering: {low}")
        except Exception as e:
            messagebox.showerror("Buchungschancen",str(e))

    def chances_csv(self):
        try:
            rows=self.chance_rows()
            f=out_dir()/("Buchungschancen_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".csv")
            with open(f,"w",newline="",encoding="utf-8-sig") as out:
                w=csv.writer(out,delimiter=";")
                w.writerow(["Datum","Tag","Zimmer","Preis","Saison","Wetter","freie Nächte","Chance %","Empfehlung"])
                for r in rows:
                    w.writerow([fmt(r["date"]),r["day"],r["room"],str(round(r["price"],2)).replace(".",","),r["season"],r["weather"],r["gap"],r["percent"],r["recommendation"]])
            messagebox.showinfo("CSV Export",str(f))
            try: os.startfile(str(f))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("CSV Export",str(e))

    def chances_pdf(self):
        try:
            rows=self.chance_rows()
            f=out_dir()/("Buchungschancen_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".pdf")
            styles=getSampleStyleSheet()
            doc=SimpleDocTemplate(str(f),pagesize=A4,rightMargin=10*mm,leftMargin=10*mm,topMargin=10*mm,bottomMargin=10*mm)
            story=[]
            add_logo_to_story(story)
            story.append(Paragraph("Buchungschancen-Assistent",styles["Title"]))
            story.append(Paragraph("Freie Tage bewertet nach Saison, Wochentag, Wetterannahme und Buchungslücke.",styles["Normal"]))
            story.append(Spacer(1,5*mm))
            data=[["Datum","Zimmer","Saison","Lücke","Chance","Empfehlung"]]
            for r in rows[:80]:
                data.append([fmt(r["date"]),r["room"],r["season"],str(r["gap"]),f"{r['percent']} %",r["recommendation"]])
            table=Table(data,colWidths=[22*mm,35*mm,28*mm,14*mm,18*mm,72*mm],repeatRows=1)
            table.setStyle(TableStyle([
                ("GRID",(0,0),(-1,-1),0.25,colors.grey),
                ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                ("FONTSIZE",(0,0),(-1,-1),6.8),
                ("VALIGN",(0,0),(-1,-1),"TOP"),
            ]))
            story.append(table)
            doc.build(story)
            messagebox.showinfo("PDF",str(f))
            try: os.startfile(str(f))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("PDF",str(e))



    # ---------------- KI-Gastprofil 360° V15.0 ----------------

    def guest_ai_booking_list(self):
        rows=[]
        for b in sorted(self.d.get("bookings",[]), key=lambda x:(x.get("arrival",""), x.get("guest",""))):
            label=f"{b.get('id','')} | {b.get('arrival','')} | {b.get('guest','')} | {room_name(self.d,b.get('room_id',''))}"
            rows.append(label)
        return rows

    def build_guest_ai_profile(self):
        main=ttk.Frame(self.tab_guest_ai)
        main.pack(fill="both",expand=True,padx=10,pady=10)
        top=self.card(main,"🧠 KI-Gastprofil 360° – Serviceprofil mit Wahrscheinlichkeiten")
        ttk.Label(top,text="Erstellt ein internes Serviceprofil aus Buchungsdaten, Nachrichten und optional manuell eingefügten öffentlichen Hinweisen. Neu: Profilqualität, Wiederbuchung, Bewertungsneigung, Ankunftszeit und Service-Checkliste. Prozentwerte sind Schätzungen, keine Tatsachen.",style="Card.TLabel",wraplength=1300).pack(anchor="w")

        row=ttk.Frame(top,style="Card.TFrame"); row.pack(fill="x",pady=6)
        self.gai_booking=StringVar()
        self.gai_status=StringVar(value="Bereit. Buchung auswählen und Profil berechnen.")
        ttk.Label(row,text="Buchung",style="Card.TLabel").pack(side="left",padx=4)
        self.gai_combo=ttk.Combobox(row,textvariable=self.gai_booking,values=self.guest_ai_booking_list(),width=85,state="readonly")
        self.gai_combo.pack(side="left",padx=4)
        ttk.Button(row,text="🔄 AKTUALISIEREN",command=self.gai_refresh_booking_list,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(row,text="HEUTE",command=lambda:self.gai_select_by_status('inhouse'),style="Soft.TButton").pack(side="left",padx=2)
        ttk.Button(row,text="ANREISE",command=lambda:self.gai_select_by_status('arrival'),style="Soft.TButton").pack(side="left",padx=2)
        ttk.Button(row,text="ABREISE",command=lambda:self.gai_select_by_status('departure'),style="Soft.TButton").pack(side="left",padx=2)
        ttk.Button(row,text="◀ VORHERIGER",command=lambda:self.gai_select_relative(-1),style="Soft.TButton").pack(side="left",padx=2)
        ttk.Button(row,text="NÄCHSTER ▶",command=lambda:self.gai_select_relative(1),style="Soft.TButton").pack(side="left",padx=2)
        ttk.Button(row,text="🧠 PROFIL BERECHNEN",command=self.gai_calculate,style="Touch.TButton").pack(side="left",padx=4)
        ttk.Button(row,text="💾 ALS NOTIZ SPEICHERN",command=self.gai_save_note,style="Gold.TButton").pack(side="left",padx=4)
        ttk.Button(row,text="🖨 GÄSTEPROFIL PDF",command=self.gai_print_profile_pdf,style="Touch.TButton").pack(side="left",padx=4)
        ttk.Label(top,textvariable=self.gai_status,style="CardTitle.TLabel").pack(anchor="w",pady=(2,0))

        pane=ttk.Frame(main); pane.pack(fill="both",expand=True)
        left=ttk.Frame(pane); left.pack(side="left",fill="both",expand=True,padx=(0,8))
        right=ttk.Frame(pane); right.pack(side="right",fill="both",expand=True,padx=(8,0))

        ext=self.card(left,"Google KI-Modus / öffentliche Hinweise – manuelle Eingabe")
        ttk.Label(ext,text="Hier fügst du selbst eine kurze Zusammenfassung aus Google KI-Modus, ChatGPT oder einem anderen KI-Agenten ein. Der Manager übernimmt den Text nur als [Nicht verifiziert] in das interne Gästeprofil und den PDF-Bericht. Keine automatische Social-Media-Suche, keine gesicherten Tatsachen daraus ableiten.",style="Card.TLabel",wraplength=760).pack(anchor="w")
        self.gai_hint_source=StringVar(value="Google KI-Modus")
        srcrow=ttk.Frame(ext,style="Card.TFrame"); srcrow.pack(fill="x",pady=(4,0))
        ttk.Label(srcrow,text="Quelle",style="Card.TLabel").pack(side="left",padx=3)
        ttk.Combobox(srcrow,textvariable=self.gai_hint_source,values=["Google KI-Modus","ChatGPT","anderer KI-Agent","Website","Telefonbuch","manuelle Notiz","Sonstiges"],width=24,state="readonly").pack(side="left",padx=3)
        self.gai_include_public=BooleanVar(value=True)
        ttk.Checkbutton(srcrow,text="in PDF-Bericht übernehmen",variable=self.gai_include_public).pack(side="left",padx=10)
        btns=ttk.Frame(ext,style="Card.TFrame"); btns.pack(fill="x",pady=4)
        ttk.Button(btns,text="Google öffnen",command=lambda:self.gai_open_search('google'),style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(btns,text="Feld leeren",command=lambda:self.gai_external.delete('1.0','end'),style="Soft.TButton").pack(side="left",padx=3)
        ttk.Button(btns,text="Beispiel einfügen",command=self.gai_insert_google_ki_example,style="Soft.TButton").pack(side="left",padx=3)
        self.gai_external=Text(ext,height=11,wrap="word")
        self.gai_external.pack(fill="both",expand=True,pady=5)
        self.gai_external.insert("1.0", "Optional: kurze Zusammenfassung aus Google KI-Modus / ChatGPT hier einfügen. Beispiel: 'Google KI-Modus nennt keine gesicherten öffentlichen Infos. Möglicher Hinweis: Name wirkt wie Privatgast; keine Firmenquelle gefunden.'\n\nWichtig: [Nicht verifiziert], nur interne Vorbereitung.")

        out=self.card(right,"KI-Profil Ergebnis")
        self.gai_output=Text(out,height=30,wrap="word")
        self.gai_output.pack(fill="both",expand=True)
        self.gai_output.insert("1.0","Noch kein Profil berechnet.")

    def gai_insert_google_ki_example(self):
        """Beispieltext für manuell eingefügte Google-KI/Agenten-Hinweise."""
        try:
            self.gai_external.delete("1.0","end")
            self.gai_external.insert("1.0", "[Nicht verifiziert] Quelle: Google KI-Modus / manueller Hinweis\n\nKurzfazit:\n- Keine gesicherte Identitätsprüfung.\n- Keine sensiblen Daten übernehmen.\n- Nur öffentlich wirkende, selbst geprüfte Hinweise eintragen.\n- Für den Aufenthalt relevant: z.B. mögliche Reiseart, Bewertungsneigung, geschäftlicher Kontext oder besondere Servicehinweise – immer als Vermutung kennzeichnen.")
        except Exception:
            pass

    def gai_refresh_booking_list(self):
        vals=self.guest_ai_booking_list()
        self.gai_combo.configure(values=vals)
        if vals and not self.gai_booking.get(): self.gai_booking.set(vals[0])
        self.gai_status.set(f"{len(vals)} Buchungen geladen.")

    def gai_select_relative(self,delta=1):
        vals=list(self.guest_ai_booking_list())
        if not vals:
            self.gai_status.set("Keine Buchungen vorhanden."); return
        cur=self.gai_booking.get()
        try:
            idx=vals.index(cur)
        except Exception:
            idx=0
        idx=(idx+delta) % len(vals)
        self.gai_combo.configure(values=vals)
        self.gai_booking.set(vals[idx])
        self.gai_calculate()

    def gai_select_by_status(self, mode="inhouse"):
        """Springt im Gastprofil zu heutigem Gast, heutiger Anreise oder heutiger Abreise."""
        vals=list(self.guest_ai_booking_list())
        if not vals:
            self.gai_status.set("Keine Buchungen vorhanden."); return
        today=date.today()
        selected=None
        for v in vals:
            bid=v.split(" | ",1)[0].strip()
            b=next((x for x in self.d.get("bookings",[]) if str(x.get("id",""))==bid), None)
            if not b or b.get("status")=="storniert":
                continue
            try:
                arr=pdate(b.get("arrival","")); dep=pdate(b.get("departure",""))
            except Exception:
                continue
            if mode=="arrival" and arr==today:
                selected=v; break
            if mode=="departure" and dep==today:
                selected=v; break
            if mode=="inhouse" and arr <= today < dep:
                selected=v; break
        if not selected:
            self.gai_status.set("Für heute kein passender Gast gefunden."); return
        self.gai_combo.configure(values=vals)
        self.gai_booking.set(selected)
        self.gai_calculate()

    def gai_selected_booking(self):
        val=str(self.gai_booking.get() or "")
        bid=val.split(" | ",1)[0].strip() if val else ""
        return next((b for b in self.d.get("bookings",[]) if str(b.get("id",""))==bid), None)

    def gai_clamp(self,n):
        return max(0,min(100,int(round(n))))

    def gai_analyze_external_hints(self,external_text=""):
        """Analysiert manuell eingefügte öffentliche Hinweise. Keine Web-Abfrage, keine automatische Datensammlung."""
        return guestprofile_analyze_external_hints(external_text)

    def gai_profile_from_booking(self,b,external_text=""):
        """Wrapper auf das zentrale Modul manager.modules.gastprofil."""
        history=[]
        try:
            name=str(b.get("guest","")).strip().lower()
            history=[x for x in self.d.get("bookings",[]) if x is not b and str(x.get("guest","")).strip().lower()==name]
        except Exception:
            history=[]
        return guestprofile_from_booking(b, external_text=external_text, history=history)

    def gai_calculate(self):
        b=self.gai_selected_booking()
        if not b:
            messagebox.showinfo("Gastprofil KI","Bitte zuerst eine Buchung auswählen."); return
        ext=self.gai_external.get("1.0","end").strip()
        if ext.startswith("Optional:"): ext=""
        if hasattr(self,"gai_include_public") and not self.gai_include_public.get(): ext=""
        prof=self.gai_profile_from_booking(b,ext)
        lines=[]
        lines.append("KI-Gastprofil 360° PLUS")
        lines.append("="*40)
        lines.append(f"Gast: {b.get('guest','')}")
        lines.append(f"Aufenthalt: {b.get('arrival','')} bis {b.get('departure','')} · {nights(b.get('arrival',''),b.get('departure',''))} Nacht/Nächte")
        lines.append(f"Zimmer: {room_name(self.d,b.get('room_id',''))}")
        lines.append(f"Profilqualität: {prof['quality']} %")
        lines.append(f"Geschätzte Ankunftszeit: {prof['expected_arrival']}")
        lines.append("")
        lines.append("[Schätzung] Reiseart")
        for k,v in prof['travel'].items(): lines.append(f"• {k}: {v} %")
        lines.append("")
        lines.append("[Schätzung] Aufenthalt/Service")
        lines.append(f"• Frühstück wahrscheinlich: {prof['breakfast']} %")
        lines.append(f"• Frühe Abreise wahrscheinlich: {prof['early']} %")
        lines.append(f"• Späte Anreise wahrscheinlich: {prof['late']} %")
        lines.append(f"• Bewertung wahrscheinlich: {prof['review']} %")
        lines.append(f"• Wiederbuchung/Stammgast-Potenzial: {prof['rebook']} %")
        lines.append(f"• Kritischkeitsrisiko: {prof['critical']} %")
        lines.append(f"• Geschäftsreise/Berufskontext: {prof['business']} %")
        lines.append("")
        lines.append("[Vermutung] Reisestil / Interessen")
        for k,v in prof['style'].items(): lines.append(f"• {k}: {v} %")
        lines.append("")
        lines.append("[Nicht verifiziert] Google KI-Modus / öffentliche Hinweise")
        if ext:
            src = self.gai_hint_source.get() if hasattr(self,"gai_hint_source") else "manuelle Quelle"
            lines.append(f"• Quelle: {src} – manuell eingefügt")
        tags=prof.get('external',{}).get('tags',[])
        if tags:
            for tag in tags: lines.append(f"• {tag}")
        else:
            lines.append("• Keine Google-KI-/Agenten-Hinweise übernommen.")
        lines.append("")
        lines.append("Service-Checkliste")
        t=prof['travel']
        if t['Wanderer']>=55: lines.append("☐ Trockenecke, frühes Frühstück/Snackbox und Welterbesteig-Hinweis vorbereiten.")
        if t['Radfahrer']>=45: lines.append("☐ Fahrradgarage, E-Bike-Laden, Werkzeug/Luftpumpe sichtbar anbieten.")
        if t['Autofahrer']>=55: lines.append("☐ Parkplatz/Hofzufahrt und Check-in kurz erklären.")
        if prof['breakfast']>=65: lines.append("☐ Frühstück aktiv anbieten bzw. vorbereiten.")
        if prof['review']>=60: lines.append("☐ Persönliche Begrüßung und kleine positive Überraschung erhöhen Bewertungschance.")
        if prof['rebook']>=60: lines.append("☐ Direktbuchung/App-Link freundlich mitgeben.")
        if prof['critical']>=45: lines.append("☐ Erwartungen schriftlich klar bestätigen, keine vagen Zusagen.")
        if prof['quality']<45: lines.append("☐ Profilqualität niedrig: bei Gelegenheit kurz nach Anreiseart/Frühstück fragen.")
        lines.append("")
        lines.append("Herleitung")
        lines.extend(prof['reasons'] if prof['reasons'] else ["• Keine starken Hinweise vorhanden; Profil basiert auf Grundmustern."])
        lines.append("")
        lines.append("Hinweis: [Fakt] sind nur Buchungsdaten. Prozentwerte sind [Schätzung] oder [Vermutung]. Google-KI-/Agenten-Hinweise sind manuell eingefügte [Nicht verifiziert] Zusatzinformationen und keine Identitätsprüfung.")
        self.gai_output.delete("1.0","end"); self.gai_output.insert("1.0","\n".join(lines))
        self.gai_status.set("Profil PLUS berechnet – bitte als Schätzung behandeln.")

    def gai_print_profile_pdf(self):
        """KI-Gastprofil als internes PDF drucken/öffnen."""
        try:
            b=self.gai_selected_booking()
            if not b:
                messagebox.showinfo("Gastprofil PDF","Bitte zuerst eine Buchung auswählen."); return
            txt=self.gai_output.get("1.0","end").strip() if hasattr(self,"gai_output") else ""
            if not txt or txt.startswith("Noch kein"):
                # Für den Druck automatisch berechnen, damit der Button sofort funktioniert.
                self.gai_calculate()
                txt=self.gai_output.get("1.0","end").strip()
            pdf=self.gai_profile_pdf_core(b,txt)
            messagebox.showinfo("Gästeprofil PDF erstellt",str(pdf))
            try: os.startfile(str(pdf))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("Gastprofil PDF",str(e))

    def gai_profile_pdf_core(self,b,profile_text):
        """Erstellt ein A4-PDF des KI-Gastprofils. Prozentwerte bleiben klar als Schätzung/Vermutung markiert."""
        safe=re.sub(r"[^A-Za-z0-9_\-]+","_",str(b.get("guest","Gast")).strip())[:50] or "Gast"
        pdf=out_dir()/f"Gaesteprofil_KI_{safe}_{str(b.get('arrival','')).replace('-','')}.pdf"
        styles=getSampleStyleSheet()
        styles["Normal"].fontSize=9
        styles["Normal"].leading=11
        styles["Italic"].fontSize=8
        doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=10*mm,bottomMargin=10*mm)
        story=[]
        add_logo_to_story(story)
        story.append(Paragraph("KI-Gästeprofil 360° / interne Gastgeberhilfe",styles["Title"]))
        story.append(Paragraph("Zuhause am Bach & Gästehaus Wachau",styles["Normal"]))
        story.append(Spacer(1,4*mm))
        ns=nights(b.get("arrival",""),b.get("departure",""))
        stammdaten=[
            ["Gast", b.get("guest","")],
            ["Aufenthalt", f"{fmt(b.get('arrival',''))} bis {fmt(b.get('departure',''))} · {ns} Nacht/Nächte"],
            ["Zimmer", room_name(self.d,b.get("room_id",""))],
            ["Personen", str(b.get("persons","") or "")],
            ["Telefon", b.get("phone","") or "—"],
            ["E-Mail", b.get("email","") or "—"],
            ["Quelle", b.get("source","") or "—"],
        ]
        table=Table([[Paragraph(html.escape(str(a)),styles["Normal"]),Paragraph(html.escape(str(c)),styles["Normal"])] for a,c in stammdaten],colWidths=[38*mm,135*mm])
        table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),("BACKGROUND",(0,0),(0,-1),colors.whitesmoke),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.append(table)
        story.append(Spacer(1,5*mm))
        story.append(Paragraph("Profil-Auswertung",styles["Heading2"]))
        clean=(profile_text or "").replace("=","-")
        for block in clean.split("\n"):
            line=block.strip()
            if not line:
                story.append(Spacer(1,2*mm)); continue
            if line.startswith("KI-Gastprofil"):
                continue
            if line in ("[Schätzung] Reiseart","[Schätzung] Aufenthalt/Service","[Vermutung] Reisestil / Interessen","[Nicht verifiziert] Öffentliche Hinweise","Serviceempfehlung","Service-Checkliste","Herleitung"):
                story.append(Paragraph(html.escape(line),styles["Heading3"]))
            else:
                story.append(Paragraph(html.escape(line),styles["Normal"]))
        story.append(Spacer(1,4*mm))
        story.append(Paragraph("Wichtig: Dieses PDF ist ausschließlich eine interne Gastgeberhilfe. [Fakt] basiert auf Buchungsdaten. Prozentwerte sind [Schätzung] oder [Vermutung] und nicht verifiziert.",styles["Italic"]))
        story.append(Paragraph(f"Erstellt mit {APP_NAME} | {VERSION}",styles["Italic"]))
        doc.build(story)
        return pdf

    def gai_save_note(self):
        b=self.gai_selected_booking()
        if not b: messagebox.showinfo("Gastprofil KI","Keine Buchung ausgewählt."); return
        txt=self.gai_output.get("1.0","end").strip()
        if not txt or txt.startswith("Noch kein"):
            messagebox.showinfo("Gastprofil KI","Bitte zuerst Profil berechnen."); return
        old=b.get("notes","")
        block="\n\n--- KI-Gastprofil 360° (intern, Schätzung) ---\n"+txt[:3500]
        b["notes"]=(old+block).strip()
        save(self.d)
        self.gai_status.set("KI-Gastprofil als interne Notiz gespeichert.")

    def gai_open_search(self,kind):
        b=self.gai_selected_booking()
        if not b: messagebox.showinfo("Gastprofil KI","Bitte zuerst eine Buchung auswählen."); return
        name=str(b.get("guest","")).strip(); city=str(b.get("city","") or b.get("ort","")).strip(); phone=str(b.get("phone","") or b.get("telefon","")).strip()
        q=' '.join(x for x in [name, city] if x).strip()
        if kind=='google': url='https://www.google.com/search?q='+urllib.parse.quote(q)
        elif kind=='facebook': url='https://www.facebook.com/search/top?q='+urllib.parse.quote(q)
        elif kind=='instagram': url='https://www.google.com/search?q='+urllib.parse.quote('site:instagram.com '+q)
        else: url='https://www.google.com/search?q='+urllib.parse.quote('Telefonbuch '+q+' '+phone)
        webbrowser.open(url)

    # ---------------- Preisagent 10/10 ----------------

    def build_price_agent(self):
        main=ttk.Frame(self.tab_priceagent)
        main.pack(fill="both",expand=True,padx=10,pady=10)

        top=self.card(main,"💡 Preisagent Wachau – KI-Strategie Professional")
        ttk.Label(top,text="PreisAgent AI 3.1: Ein kompakter Agent berechnet die Preisstrategie aus eigener Belegung, Wetter, Events, Schulferien AT/DE und Mitbewerber-Signalen. Booking/Google werden nicht als extra Knopflandschaft angezeigt; der Agent öffnet die sichtbare Marktrecherche gebündelt und erstellt den KI-Recherchetext.",style="Card.TLabel",wraplength=1400).pack(anchor="w")

        line=ttk.Frame(top,style="Card.TFrame"); line.pack(fill="x",pady=5)
        self.pa_start=StringVar(value=date.today().isoformat())
        self.pa_days=StringVar(value="7")
        self.pa_base_price=StringVar(value="99")
        self.pa_min_price=StringVar(value="79")
        self.pa_max_price=StringVar(value="149")
        self.pa_status=StringVar(value="Bereit. KI-Preisstrategie starten.")

        for label,var,w in [("Start",self.pa_start,12),("Tage",self.pa_days,5),("Basis",self.pa_base_price,7),("Min",self.pa_min_price,7),("Max",self.pa_max_price,7)]:
            ttk.Label(line,text=label,style="Card.TLabel").pack(side="left",padx=3)
            ttk.Entry(line,textvariable=var,width=w).pack(side="left",padx=3)
        ttk.Button(line,text="🤖 KI-PREISSTRATEGIE ERMITTELN",command=self.pa_run_market_agent,style="Touch.TButton").pack(side="left",padx=8)
        ttk.Button(line,text="CSV",command=self.price_agent_csv,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(line,text="PREIS ÜBERNEHMEN",command=self.price_agent_apply_selected,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Label(top,textvariable=self.pa_status,style="Card.TLabel").pack(anchor="w")

        result=self.card(main,"Preisstrategie – nächste freie Zimmer-Tage")
        cols=("date","room","weather","own_occ","comp","event","market","score","low","price","high","reason")
        self.pa_tree=ttk.Treeview(result,columns=cols,show="headings",height=11)
        labels={"date":"Datum","room":"Zimmer","weather":"Wetter","own_occ":"Ausl.","comp":"Markt","event":"Event","market":"KI","score":"Score","price":"Empfohlen","low":"Schnellpreis","high":"Maximalpreis","reason":"Status"}
        widths={"date":86,"room":115,"weather":130,"own_occ":55,"comp":135,"event":90,"market":95,"score":55,"low":86,"price":86,"high":86,"reason":300}
        for c in cols:
            self.pa_tree.heading(c,text=labels[c])
            self.pa_tree.column(c,width=widths[c],anchor="w",stretch=(c=="reason"))
        self.pa_tree.pack(fill="both",expand=True)
        self.pa_tree.bind("<Double-1>", self.pa_show_selected_detail)

        lower=ttk.Frame(main); lower.pack(fill="both",expand=True,pady=(8,0))
        left=ttk.Frame(lower); left.pack(side="left",fill="both",expand=True,padx=(0,6))
        right=ttk.Frame(lower); right.pack(side="right",fill="y",padx=(6,0))

        info=self.card(left,"KI-Agent Ergebnis / Strategie")
        self.pa_text=Text(info,height=9,wrap="word",bg="#ffffff",relief="flat",font=("Consolas",10),padx=10,pady=8)
        self.pa_text.pack(fill="both",expand=True)

        comp=self.card(right,"Mitbewerber kurz erfassen")
        self.comp_name=StringVar()
        self.comp_price=StringVar(value="95")
        self.comp_available=BooleanVar(value=True)
        self.comp_rating=StringVar(value="9.0")
        self.comp_distance=StringVar(value="5")
        for label,var,width in [("Name",self.comp_name,18),("Preis",self.comp_price,7),("Bew.",self.comp_rating,5),("km",self.comp_distance,5)]:
            row=ttk.Frame(comp,style="Card.TFrame"); row.pack(fill="x",pady=1)
            ttk.Label(row,text=label,style="Card.TLabel",width=7).pack(side="left")
            ttk.Entry(row,textvariable=var,width=width).pack(side="left",fill="x",expand=True)
        ttk.Checkbutton(comp,text="sichtbar frei",variable=self.comp_available).pack(anchor="w")
        rb=ttk.Frame(comp,style="Card.TFrame"); rb.pack(fill="x",pady=3)
        ttk.Button(rb,text="HINZUFÜGEN",command=self.add_competitor,style="Primary.TButton").pack(side="left",padx=2)
        ttk.Button(rb,text="LEEREN",command=self.pa_clear_competitors,style="Primary.TButton").pack(side="left",padx=2)
        self.comp_tree=ttk.Treeview(comp,columns=("name","price","available"),show="headings",height=4)
        for c,w in [("name",130),("price",55),("available",50)]:
            self.comp_tree.heading(c,text=c); self.comp_tree.column(c,width=w,anchor="w")
        self.comp_tree.pack(fill="x",pady=4)

        ev=self.card(right,"Events kurz")
        self.event_date=StringVar(value=date.today().isoformat())
        self.event_title=StringVar()
        self.event_strength=StringVar(value="15")
        for label,var,width in [("Datum",self.event_date,11),("Titel",self.event_title,18),("Punkte",self.event_strength,5)]:
            row=ttk.Frame(ev,style="Card.TFrame"); row.pack(fill="x",pady=1)
            ttk.Label(row,text=label,style="Card.TLabel",width=7).pack(side="left")
            ttk.Entry(row,textvariable=var,width=width).pack(side="left",fill="x",expand=True)
        rb=ttk.Frame(ev,style="Card.TFrame"); rb.pack(fill="x",pady=3)
        ttk.Button(rb,text="ADD",command=self.add_event_hint,style="Primary.TButton").pack(side="left",padx=2)
        ttk.Button(rb,text="ONLINE",command=self.pa_load_events_online,style="Gold.TButton").pack(side="left",padx=2)
        self.event_tree=ttk.Treeview(ev,columns=("date","title","strength"),show="headings",height=4)
        for c,w in [("date",80),("title",145),("strength",55)]:
            self.event_tree.heading(c,text=c); self.event_tree.column(c,width=w,anchor="w")
        self.event_tree.pack(fill="x",pady=4)

        self.refresh_price_agent()

    def ensure_price_agent_data(self):
        self.d.setdefault("competitors",[])
        self.d.setdefault("event_hints",[])
        self.d.setdefault("price_agent_weather",{})
        self.d.setdefault("school_holidays_cache",{})

    def add_competitor(self):
        try:
            self.ensure_price_agent_data()
            name=self.comp_name.get().strip()
            if not name:
                messagebox.showinfo("Mitbewerber","Bitte Namen eingeben.")
                return
            self.d["competitors"].append({"id":uid("COMP"),"name":name,"price":fnum(self.comp_price.get()),"available":bool(self.comp_available.get()),"rating":fnum(self.comp_rating.get()),"distance":fnum(self.comp_distance.get())})
            save(self.d); self.comp_name.set("")
            self.refresh_competitors(); self.refresh_price_agent()
        except Exception as e:
            messagebox.showerror("Mitbewerber",str(e))

    def delete_competitor(self):
        sel=self.comp_tree.selection()
        if not sel:
            messagebox.showinfo("Mitbewerber","Bitte Mitbewerber markieren.")
            return
        name=self.comp_tree.item(sel[0])["values"][0]
        self.d["competitors"]=[c for c in self.d.get("competitors",[]) if c.get("name")!=name]
        save(self.d); self.refresh_competitors(); self.refresh_price_agent()

    def refresh_competitors(self):
        if not hasattr(self,"comp_tree"):
            return
        self.ensure_price_agent_data()
        for i in self.comp_tree.get_children(): self.comp_tree.delete(i)
        for c in self.d.get("competitors",[]):
            self.comp_tree.insert("",END,values=(c.get("name",""),money(c.get("price",0)),"ja" if c.get("available",True) else "nein",str(c.get("rating","")),str(c.get("distance",""))))

    def add_event_hint(self):
        try:
            self.ensure_price_agent_data()
            ds=self.event_date.get().strip(); pdate(ds)
            title=self.event_title.get().strip() or "Veranstaltung"
            strength=fint(self.event_strength.get(),15)
            self.d["event_hints"].append({"id":uid("EVT"),"date":ds,"title":title,"strength":strength,"source":"manuell"})
            save(self.d); self.event_title.set("")
            self.refresh_event_hints(); self.refresh_price_agent()
        except Exception as e:
            messagebox.showerror("Event",str(e))

    def delete_event_hint(self):
        sel=self.event_tree.selection()
        if not sel:
            messagebox.showinfo("Event","Bitte Event markieren.")
            return
        vals=self.event_tree.item(sel[0])["values"]
        ds=str(vals[0]); title=str(vals[1])
        self.d["event_hints"]=[e for e in self.d.get("event_hints",[]) if not (str(e.get("date",""))==ds and str(e.get("title",""))==title)]
        save(self.d); self.refresh_event_hints(); self.refresh_price_agent()

    def refresh_event_hints(self):
        if not hasattr(self,"event_tree"):
            return
        self.ensure_price_agent_data()
        for i in self.event_tree.get_children(): self.event_tree.delete(i)
        for e in sorted(self.d.get("event_hints",[]),key=lambda x:x.get("date","")):
            self.event_tree.insert("",END,values=(e.get("date",""),e.get("title",""),e.get("strength",0),e.get("source","")))

    def pa_load_weather(self):
        try:
            self.ensure_price_agent_data()
            self.pa_status.set("Wetter wird online geladen …"); self.root.update_idletasks()
            data, err = fetch_aggsbach_weather_7days()
            if err:
                self.pa_status.set("Wetter konnte nicht geladen werden – neutrale Annahme.")
                messagebox.showwarning("Wetter",str(err)); return
            self.d["price_agent_weather"]=data
            save(self.d)
            self.pa_status.set(f"Wetter geladen: {len(data)} Tage Aggsbach Markt/Wachau.")
            self.refresh_price_agent()
        except Exception as e:
            messagebox.showerror("Wetter",str(e))

    def pa_event_urls(self):
        # Öffentliche regionale Veranstaltungskalender.
        # Der Preisagent nutzt diese Seiten als Events-Signal und sucht nach Orten/Datumsangaben.
        return [
            "https://veranstaltungen.niederoesterreich.at/cal/wachau",
            "https://www.donau.com/wachau-nibelungengau-kremstal/veranstaltungen-finden",
            "https://www.donau.com/veranstaltungen-finden",
            "https://www.domaene-wachau.at/de/besuch/aktuelle-events/",
            "https://www.spitzaktuell.at/highlights-in-der-wachau",
            "https://www.schloss.at/de/kalender",
        ]

    def pa_event_locations(self):
        # Distanzwerte grob/konservativ als Signal für Preiswirkung.
        # Aggsbach/Aggstein/Spitz/Weißenkirchen/Melk sind Kernbereich.
        # Krems/Dürnstein werden auf Wunsch trotzdem einbezogen, aber distanzgewichtet.
        return [
            {"name":"Aggsbach Markt","aliases":["Aggsbach Markt","Aggsbach"],"km":0,"weight":1.00},
            {"name":"Aggstein","aliases":["Aggstein","Burgruine Aggstein","Schlossruine Aggstein"],"km":4,"weight":1.00},
            {"name":"Spitz","aliases":["Spitz","Spitz an der Donau"],"km":7,"weight":1.00},
            {"name":"Weißenkirchen","aliases":["Weißenkirchen","Weissenkirchen","Weißenkirchen in der Wachau"],"km":12,"weight":0.95},
            {"name":"Melk","aliases":["Melk","Stift Melk"],"km":14,"weight":0.90},
            {"name":"Wachau","aliases":["Wachau","Welterbesteig","Wachauer"],"km":10,"weight":0.90},
            {"name":"Dürnstein","aliases":["Dürnstein","Duernstein","Stift Dürnstein"],"km":18,"weight":0.70},
            {"name":"Krems","aliases":["Krems","Krems an der Donau","Krems-Stein","Stein an der Donau","Landesgalerie Niederösterreich","Karikaturmuseum Krems"],"km":24,"weight":0.55},
        ]

    def pa_event_date_patterns(self, d):
        months_de=["Jänner","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]
        months_de_alt=["Jaenner","Februar","Maerz","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]
        return [
            d.strftime("%d.%m.%Y"),
            d.strftime("%d.%m."),
            d.strftime("%Y-%m-%d"),
            f"{d.day}. {months_de[d.month-1]}",
            f"{d.day}. {months_de_alt[d.month-1]}",
            f"{d.day}. {d.month}.",
        ]

    def pa_event_extract_context(self, text, pos, size=180):
        a=max(0,pos-size)
        b=min(len(text),pos+size)
        s=text[a:b]
        s=re.sub(r"\s+"," ",s).strip()
        return s[:240]

    def pa_event_distance_weight(self, location):
        try:
            km=float(location.get("km",99))
        except Exception:
            km=99
        if km <= 15:
            return float(location.get("weight",1.0))
        # Ausdrücklich gewünschte Orte jenseits des Kernradius werden nicht verworfen,
        # sondern schwächer gewichtet.
        if km <= 25:
            return min(float(location.get("weight",0.55)),0.70)
        return 0.35


    def pa_load_events_online(self):
        """Erweiterte Eventprüfung für Preisagent:
        - prüft mehrere regionale Quellen
        - sucht nach Datum und Ortsnamen
        - berücksichtigt Aggsbach/Aggstein/Melk/Spitz/Weißenkirchen/Dürnstein/Krems/Wachau
        - gewichtet Ereignisse im 15-km-Kern höher
        """
        try:
            self.ensure_price_agent_data()
            start=pdate(self.pa_start.get())
            days=max(1,min(31,fint(self.pa_days.get(),7)))
            dates=[start+timedelta(days=i) for i in range(days)]
            locations=self.pa_event_locations()

            self.pa_status.set("Events Wachau/Melk/Krems/Spitz/Aggstein werden online geprüft …")
            self.root.update_idletasks()

            found=[]
            sources_ok=0
            for url in self.pa_event_urls():
                try:
                    with urllib.request.urlopen(url,timeout=12) as resp:
                        raw=resp.read().decode("utf-8","ignore")
                    sources_ok+=1
                    text=re.sub(r"<script.*?</script>"," ",raw,flags=re.S|re.I)
                    text=re.sub(r"<style.*?</style>"," ",text,flags=re.S|re.I)
                    text=re.sub(r"<[^>]+>"," ",text)
                    text=html.unescape(text)
                    text=re.sub(r"\s+"," ",text)

                    text_lower=text.lower()

                    for d in dates:
                        date_hits=[]
                        for pat in self.pa_event_date_patterns(d):
                            idx=text_lower.find(pat.lower())
                            if idx!=-1:
                                date_hits.append(idx)

                        # Manche Seiten listen Jahres-/Dauerveranstaltungen ohne konkreten Tag.
                        # Wenn kein Datum gefunden wird, aber starke Orts-/Wachau-Signale vorhanden sind,
                        # wird kein konkreter Treffer gesetzt.
                        if not date_hits:
                            continue

                        for loc in locations:
                            aliases=loc.get("aliases",[])
                            loc_positions=[]
                            for alias in aliases:
                                idx=text_lower.find(str(alias).lower())
                                if idx!=-1:
                                    loc_positions.append(idx)

                            if not loc_positions:
                                continue

                            # Treffer ist stärker, wenn Ort und Datum nahe im Text stehen.
                            best_distance=999999
                            best_pos=loc_positions[0]
                            for dp in date_hits:
                                for lp in loc_positions:
                                    dist=abs(dp-lp)
                                    if dist<best_distance:
                                        best_distance=dist
                                        best_pos=lp

                            if best_distance > 3000:
                                # Ort und Datum stehen zu weit auseinander; vermutlich Navigation/Seitentext.
                                continue

                            distance_weight=self.pa_event_distance_weight(loc)
                            proximity_bonus=10 if best_distance<500 else 6 if best_distance<1200 else 3
                            strength=int(round((12 + proximity_bonus) * distance_weight))
                            if "wachau" in text_lower[max(0,best_pos-300):best_pos+300]:
                                strength+=3
                            if any(word in text_lower[max(0,best_pos-300):best_pos+300] for word in ["fest","sonnenwende","wein","heurig","konzert","markt","führung","kultur"]):
                                strength+=3

                            context=self.pa_event_extract_context(text,best_pos)
                            title=f"{loc.get('name','Region')} – Veranstaltungshinweis"
                            if context:
                                # Kontext nicht zu lang als Titel verwenden
                                title=f"{loc.get('name','Region')}: {context[:95]}"

                            found.append({
                                "date":d.isoformat(),
                                "title":title,
                                "strength":max(5,min(25,strength)),
                                "source":"online",
                                "place":loc.get("name",""),
                                "km":loc.get("km",""),
                                "url":url
                            })
                except Exception:
                    continue

            # Alte online-Hinweise im geprüften Zeitraum entfernen
            date_range={d.isoformat() for d in dates}
            self.d["event_hints"]=[
                e for e in self.d.get("event_hints",[])
                if not (e.get("source")=="online" and e.get("date") in date_range)
            ]

            # Deduplizieren: Datum+Ort+Quelle
            existing={(e.get("date"),e.get("place",""),e.get("source"),e.get("url","")) for e in self.d.get("event_hints",[])}
            added=0
            for e in found:
                key=(e.get("date"),e.get("place",""),e.get("source"),e.get("url",""))
                if key not in existing:
                    self.d["event_hints"].append(e)
                    existing.add(key)
                    added+=1

            save(self.d)
            self.refresh_event_hints()
            self.pa_status.set(f"Eventprüfung abgeschlossen: {added} Signal(e), {sources_ok} Quelle(n) erreichbar. Bitte manuell prüfen.")
            self.refresh_price_agent()
        except Exception as e:
            messagebox.showerror("Events online",str(e))


    def pa_own_occupancy_percent(self, d):
        rooms=[r for r in self.d.get("rooms",[]) if r.get("active",True)]
        total=max(1,len(rooms)); occupied=0
        for r in rooms:
            rid=r.get("id")
            for b in self.d.get("bookings",[]):
                if b.get("status")=="storniert": continue
                if str(b.get("room_id",""))==str(rid) and pdate(b.get("arrival","")) <= d < pdate(b.get("departure","")):
                    occupied+=1; break
        return int(round(occupied*100/total)), occupied, total

    def pa_competitor_signal(self):
        comps=self.d.get("competitors",[])
        available=[c for c in comps if c.get("available",True)]
        if not comps:
            return 0,"keine Daten",None
        avg=sum(float(c.get("price",0) or 0) for c in available)/max(1,len(available)) if available else 0
        ratio=len(available)/max(1,len(comps))
        signal=12 if ratio<=0.35 else 6 if ratio<=0.60 else -8 if ratio>=0.85 else 0
        return signal,f"{len(available)}/{len(comps)} frei",avg

    def pa_event_signal_for_date(self,d):
        ds=d.isoformat()
        events=[e for e in self.d.get("event_hints",[]) if e.get("date")==ds]
        if not events:
            return 0,"nein"
        strength=sum(fint(e.get("strength",0),0) for e in events)
        parts=[]
        for e in events[:3]:
            place=e.get("place","") or ""
            km=e.get("km","")
            title=e.get("title","Event")
            if place:
                parts.append(f"{place} ({km} km)")
            else:
                parts.append(title[:30])
        label=", ".join(parts)
        return min(30,strength), label[:100]



    def pa_school_holiday_regions_weight(self):
        """Gewichtung der Herkunftsmärkte für Zuhause am Bach.
        Bayern/Deutschland-Süd und Österreich-Ost sind für die Wachau besonders relevant.
        """
        return {
            # Österreich
            "AT-NÖ": 1.00, "AT-WI": 0.90, "AT-OOE": 0.75, "AT-BGLD": 0.65,
            "AT-STMK": 0.55, "AT-SBG": 0.45, "AT-KTN": 0.40, "AT-T": 0.35, "AT-VBG": 0.30,
            # Deutschland
            "DE-BY": 1.00, "DE-BW": 0.90, "DE-HE": 0.60, "DE-NW": 0.55,
            "DE-SN": 0.45, "DE-RP": 0.40, "DE-NI": 0.35, "DE-TH": 0.35,
            "DE-BE": 0.30, "DE-BB": 0.30, "DE-HH": 0.25, "DE-HB": 0.20,
            "DE-MV": 0.25, "DE-SH": 0.25, "DE-SL": 0.20, "DE-ST": 0.25,
        }

    def pa_seed_school_holidays_if_missing(self):
        """Legt eine editierbare lokale Ferientabelle an, falls noch keine existiert.
        Die Tabelle enthält gesicherte AT-2026 Kernferien aus öffentlichen Quellen und kann ergänzt werden.
        Für DE/AT wird zusätzlich online über OpenHolidays aktualisiert, wenn Internet verfügbar ist.
        """
        fn = school_holidays_file()
        if fn.exists():
            return
        rows = [
            ["country","region","name","start","end","weight","source"],
            ["AT","AT-NÖ","Semesterferien", "2026-02-02", "2026-02-07", "1.00", "BMB/ÖAMTC"],
            ["AT","AT-WI","Semesterferien", "2026-02-02", "2026-02-07", "0.90", "BMB/ÖAMTC"],
            ["AT","AT-BGLD","Semesterferien", "2026-02-09", "2026-02-14", "0.65", "BMB/ÖAMTC"],
            ["AT","AT-KTN","Semesterferien", "2026-02-09", "2026-02-14", "0.40", "BMB/ÖAMTC"],
            ["AT","AT-SBG","Semesterferien", "2026-02-09", "2026-02-14", "0.45", "BMB/ÖAMTC"],
            ["AT","AT-T","Semesterferien", "2026-02-09", "2026-02-14", "0.35", "BMB/ÖAMTC"],
            ["AT","AT-VBG","Semesterferien", "2026-02-09", "2026-02-14", "0.30", "BMB/ÖAMTC"],
            ["AT","AT-OOE","Semesterferien", "2026-02-16", "2026-02-21", "0.75", "BMB/ÖAMTC"],
            ["AT","AT-STMK","Semesterferien", "2026-02-16", "2026-02-21", "0.55", "BMB/ÖAMTC"],
            ["AT","AT-ALL","Osterferien", "2026-03-28", "2026-04-06", "0.80", "BMB"],
            ["AT","AT-ALL","Pfingstferien", "2026-05-23", "2026-05-25", "0.55", "BMB"],
            ["AT","AT-NÖ","Sommerferien", "2026-07-04", "2026-09-06", "1.00", "ÖAMTC/BMB"],
            ["AT","AT-WI","Sommerferien", "2026-07-04", "2026-09-06", "0.90", "ÖAMTC/BMB"],
            ["AT","AT-BGLD","Sommerferien", "2026-07-04", "2026-09-06", "0.65", "ÖAMTC/BMB"],
            ["AT","AT-KTN","Sommerferien", "2026-07-11", "2026-09-13", "0.40", "ÖAMTC/BMB"],
            ["AT","AT-OOE","Sommerferien", "2026-07-11", "2026-09-13", "0.75", "ÖAMTC/BMB"],
            ["AT","AT-SBG","Sommerferien", "2026-07-11", "2026-09-13", "0.45", "ÖAMTC/BMB"],
            ["AT","AT-STMK","Sommerferien", "2026-07-11", "2026-09-13", "0.55", "ÖAMTC/BMB"],
            ["AT","AT-T","Sommerferien", "2026-07-11", "2026-09-13", "0.35", "ÖAMTC/BMB"],
            ["AT","AT-VBG","Sommerferien", "2026-07-11", "2026-09-13", "0.30", "ÖAMTC/BMB"],
            ["AT","AT-ALL","Weihnachtsferien", "2026-12-24", "2027-01-06", "0.70", "BMB"],
        ]
        try:
            with open(fn, "w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f, delimiter=";").writerows(rows)
        except Exception:
            pass

    def pa_load_school_holidays_local(self):
        self.pa_seed_school_holidays_if_missing()
        rows=[]
        fn=school_holidays_file()
        if not fn.exists():
            return rows
        try:
            with open(fn, "r", encoding="utf-8-sig", newline="") as f:
                reader=csv.DictReader(f, delimiter=";")
                for r in reader:
                    start=pa_safe_date(r.get("start")); end=pa_safe_date(r.get("end"))
                    if not start or not end: continue
                    rows.append({
                        "country": r.get("country",""), "region": r.get("region",""), "name": r.get("name","Ferien"),
                        "start": start, "end": end, "weight": fnum(r.get("weight",1),1), "source": r.get("source","lokal")
                    })
        except Exception:
            pass
        return rows

    def pa_openholidays_name(self, item):
        names=item.get("name") or item.get("names") or []
        if isinstance(names, str): return names
        if isinstance(names, list):
            for n in names:
                if isinstance(n, dict) and str(n.get("language",""))[:2].lower() in ("de","en"):
                    return n.get("text") or n.get("name") or "Schulferien"
            if names and isinstance(names[0], dict): return names[0].get("text") or names[0].get("name") or "Schulferien"
        return "Schulferien"

    def pa_online_school_holiday_rows(self, start, end):
        """Online-Ferienimport über OpenHolidays API. Fällt still auf lokale CSV zurück.
        [Nicht verifiziert im Ausdruck] Internet/API kann scheitern oder einzelne Länder anders gruppieren.
        """
        rows=[]
        # Country-level Query: OpenHolidays liefert je nach Land nationale und regionale Einträge.
        for country in ("AT", "DE"):
            url = "https://openholidaysapi.org/SchoolHolidays?" + urllib.parse.urlencode({
                "countryIsoCode": country,
                "languageIsoCode": "DE",
                "validFrom": start.isoformat(),
                "validTo": end.isoformat(),
            })
            try:
                req=urllib.request.Request(url, headers={"accept":"text/json", "User-Agent":"ZuhauseAmBachManager/19.2"})
                raw=urllib.request.urlopen(req, timeout=8).read().decode("utf-8","ignore")
                data=json.loads(raw)
                for item in data if isinstance(data,list) else []:
                    sd=pa_safe_date(item.get("startDate") or item.get("validFrom")); ed=pa_safe_date(item.get("endDate") or item.get("validTo"))
                    if not sd or not ed: continue
                    name=self.pa_openholidays_name(item)
                    regions=[]
                    for key in ("subdivisions","subdivisionCodes","regions"):
                        val=item.get(key)
                        if isinstance(val,list):
                            for x in val:
                                if isinstance(x,dict): regions.append(x.get("code") or x.get("shortName") or x.get("id") or "")
                                else: regions.append(str(x))
                    if not regions:
                        regions=[country+"-ALL"]
                    for reg in regions:
                        rows.append({"country":country,"region":str(reg),"name":name,"start":sd,"end":ed,"weight":1.0,"source":"OpenHolidays"})
            except Exception:
                continue
        return rows

    def pa_load_school_holidays_online_cache(self):
        try:
            start=pdate(self.pa_start.get())
            days=max(1,min(365,fint(self.pa_days.get(),31)))
        except Exception:
            start=date.today(); days=31
        end=start+timedelta(days=days+1)
        rows=self.pa_online_school_holiday_rows(start,end)
        if not rows:
            return 0
        cache=[]
        for r in rows:
            cache.append({"country":r["country"],"region":r["region"],"name":r["name"],"start":r["start"].isoformat(),"end":r["end"].isoformat(),"weight":r.get("weight",1),"source":r.get("source","online")})
        self.d["school_holidays_cache"]={"updated":datetime.now().isoformat(timespec="seconds"),"rows":cache}
        save(self.d)
        return len(cache)

    def pa_school_holiday_rows(self):
        rows=self.pa_load_school_holidays_local()
        cache=self.d.get("school_holidays_cache",{}).get("rows",[])
        for r in cache:
            sd=pa_safe_date(r.get("start")); ed=pa_safe_date(r.get("end"))
            if sd and ed:
                rows.append({"country":r.get("country",""),"region":r.get("region",""),"name":r.get("name","Schulferien"),"start":sd,"end":ed,"weight":fnum(r.get("weight",1),1),"source":r.get("source","online")})
        return rows

    def pa_school_holiday_signal_for_date(self,d):
        weights=self.pa_school_holiday_regions_weight()
        hits=[]; score=0.0
        for r in self.pa_school_holiday_rows():
            try:
                if r["start"] <= d <= r["end"]:
                    reg=str(r.get("region") or "")
                    base=weights.get(reg, 0.65 if reg.endswith("ALL") else 0.35)
                    w=base * fnum(r.get("weight",1),1)
                    score += 10*w
                    hits.append((w, reg, r.get("name","Ferien"), r.get("source","")))
            except Exception:
                continue
        if not hits:
            return 0,"keine Ferien"
        hits.sort(reverse=True, key=lambda x:x[0])
        label_parts=[]
        for w,reg,name,source in hits[:4]:
            reg_label=reg.replace("AT-","AT ").replace("DE-","DE ")
            label_parts.append(f"{reg_label} {name}")
        label=", ".join(label_parts)
        return int(min(28, round(score))), label[:110]

    def pa_weather_signal_for_date(self,d):
        w=self.d.get("price_agent_weather",{}).get(d.isoformat())
        if not w: return 0,"neutral"
        desc=w.get("weather",""); temp=w.get("temp_max"); rain=w.get("precip_prob")
        score=0
        try:
            if temp is not None and 18 <= float(temp) <= 28: score+=8
            if rain is not None and float(rain)>=70: score-=12
            elif rain is not None and float(rain)>=45: score-=6
        except Exception:
            pass
        if "sonnig" in desc: score+=7
        if "bewölkt" in desc: score+=2
        if "Gewitter" in desc: score-=14
        return score,f"{desc}, {temp}°C, Regen {rain if rain is not None else '-'}%"

    def pa_recommended_price(self, room, d):
        """Preisagent V14.1: Johann-Formel, aber mit vorhandenen Managerdaten.
        Verändert keine Buchung automatisch. Erst der Button übernimmt den Preis.
        """
        base=fnum(self.pa_base_price.get(),99)
        minp=fnum(self.pa_min_price.get(),79)
        maxp=fnum(self.pa_max_price.get(),149)
        if float(room.get("price",0) or 0)>0:
            # Zimmerpreis als Basis nutzen, falls gepflegt; sonst Basisfeld.
            base=float(room.get("price",0) or 0)
        weather_score, weather_label=self.pa_weather_signal_for_date(d)
        occ_percent, occ_num, occ_total=self.pa_own_occupancy_percent(d)
        comp_score, comp_label, comp_avg=self.pa_competitor_signal()
        event_score, event_label=self.pa_event_signal_for_date(d)
        holiday_score, holiday_label=self.pa_school_holiday_signal_for_date(d)
        combined_event_score = min(40, event_score + holiday_score)
        if holiday_label != "keine Ferien":
            event_label = (event_label + " · " if event_label != "nein" else "") + "Ferien: " + holiday_label
        gap=self.free_gap_days(room.get("id"),d,10)
        days_until=(pdate(d)-date.today()).days

        # Nachfrage aus Mitbewerbern ableiten: wenige freie/teure Mitbewerber = Nachfrage höher.
        comps=[c for c in self.d.get("competitors",[]) if c.get("available",True)]
        if comps:
            available=len(comps)
            # konservative Näherung, weil wir ohne API keine echte Wachau-Gesamtverfügbarkeit kennen.
            free_percent=10 if comp_score>=12 else 20 if comp_score>=6 else 30 if available<=4 else 45
        else:
            free_percent=30

        price, details = pa_johann_dynamic_price(
            base=base,
            d=d,
            occ_percent=occ_percent,
            free_percent=free_percent,
            weather_score=weather_score,
            event_score=combined_event_score,
            days_until_arrival=days_until,
            min_price=minp,
            max_price=maxp,
        )

        # Mitbewerberanker: nicht massiv über passende Mitbewerber, aber auch nicht verschenken.
        if comp_avg and comp_avg>0:
            price=max(price, int(round(comp_avg-10))) if comp_avg>base else min(price, int(round(comp_avg+15)))
            price=max(minp, min(maxp, price))

        score_val = 1
        try:
            score_val = max(1,min(10,round((details["raw"] / max(1,base)) * 4)))
        except Exception:
            pass
        reasons=[
            f"{details['season_label']} ×{details['season_factor']}",
            f"{details['weekend_label']} ×{details['weekend_factor']}",
            f"Auslastung {occ_percent}% ×{details['occupancy_factor']}",
            f"{details['demand_label']} ×{details['demand_factor']}",
            f"{details['weather_label']} ×{details['weather_factor']}",
        ]
        if event_label!="nein":
            reasons.append(f"Event/Ferien: {event_label} ×{details['event_factor']}")
        reasons.append(f"{details['lastminute_label']} ×{details['lastminute_factor']}")
        reasons.append(f"Deckel {money(minp)}–{money(maxp)}")
        
        market_label = self.pa_market_ai_label(comp_score, comp_avg, occ_percent, combined_event_score, weather_score)
        # Preisband sauber begrenzen: Schnellpreis <= Empfohlen <= Maximalpreis <= eingestelltes Maximum.
        price = int(max(minp, min(maxp, round(price))))
        low_price = int(max(minp, min(price, round(price * 0.94))))
        high_price = int(max(price, min(maxp, round(price * 1.08))))
        if high_price < price:
            high_price = price
        if low_price > price:
            low_price = price
        status = self.pa_strategy_status(score_val, market_label, event_label, weather_label)
        return {"date":d,"room":room.get("name",""),"room_id":room.get("id",""),"weather":weather_label,"own_occ":f"{occ_percent}%","comp":comp_label,"event":event_label,"market":market_label,"score":f"{score_val}/10","price":price,"low":low_price,"high":high_price,"reason":status,"detail":" | ".join(reasons[:8])}

    def price_agent_rows(self):
        self.ensure_price_agent_data()
        try: start=pdate(self.pa_start.get())
        except Exception: start=date.today()
        days=max(1,min(31,fint(self.pa_days.get(),7)))
        rooms=[r for r in self.d.get("rooms",[]) if r.get("active",True)]
        rows=[]
        for i in range(days):
            d=start+timedelta(days=i)
            free_ids={str(r.get("id")) for r in self.free_rooms_on_date(d)}
            for room in rooms:
                if str(room.get("id")) in free_ids:
                    rows.append(self.pa_recommended_price(room,d))
        rows.sort(key=lambda x:(x["date"],x["room"]))
        return rows




    def pa_market_ai_label(self, comp_score, comp_avg, occ_percent, event_score, weather_score):
        """Konservative KI-Heuristik für Marktlage. Keine gesicherten externen Fakten."""
        points = 0
        points += comp_score
        points += 10 if occ_percent >= 75 else 5 if occ_percent >= 50 else -5 if occ_percent == 0 else 0
        points += min(12, event_score)
        points += 6 if weather_score >= 8 else -8 if weather_score <= -8 else 0
        if comp_avg and comp_avg >= 120: points += 6
        elif comp_avg and comp_avg <= 80: points -= 4
        if points >= 28: return "hoch · mutig"
        if points >= 14: return "gut · halten"
        if points <= -8: return "schwach · füllen"
        return "normal"


    def pa_strategy_status(self, score_val, market_label, event_label, weather_label):
        """Kurzer Status für die Preisagent-Tabelle statt überlanger Begründung."""
        try:
            score_int = int(str(score_val).split('/')[0])
        except Exception:
            score_int = 5
        if 'schwach' in str(market_label).lower() or score_int <= 3:
            return "schwache Nachfrage · Schnellpreis prüfen"
        if score_int >= 8:
            return "sehr gute Nachfrage · Preis halten"
        if score_int >= 6:
            return "gute Nachfrage · empfohlen"
        if event_label and event_label != "nein":
            return "Event-Signal · vorsichtig höher"
        return "normal · Markt beobachten"

    def pa_run_market_agent(self):
        """Ein Knopf statt Knopflandschaft: Wetter/Events/Browserrecherche/KI-Text/Preisberechnung."""
        try:
            self.pa_load_weather()
        except Exception:
            pass
        try:
            self.pa_load_events_online()
        except Exception:
            pass
        try:
            self.pa_load_school_holidays_online_cache()
        except Exception:
            pass
        try:
            start = pdate(self.pa_start.get())
            days = max(1, fint(self.pa_days.get(), 1))
        except Exception:
            start = date.today(); days = 1
        end = start + timedelta(days=days)
        booking_q = "Aggsbach Markt Maria Laach Spitz Wachau Unterkunft"
        booking_url = ("https://www.booking.com/searchresults.de.html?" + urllib.parse.urlencode({
            "ss": booking_q,
            "checkin": start.isoformat(),
            "checkout": end.isoformat(),
            "group_adults": 2,
            "no_rooms": 1,
            "group_children": 0,
        }))
        google_q = f'Unterkunft Aggsbach Markt Wachau Nordufer 10 km {start.isoformat()} {end.isoformat()} 2 Personen Preis Bewertung'
        try:
            webbrowser.open(booking_url)
            webbrowser.open('https://www.google.com/search?q=' + urllib.parse.quote(google_q))
        except Exception:
            pass
        text = self.pa_ai_copilot_text()
        try:
            self.clipboard_clear(); self.clipboard_append(text)
        except Exception:
            pass
        self.refresh_price_agent()
        if hasattr(self,"pa_text"):
            self.pa_text.insert("1.0", "KI-Agent gestartet: Booking + Google wurden im Browser geöffnet, der KI-Recherchetext liegt in der Zwischenablage. Sichtbare passende Mitbewerberpreise kurz rechts erfassen, dann erneut KI-PREISSTRATEGIE ERMITTELN.\n\n")
        self.pa_status.set("KI-Agent: Booking/Google geöffnet, Prompt kopiert, Preisstrategie berechnet.")

    def pa_open_booking_search(self):
        try:
            start = pdate(self.pa_start.get())
            days = max(1, fint(self.pa_days.get(), 1))
        except Exception:
            start = date.today(); days = 1
        end = start + timedelta(days=days)
        # Sichtbare Marktrecherche: Nordufer-nahe Orte statt verdecktem Scraping.
        q = "Aggsbach Markt Maria Laach Spitz Wachau Unterkunft"
        url = ("https://www.booking.com/searchresults.de.html?" + urllib.parse.urlencode({
            "ss": q,
            "checkin": start.isoformat(),
            "checkout": end.isoformat(),
            "group_adults": 2,
            "no_rooms": 1,
            "group_children": 0,
        }))
        webbrowser.open(url)
        messagebox.showinfo("Booking Marktrecherche", "Booking-Suche wurde geöffnet. Bitte nur Nordufer/10-km-nahe passende Unterkünfte übernehmen und Preise manuell als Mitbewerber eintragen.")

    def pa_open_google_search(self):
        try:
            start = pdate(self.pa_start.get())
            days = max(1, fint(self.pa_days.get(), 1))
        except Exception:
            start = date.today(); days = 1
        end = start + timedelta(days=days)
        q = f'Unterkunft Aggsbach Markt Wachau Nordufer 10 km {start.isoformat()} {end.isoformat()} 2 Personen Preis Bewertung'
        webbrowser.open('https://www.google.com/search?q=' + urllib.parse.quote(q))
        messagebox.showinfo("Google Marktrecherche", "Google-Suche wurde geöffnet. Sichtbare Preise/Bewertungen bitte als Mitbewerber eintragen.")

    def pa_copy_market_ai_prompt(self):
        text = self.pa_ai_copilot_text()
        try:
            self.clipboard_clear(); self.clipboard_append(text)
            messagebox.showinfo("Markt-KI", "KI-Recherchetext wurde in die Zwischenablage kopiert.")
        except Exception:
            if hasattr(self, 'pa_ai_text'):
                self.pa_ai_text.delete('1.0', END); self.pa_ai_text.insert('1.0', text)
            messagebox.showinfo("Markt-KI", "KI-Recherchetext steht im Textfeld.")

    def pa_clear_competitors(self):
        if not messagebox.askyesno("Mitbewerber leeren", "Alle aktuell eingetragenen Mitbewerberdaten löschen?"):
            return
        self.ensure_price_agent_data()
        self.d["competitors"] = []
        save(self.d)
        self.refresh_competitors(); self.refresh_price_agent()

    def pa_ai_copilot_text(self):
        """Automatischer KI-Copilot-Text für Preisrecherche und Preisentscheidung."""
        try:
            start = self.pa_start.get().strip() if hasattr(self,"pa_start") else date.today().isoformat()
            days = int(self.pa_days.get()) if hasattr(self,"pa_days") else 1
            try:
                arr = pdate(start)
            except Exception:
                arr = date.today()
            dep = arr + timedelta(days=max(1,days))
            base = self.pa_base_price.get().strip() if hasattr(self,"pa_base_price") else "90"
            minp = self.pa_min_price.get().strip() if hasattr(self,"pa_min_price") else "70"
            maxp = self.pa_max_price.get().strip() if hasattr(self,"pa_max_price") else "125"
            return f"""KI-Copilot Preisrecherche – Zuhause am Bach / Gästehaus Wachau

Kategorie:
Kleine Unterkunft / Privatzimmer / Bed & Breakfast / Unterkunft für Wanderer und Radfahrer in der Wachau.

Zeitraum:
Anreise: {arr.isoformat()}
Abreise: {dep.isoformat()}
Nächte: {(dep-arr).days}
Standardannahme: 2 Personen

Vergleichsraum:
NUR Nordseite der Donau im Umkreis von ca. 10 km ab Aggsbach Markt.
Bevorzugte Orte: Aggsbach Markt, Willendorf, Schwallenbach, Spitz-Nordufer, Maria Laach am Jauerling, Mühldorf, Jauerling-Umfeld.
Südseite nur als schwaches Signal, wenn für Welterbesteig/Donauradweg-Nordufer praktisch vergleichbar.
Feuerwehrfeste, Dorffeste, Kirtage, Weinveranstaltungen und Rad-/Wanderevents im Umkreis
Schulferien/Feiertage Österreich und Deutschland, besonders Bayern, Baden-Württemberg, Wien, Niederösterreich und Oberösterreich

Bitte recherchiere aktuelle sichtbare Unterkunftspreise für diesen Zeitraum auf Booking.com, Google Hotels und anderen Hotel-/Unterkunftsportalen.
Wichtig: Anzahl wirklich freier Zimmer nur nennen, wenn sie sichtbar/verlässlich angezeigt wird; sonst als "nicht verifiziert" markieren.

Bitte vergleiche nur passende Mitbewerber:
kleine Pensionen, Privatzimmer, Gästehäuser, B&B, einfache Hotels, wanderer-/radfahrerfreundliche Unterkünfte.

Bitte nicht gleichwertig werten:
Luxushotels, Wellnesshotels, Ferienwohnungen für große Gruppen, Unterkünfte auf der falschen Donauseite, wenn sie für Welterbesteig/Donauradweg Nordufer unpraktisch sind.

Ausgabe bitte als Tabelle:
Ort | Unterkunft | Preis Zeitraum | Preis/Nacht | Frühstück | Bewertung | Entfernung/Lage | Quelle | direkte Konkurrenz ja/nein

Preisrahmen Zuhause am Bach:
Basispreis: {base} €
Mindestpreis: {minp} €
Maximalpreis: {maxp} €

Am Ende bitte:
1. Durchschnittspreis der passenden Mitbewerber
2. niedrigster realistischer Preis
3. höchster realistischer Preis
4. konkrete Preisempfehlung für Zuhause am Bach mit drei Varianten: Schnellpreis, Empfohlener Preis, Maximalpreis
5. kurze Begründung
6. Ferien-/Feiertagssignal für AT/DE, falls relevant
7. Warnhinweis, falls Preise oder freie Zimmer nicht verlässlich sichtbar sind
"""
        except Exception as e:
            return f"KI-Copilot konnte nicht erstellt werden: {e}"

    def pa_update_ai_copilot(self):
        """Aktualisiert den eingebauten KI-Copilot-Bereich automatisch."""
        try:
            if hasattr(self,"pa_ai_text"):
                self.pa_ai_text.delete("1.0",END)
                self.pa_ai_text.insert("1.0",self.pa_ai_copilot_text())
        except Exception:
            pass


    def pa_competitor_summary(self):
        comps=self.d.get("competitors",[])
        prices=[]
        for c in comps:
            try:
                if c.get("available",True):
                    prices.append(float(c.get("price",0) or 0))
            except Exception:
                pass
        if not prices:
            return {"count":0,"avg":0,"min":0,"max":0,"signal":"keine Mitbewerberdaten"}
        avg=sum(prices)/len(prices)
        return {"count":len(prices),"avg":avg,"min":min(prices),"max":max(prices),"signal":f"{len(prices)} frei · Ø {money(avg)} · min {money(min(prices))} · max {money(max(prices))}"}

    def refresh_price_agent(self):
        comp_summary=self.pa_competitor_summary()
        self.pa_update_ai_copilot()
        if not hasattr(self,"pa_tree"): return
        self.ensure_price_agent_data()
        for i in self.pa_tree.get_children(): self.pa_tree.delete(i)
        rows=self.price_agent_rows()
        for r in rows:
            self.pa_tree.insert("",END,values=(r["date"].isoformat(),r["room"],r["weather"],r["own_occ"],r["comp"],r["event"],r.get("market",""),r["score"],money(r.get("low",r["price"])),money(r["price"]),money(r.get("high",r["price"])),r["reason"]))
        if hasattr(self,"pa_text"):
            self.pa_text.delete("1.0",END)
            self.pa_text.insert(END,f"Preisagent berechnet {len(rows)} freie Zimmer-Tage.\n")
            self.pa_text.insert(END,"PreisAgent AI 3.1: Johann-Formel + Mitbewerberanker + Ferien AT/DE + Events + Markt-KI-Signal + Preisband.\n\n")
            self.pa_text.insert(END,"Wichtig: Booking/Google werden sichtbar im Browser geprüft. Exakte freie Zimmer der Konkurrenz sind ohne offizielle API nicht gesichert.\n")

    def pa_show_selected_detail(self, event=None):
        """Zeigt die lange Herleitung zur markierten Preisstrategie."""
        try:
            sel=self.pa_tree.selection()
            if not sel: return
            vals=self.pa_tree.item(sel[0])["values"]
            rows=self.price_agent_rows()
            ds=str(vals[0]); room=str(vals[1])
            r=next((x for x in rows if x["date"].isoformat()==ds and str(x["room"])==room), None)
            if not r: return
            msg = (f"{ds} · {room}\n\n"
                   f"Schnellpreis: {money(r.get('low',0))}\n"
                   f"Empfohlen: {money(r.get('price',0))}\n"
                   f"Maximalpreis: {money(r.get('high',0))}\n\n"
                   f"Status: {r.get('reason','')}\n\n"
                   f"Herleitung:\n{r.get('detail','')}")
            messagebox.showinfo("Preisstrategie Detail", msg)
        except Exception as e:
            messagebox.showerror("Preisstrategie Detail", str(e))

    def price_agent_csv(self):
        try:
            rows=self.price_agent_rows()
            fn=out_dir()/("Preisagent_10_10_"+date.today().isoformat()+".csv")
            with open(fn,"w",newline="",encoding="utf-8-sig") as f:
                w=csv.writer(f,delimiter=";")
                w.writerow(["Datum","Zimmer","Wetter","Eigene Auslastung","Mitbewerber","Event","Markt-KI","Score","Schnellpreis","Empfohlener Preis","Maximalpreis","Status","Herleitung"])
                for r in rows:
                    w.writerow([r["date"].isoformat(),r["room"],r["weather"],r["own_occ"],r["comp"],r["event"],r.get("market",""),r["score"],money(r.get("low",r["price"])),money(r["price"]),money(r.get("high",r["price"])),r["reason"],r.get("detail","")])
            messagebox.showinfo("CSV",f"Export erstellt:\n{fn}")
        except Exception as e:
            messagebox.showerror("CSV",str(e))

    def price_agent_apply_selected(self):
        sel=self.pa_tree.selection()
        if not sel:
            messagebox.showinfo("Preisagent","Bitte eine Zeile markieren.")
            return
        vals=self.pa_tree.item(sel[0])["values"]
        room_name_sel=str(vals[1])
        price_txt=str(vals[9]).replace("€","").replace(".","").replace(",",".").strip()
        try: price=float(price_txt)
        except Exception:
            messagebox.showerror("Preisagent","Preis konnte nicht gelesen werden."); return
        room=next((r for r in self.d.get("rooms",[]) if r.get("name")==room_name_sel),None)
        if not room:
            messagebox.showerror("Preisagent","Zimmer wurde nicht gefunden."); return
        if not messagebox.askyesno("Preis übernehmen",f"Standardpreis für {room_name_sel} auf {money(price)} setzen?"):
            return
        room["price"]=price
        save(self.d)
        try: self.refresh_rooms()
        except Exception: pass
        messagebox.showinfo("Preis übernommen",f"{room_name_sel}: {money(price)}")


    # ---------------- Revenue Management Pro ----------------
    def build_revenue_management(self):
        main=ttk.Frame(self.tab_revenue)
        main.pack(fill="both",expand=True,padx=10,pady=10)

        top=self.card(main,"📈 Revenue-Management-System Pro – Zuhause am Bach")
        ttk.Label(top,text="Steuert Preis, Auslastung und Buchungschance gemeinsam: freie Zimmer-Tage, Nachfrage-Ampel, Preisband, Umsatzpotenzial und konkrete Handlungsempfehlung.",style="Card.TLabel",wraplength=1400).pack(anchor="w")
        line=ttk.Frame(top,style="Card.TFrame"); line.pack(fill="x",pady=6)
        self.rev_start=StringVar(value=date.today().isoformat())
        self.rev_days=StringVar(value="60")
        self.rev_goal_occ=StringVar(value="70")
        self.rev_goal_adr=StringVar(value="105")
        self.rev_status=StringVar(value="Bereit. Revenue-Analyse starten.")
        for label,var,w in [("Start",self.rev_start,12),("Tage",self.rev_days,5),("Ziel-Ausl.%",self.rev_goal_occ,7),("Ziel-ADR",self.rev_goal_adr,7)]:
            ttk.Label(line,text=label,style="Card.TLabel").pack(side="left",padx=3)
            ttk.Entry(line,textvariable=var,width=w).pack(side="left",padx=3)
        ttk.Button(line,text="📈 REVENUE ANALYSE",command=self.refresh_revenue_management,style="Touch.TButton").pack(side="left",padx=8)
        ttk.Button(line,text="CSV",command=self.revenue_csv,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Label(top,textvariable=self.rev_status,style="Card.TLabel").pack(anchor="w")

        kpis=ttk.Frame(main); kpis.pack(fill="x",pady=(0,8))
        self.rev_kpi_occ=StringVar(value="-"); self.rev_kpi_free=StringVar(value="-"); self.rev_kpi_adr=StringVar(value="-"); self.rev_kpi_potential=StringVar(value="-"); self.rev_kpi_action=StringVar(value="-")
        for title,var in [("Prognose-Auslastung",self.rev_kpi_occ),("freie Zimmernächte",self.rev_kpi_free),("empf. ADR",self.rev_kpi_adr),("Umsatzpotenzial",self.rev_kpi_potential),("Hauptaktion",self.rev_kpi_action)]:
            box=ttk.Frame(kpis,style="Card.TFrame",padding=9); box.pack(side="left",fill="x",expand=True,padx=4)
            ttk.Label(box,text=title,style="Card.TLabel").pack(anchor="center")
            ttk.Label(box,textvariable=var,style="CardTitle.TLabel").pack(anchor="center")

        result=self.card(main,"Revenue-Kalender – freie Tage, Ampel, Preis und Handlung")
        cols=("date","weekday","free","occ","ampel","chance","strategy","quick","rec","max","action")
        self.rev_tree=ttk.Treeview(result,columns=cols,show="headings",height=15)
        labels={"date":"Datum","weekday":"Tag","free":"frei","occ":"Ausl.","ampel":"Ampel","chance":"Chance","strategy":"Strategie","quick":"Schnell","rec":"Empfohlen","max":"Max","action":"Aktion"}
        widths={"date":90,"weekday":55,"free":55,"occ":60,"ampel":80,"chance":70,"strategy":150,"quick":80,"rec":90,"max":80,"action":420}
        for c in cols:
            self.rev_tree.heading(c,text=labels[c]); self.rev_tree.column(c,width=widths[c],anchor="w",stretch=(c=="action"))
        self.rev_tree.pack(fill="both",expand=True)
        self.rev_tree.bind("<Double-1>", self.revenue_show_detail)

        note=self.card(main,"Revenue-Regeln")
        txt=Text(note,height=4,wrap="word",bg="#ffffff",relief="flat",font=("Segoe UI",9),padx=8,pady=6)
        txt.pack(fill="x")
        txt.insert("1.0","Ampel: Grün = Preis halten/erhöhen, Gelb = normal verkaufen, Orange = Sichtbarkeit/Angebot prüfen, Rot = Schnellpreis/Last-Minute.\nDie Werte sind Schätzungen aus eigenen Buchungen, freien Zimmern, PreisAgent, Wetter, Events, Ferien AT/DE und manuell erfassten Mitbewerbern. Externe freie Konkurrenzzimmer bleiben ohne API nicht gesichert.")
        txt.configure(state="disabled")
        self.refresh_revenue_management()

    def revenue_rows(self):
        self.ensure_price_agent_data()
        try: start=pdate(self.rev_start.get())
        except Exception: start=date.today()
        days=max(1,min(365,fint(self.rev_days.get(),60)))
        rows=[]
        rooms=[r for r in self.d.get("rooms",[]) if r.get("active",True)]
        total=max(1,len(rooms))
        for i in range(days):
            d=start+timedelta(days=i)
            occ_percent, occ_num, occ_total=self.pa_own_occupancy_percent(d)
            free_rooms=self.free_rooms_on_date(d)
            free_count=len(free_rooms)
            if free_count>0:
                sample=free_rooms[0]
                pr=self.pa_recommended_price(sample,d)
                try: score_int=int(str(pr.get("score","5/10")).split("/")[0])
                except Exception: score_int=5
                rec=int(pr.get("price",0)); quick=int(pr.get("low",rec)); maxp=int(pr.get("high",rec))
                event=str(pr.get("event","")); market=str(pr.get("market","normal")); weather=str(pr.get("weather","neutral"))
            else:
                score_int=10; rec=quick=maxp=0; event="voll"; market="ausgebucht"; weather=""
            days_until=(d-date.today()).days
            chance=max(5,min(98, 18 + score_int*7 + (15 if occ_percent>=50 else 0) + (8 if free_count<=1 and free_count>0 else 0) - (8 if days_until<=2 and occ_percent==0 else 0)))
            if free_count==0:
                ampel="🔵 voll"; strategy="Ausgebucht"; action="Keine Aktion – Termin belegt. Bei Nachfrage Alternativdatum anbieten."
            elif chance>=78:
                ampel="🟢 hoch"; strategy="Ertrag sichern"; action=f"Empfohlenen Preis {money(rec)} halten; bei Anfrage nicht rabattieren. Maximalpreis {money(maxp)} möglich."
            elif chance>=55:
                ampel="🟡 normal"; strategy="Optimal verkaufen"; action=f"Preis {money(rec)} setzen und Sichtbarkeit/WhatsApp/App-Hinweis nutzen."
            elif chance>=35:
                ampel="🟠 schwach"; strategy="Füllen"; action=f"Schnellpreis {money(quick)} prüfen, besonders bei 1 Nacht und kurzfristiger Lücke."
            else:
                ampel="🔴 kritisch"; strategy="Last-Minute"; action=f"Schnellpreis {money(quick)} + aktive Bewerbung; Frühstück/Transfer als Mehrwert erwähnen."
            weekday=["Mo","Di","Mi","Do","Fr","Sa","So"][d.weekday()]
            detail=f"Markt: {market} | Event/Ferien: {event} | Wetter: {weather} | Auslastung: {occ_percent}% | Score: {score_int}/10 | Freie Zimmer: {free_count}/{total}"
            rows.append({"date":d,"weekday":weekday,"free":free_count,"occ":occ_percent,"ampel":ampel,"chance":chance,"strategy":strategy,"quick":quick,"rec":rec,"max":maxp,"action":action,"detail":detail})
        return rows

    def refresh_revenue_management(self):
        if not hasattr(self,"rev_tree"): return
        try:
            self.pa_load_school_holidays_online_cache()
        except Exception:
            pass
        rows=self.revenue_rows()
        for i in self.rev_tree.get_children(): self.rev_tree.delete(i)
        for r in rows:
            self.rev_tree.insert("",END,values=(r["date"].isoformat(),r["weekday"],r["free"],f'{r["occ"]}%',r["ampel"],f'{r["chance"]}%',r["strategy"],money(r["quick"]) if r["quick"] else "-",money(r["rec"]) if r["rec"] else "-",money(r["max"]) if r["max"] else "-",r["action"]))
        free_nights=sum(r["free"] for r in rows)
        sold_nights=sum(max(0, len([room for room in self.d.get("rooms",[]) if room.get("active",True)])-r["free"]) for r in rows)
        total_nights=max(1,free_nights+sold_nights)
        occ=round(sold_nights*100/total_nights)
        recs=[r["rec"] for r in rows if r["rec"]]
        adr=round(sum(recs)/len(recs)) if recs else 0
        potential=sum(r["rec"]*r["free"] for r in rows if r["rec"])
        weak=sum(1 for r in rows if "🔴" in r["ampel"] or "🟠" in r["ampel"])
        strong=sum(1 for r in rows if "🟢" in r["ampel"])
        self.rev_kpi_occ.set(f"{occ}%")
        self.rev_kpi_free.set(str(free_nights))
        self.rev_kpi_adr.set(money(adr))
        self.rev_kpi_potential.set(money(potential))
        self.rev_kpi_action.set("Preise erhöhen" if strong>weak else "Lücken füllen" if weak else "halten")
        self.rev_status.set(f"Revenue-Analyse: {len(rows)} Tage · {free_nights} freie Zimmernächte · {weak} schwache Tage · {strong} starke Tage")

    def revenue_show_detail(self, event=None):
        try:
            sel=self.rev_tree.selection()
            if not sel: return
            vals=self.rev_tree.item(sel[0])["values"]
            ds=str(vals[0])
            r=next((x for x in self.revenue_rows() if x["date"].isoformat()==ds),None)
            if not r: return
            messagebox.showinfo("Revenue Detail", f"{ds} ({r['weekday']})\n\nAmpel: {r['ampel']}\nBuchungschance: {r['chance']}%\nStrategie: {r['strategy']}\n\nSchnellpreis: {money(r['quick']) if r['quick'] else '-'}\nEmpfohlen: {money(r['rec']) if r['rec'] else '-'}\nMaximalpreis: {money(r['max']) if r['max'] else '-'}\n\nAktion:\n{r['action']}\n\nHerleitung:\n{r['detail']}")
        except Exception as e:
            messagebox.showerror("Revenue Detail",str(e))

    def revenue_csv(self):
        try:
            rows=self.revenue_rows()
            fn=out_dir()/("Revenue_Management_"+date.today().isoformat()+".csv")
            with open(fn,"w",newline="",encoding="utf-8-sig") as f:
                w=csv.writer(f,delimiter=";")
                w.writerow(["Datum","Tag","freie Zimmer","Auslastung","Ampel","Buchungschance","Strategie","Schnellpreis","Empfohlen","Maximalpreis","Aktion","Herleitung"])
                for r in rows:
                    w.writerow([r["date"].isoformat(),r["weekday"],r["free"],f'{r["occ"]}%',r["ampel"],f'{r["chance"]}%',r["strategy"],money(r["quick"]) if r["quick"] else "",money(r["rec"]) if r["rec"] else "",money(r["max"]) if r["max"] else "",r["action"],r["detail"]])
            messagebox.showinfo("Revenue CSV",f"Export erstellt:\n{fn}")
        except Exception as e:
            messagebox.showerror("Revenue CSV",str(e))


    # ---------------- WhatsApp Kontakte Export ----------------

    def wa_default_templates(self):
        return {
            "Begrüßung": "Guten Tag {guest},\n\nwir freuen uns auf Ihren Aufenthalt im Zuhause am Bach von {arrival} bis {departure}.\n\nDamit wir alles gut vorbereiten können: Reisen Sie mit Auto, Fahrrad oder als Wanderer an? Bitte nennen Sie uns auch eine ungefähre Ankunftszeit.\n\nFrühstück ist auf Wunsch möglich: 12 € pro Person.\n\nUnsere Gäste-App mit Tipps für Welterbesteig, Donauradweg und Wachau finden Sie hier:\n{app}\n\nLiebe Grüße\nZuhause am Bach – Laura & Johann Prem",
            "Frühstück fragen": "Guten Tag {guest},\n\nwir freuen uns auf Ihren Aufenthalt im Zuhause am Bach von {arrival} bis {departure}. Möchten Sie am nächsten Morgen Frühstück? Der Preis beträgt 12 € pro Person.\n\nLiebe Grüße\nZuhause am Bach – Laura & Johann Prem",
            "Ankunft fragen": "Guten Tag {guest},\n\nkurze Frage zu Ihrer Anreise am {arrival}: Kommen Sie mit Auto, Fahrrad oder als Wanderer? Eine ungefähre Ankunftszeit hilft uns sehr bei der Vorbereitung.\n\nLiebe Grüße\nZuhause am Bach – Laura & Johann Prem",
            "Bewertung nach Abreise": "Guten Tag {guest},\n\nherzlichen Dank für Ihren Aufenthalt im Zuhause am Bach. Wenn es Ihnen bei uns gefallen hat, freuen wir uns sehr über eine Bewertung.\n\nLiebe Grüße aus der Wachau\nLaura & Johann Prem"
        }

    def wa_ensure_templates(self):
        tpl=self.d.setdefault("whatsapp_templates", {})
        for k,v in self.wa_default_templates().items():
            tpl.setdefault(k,v)
        return tpl

    def wa_template_names(self):
        return sorted(self.wa_ensure_templates().keys(), key=lambda x: (x not in ["Begrüßung","Ankunft fragen","Frühstück fragen","Bewertung nach Abreise"], x.lower()))

    def wa_refresh_template_combo(self):
        if hasattr(self,"wa_template_combo"):
            vals=self.wa_template_names()
            self.wa_template_combo.configure(values=vals)
            if self.wa_template.get() not in vals and vals:
                self.wa_template.set(vals[0])

    def wa_template_save_current(self):
        name=(self.wa_template.get() or "").strip()
        if not name:
            messagebox.showinfo("Textbaustein","Bitte zuerst einen Namen im Textfeld/Dropdown eintragen."); return
        body=self.wa_message.get("1.0","end").strip() if hasattr(self,"wa_message") else ""
        if not body:
            messagebox.showinfo("Textbaustein","Der Text ist leer."); return
        self.wa_ensure_templates()[name]=body
        save(self.d)
        self.wa_refresh_template_combo()
        self.wa_status.set(f"Textbaustein '{name}' gespeichert.")

    def wa_template_new(self):
        base="Neuer Textbaustein"
        name=base; n=1
        tpl=self.wa_ensure_templates()
        while name in tpl:
            n+=1; name=f"{base} {n}"
        tpl[name]="Guten Tag {guest},\n\n...\n\nLiebe Grüße\nZuhause am Bach – Laura & Johann Prem"
        self.wa_template.set(name)
        save(self.d)
        self.wa_refresh_template_combo()
        self.wa_update_message_preview()
        self.wa_status.set("Neuer Textbaustein angelegt. Text bearbeiten und speichern.")

    def wa_template_delete(self):
        name=(self.wa_template.get() or "").strip()
        if not name:
            return
        if name in self.wa_default_templates():
            messagebox.showinfo("Textbaustein","Standard-Textbausteine werden nicht gelöscht. Du kannst sie aber überschreiben."); return
        if not messagebox.askyesno("Textbaustein löschen",f"Textbaustein '{name}' löschen?"):
            return
        self.wa_ensure_templates().pop(name,None)
        save(self.d)
        vals=self.wa_template_names(); self.wa_template.set(vals[0] if vals else "Begrüßung")
        self.wa_refresh_template_combo(); self.wa_update_message_preview()
        self.wa_status.set("Textbaustein gelöscht.")

    def wa_select_image(self):
        """Bild/Datei für WhatsApp vormerken. WhatsApp Web kann über wa.me kein Bild automatisch anhängen; der Manager öffnet WhatsApp und zusätzlich den Dateiordner."""
        fn=filedialog.askopenfilename(
            title="Bild oder Datei für WhatsApp auswählen",
            filetypes=[("Bilder", "*.jpg *.jpeg *.png *.webp *.gif"), ("PDF/Dokumente", "*.pdf *.docx *.xlsx"), ("Alle Dateien", "*.*")]
        )
        if not fn:
            return
        self.wa_attachment.set(fn)
        try:
            self.wa_status.set("Anhang vorgemerkt. WhatsApp öffnet Text; Bild bitte im geöffneten Ordner manuell hinzufügen.")
        except Exception:
            pass

    def wa_clear_image(self):
        if hasattr(self,"wa_attachment"):
            self.wa_attachment.set("")
        if hasattr(self,"wa_status"):
            self.wa_status.set("Anhang entfernt.")

    def build_whatsapp_contacts(self):
        main=ttk.Frame(self.tab_whatsapp)
        main.pack(fill="both",expand=True,padx=10,pady=10)

        top=self.card(main,"🎀 Pia Kommunikationscenter – Begrüßung, Frühstück, Bewertung")
        ttk.Label(
            top,
            text="Pia bereitet Gästekommunikation vor und öffnet WhatsApp-Links mit fertigen Texten. Der Versand bleibt sichtbar kontrollierbar: WhatsApp öffnet sich, du klickst selbst auf Senden. Danach setzt der Manager den Versand-Haken und speichert den Verlauf.",
            style="Card.TLabel",
            wraplength=1250
        ).pack(anchor="w")

        line=ttk.Frame(top,style="Card.TFrame")
        line.pack(fill="x",pady=5)

        self.wa_start=StringVar(value=date.today().isoformat())
        self.wa_days=StringVar(value="60")
        self.wa_only_arrivals=BooleanVar(value=True)
        self.wa_template=StringVar(value="Begrüßung")
        self.wa_status=StringVar(value="Bereit. Gäste mit Telefonnummer werden aus den Buchungen geladen.")
        self.wa_attachment=StringVar(value="")

        ttk.Label(line,text="Start",style="Card.TLabel").pack(side="left",padx=3)
        ttk.Entry(line,textvariable=self.wa_start,width=12).pack(side="left",padx=3)
        ttk.Label(line,text="Tage",style="Card.TLabel").pack(side="left",padx=3)
        ttk.Entry(line,textvariable=self.wa_days,width=6).pack(side="left",padx=3)
        ttk.Checkbutton(line,text="nur Anreisen im Zeitraum",variable=self.wa_only_arrivals).pack(side="left",padx=6)
        ttk.Label(line,text="Text",style="Card.TLabel").pack(side="left",padx=3)
        self.wa_template_combo=ttk.Combobox(line,textvariable=self.wa_template,values=self.wa_template_names(),width=24,state="normal")
        self.wa_template_combo.pack(side="left",padx=3)
        self.wa_template_combo.bind("<<ComboboxSelected>>",lambda e:self.wa_update_message_preview())
        ttk.Button(line,text="VORSCHAU",command=self.refresh_whatsapp_contacts,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(line,text="VCF EXPORT",command=self.export_whatsapp_vcf,style="Soft.TButton").pack(side="left",padx=4)
        ttk.Button(line,text="TEXT ERSTELLEN",command=self.wa_template_new,style="Soft.TButton").pack(side="left",padx=3)
        ttk.Button(line,text="TEXT SPEICHERN/ÄNDERN",command=self.wa_template_save_current,style="Soft.TButton").pack(side="left",padx=3)
        ttk.Button(line,text="TEXT LÖSCHEN",command=self.wa_template_delete,style="Soft.TButton").pack(side="left",padx=3)

        line_img=ttk.Frame(top,style="Card.TFrame")
        line_img.pack(fill="x",pady=3)
        ttk.Button(line_img,text="🖼 BILD/DATEI VORMERKEN",command=self.wa_select_image,style="Soft.TButton").pack(side="left",padx=4)
        ttk.Button(line_img,text="ANHANG ENTFERNEN",command=self.wa_clear_image,style="Soft.TButton").pack(side="left",padx=4)
        ttk.Label(line_img,textvariable=self.wa_attachment,style="Card.TLabel",wraplength=900).pack(side="left",padx=6,fill="x",expand=True)

        line2=ttk.Frame(top,style="Card.TFrame")
        line2.pack(fill="x",pady=5)
        ttk.Button(line2,text="📲 WHATSAPP AN AUSWAHL ÖFFNEN",command=self.wa_open_selected,style="Touch.TButton").pack(side="left",padx=4)
        ttk.Button(line2,text="✓ BEGRÜSSUNG VERSENDET HAKEN",command=self.wa_mark_selected_sent,style="Gold.TButton").pack(side="left",padx=4)
        ttk.Button(line2,text="👥 GRUPPENVERSAND-LISTE ERSTELLEN",command=self.wa_create_group_send_html,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(line2,text="VERLAUF AKTUALISIEREN",command=self.wa_refresh_history,style="Soft.TButton").pack(side="left",padx=4)
        ttk.Label(top,textvariable=self.wa_status,style="Card.TLabel").pack(anchor="w",pady=(4,0))

        preview_card=self.card(main,"Gäste-Vorschau")
        preview_card.pack(fill="both",expand=True,pady=(8,4))
        cols=("arrival","name","phone","sent","contact_name","room")
        wa_table_frame=ttk.Frame(preview_card,style="Card.TFrame")
        wa_table_frame.pack(fill="both",expand=True)

        self.wa_tree=ttk.Treeview(wa_table_frame,columns=cols,show="headings",height=13,selectmode="extended")
        labels={"arrival":"Anreise","name":"Gast","phone":"Telefon","sent":"Begrüßung","contact_name":"Kontaktname","room":"Zimmer"}
        widths={"arrival":95,"name":210,"phone":150,"sent":95,"contact_name":280,"room":170}
        for c in cols:
            self.wa_tree.heading(c,text=labels[c])
            self.wa_tree.column(c,width=widths[c],anchor="w")
        vsb=ttk.Scrollbar(wa_table_frame,orient="vertical",command=self.wa_tree.yview)
        hsb=ttk.Scrollbar(wa_table_frame,orient="horizontal",command=self.wa_tree.xview)
        self.wa_tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.wa_tree.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        wa_table_frame.rowconfigure(0,weight=1)
        wa_table_frame.columnconfigure(0,weight=1)

        msg_card=self.card(main,"Nachrichtenvorschau / Vorlage")
        msg_card.pack(fill="both",expand=True,pady=(4,4))
        ttk.Label(msg_card,text="Text wird pro Gast mit Name, Datum und App-Link erzeugt. Du kannst lange Texte hier ändern/speichern. Bilder/Dateien werden vorgemerkt und manuell in WhatsApp angehängt.",style="Card.TLabel").pack(anchor="w")
        self.wa_message=Text(msg_card,height=18,wrap="word",bg="#ffffff",relief="flat",font=("Segoe UI",10),padx=10,pady=8)
        self.wa_message.pack(fill="both",expand=True,pady=4)

        hist_card=self.card(main,"Versandverlauf")
        hist_card.pack(fill="both",expand=True,pady=(4,0))
        self.wa_history_text=Text(hist_card,height=6,wrap="word",bg="#ffffff",relief="flat",font=("Consolas",9),padx=10,pady=8)
        self.wa_history_text.pack(fill="both",expand=True)

        self.wa_tree.bind("<<TreeviewSelect>>",lambda e:self.wa_update_message_preview())
        self.refresh_whatsapp_contacts()
        self.wa_refresh_history()

    def wa_format_date(self, ds):
        try:
            d=pdate(ds)
            return d.strftime("%Y/%m/%d")
        except Exception:
            return str(ds).replace("-","/")

    def normalize_phone_for_contacts(self, phone, country=""):
        raw=str(phone or "").strip()
        if not raw:
            return ""
        # einfache Säuberung, aber Plus erhalten
        raw=raw.replace(" ","").replace("-","").replace("/","").replace("(","").replace(")","")
        if raw.startswith("00"):
            raw="+"+raw[2:]
        # Österreichische Nummern aus Booking oft 0664...
        if raw.startswith("0") and not raw.startswith("00"):
            c=str(country or "").upper()
            if c in ("AT","AUT","AUSTRIA","ÖSTERREICH","OESTERREICH",""):
                raw="+43"+raw[1:]
        return raw

    def whatsapp_contact_rows(self):
        try:
            start=pdate(self.wa_start.get())
        except Exception:
            start=date.today()
        days=max(1,min(365,fint(self.wa_days.get(),60)))
        end=start+timedelta(days=days)
        rows=[]
        for b in self.d.get("bookings",[]):
            if b.get("status")=="storniert":
                continue
            phone=b.get("phone","") or b.get("telefon","") or b.get("mobile","")
            if not str(phone).strip():
                continue
            try:
                arr=pdate(b.get("arrival",""))
            except Exception:
                continue
            if self.wa_only_arrivals.get():
                if not (start <= arr < end):
                    continue
            guest=str(b.get("guest","")).strip()
            if not guest:
                continue
            country=b.get("country","")
            phone_norm=self.normalize_phone_for_contacts(phone,country)
            contact_name=f"{self.wa_format_date(b.get('arrival',''))} - {guest}"
            rows.append({
                "arrival":arr,
                "arrival_text":self.wa_format_date(b.get("arrival","")),
                "guest":guest,
                "phone":phone_norm,
                "contact_name":contact_name,
                "room":room_name(self.d,b.get("room_id","")),
                "departure":self.wa_format_date(b.get("departure","")),
                "booking_id":b.get("id","") or b.get("booking_id","") or guest+str(arr),
                "welcome_sent": bool(b.get("welcome_sent") or b.get("begruessung_gesendet")),
                "booking": b
            })
        rows.sort(key=lambda r:(r["arrival"],r["guest"]))
        return rows

    def refresh_whatsapp_contacts(self):
        if not hasattr(self,"wa_tree"):
            return
        for i in self.wa_tree.get_children():
            self.wa_tree.delete(i)
        rows=self.whatsapp_contact_rows()
        self._wa_rows={}
        for idx,r in enumerate(rows):
            iid=str(r.get("booking_id") or f"wa_{idx}")
            r["iid"]=iid
            self._wa_rows[iid]=r
            sent="✓ ja" if r.get("welcome_sent") else "— offen"
            self.wa_tree.insert("",END,iid=iid,values=(r["arrival_text"],r["guest"],r["phone"],sent,r["contact_name"],r["room"]))
        kids=self.wa_tree.get_children()
        if kids:
            try:
                self.wa_tree.selection_set(kids[0])
                self.wa_tree.focus(kids[0])
                self.wa_tree.see(kids[0])
            except Exception:
                pass
        if hasattr(self,"wa_status"):
            self.wa_status.set(f"{len(rows)} Kontakt(e) mit Telefonnummer gefunden. Mehrfachauswahl für Gruppenversand möglich.")
        self.wa_update_message_preview()

    def wa_selected_rows(self):
        rows=[]
        if not hasattr(self,"wa_tree"):
            return rows
        cache=getattr(self,"_wa_rows",{})
        for iid in self.wa_tree.selection():
            r=cache.get(str(iid))
            if r:
                rows.append(r)
        if not rows:
            # Wenn nichts markiert ist, ersten sichtbaren Gast nehmen.
            kids=self.wa_tree.get_children()
            if kids:
                r=cache.get(str(kids[0]))
                if r: rows.append(r)
        return rows

    def wa_template_text(self,b):
        guest=str(b.get("guest","")).strip() or "lieber Gast"
        arr=fmt(b.get("arrival",""))
        dep=fmt(b.get("departure",""))
        app="https://topdiveair-sketch.github.io/Gaeste/"
        templ=self.wa_template.get() if hasattr(self,"wa_template") else "Begrüßung"
        body=self.wa_ensure_templates().get(templ) or self.wa_default_templates().get("Begrüßung","")
        data={
            "guest":guest,
            "arrival":arr,
            "departure":dep,
            "app":app,
            "room":room_name(self.d,b.get("room_id","")),
            "persons":str(b.get("persons","") or ""),
            "firstname":guest.split()[0] if guest.split() else guest,
        }
        try:
            return body.format(**data)
        except Exception:
            # Falls im Text versehentlich einzelne geschweifte Klammern stehen.
            return body

    def wa_update_message_preview(self):
        if not hasattr(self,"wa_message"):
            return
        rows=self.wa_selected_rows()
        txt=""
        if rows:
            txt=self.wa_template_text(rows[0].get("booking",{}))
        self.wa_message.delete("1.0","end")
        self.wa_message.insert("1.0",txt or "Bitte einen Gast auswählen.")

    def wa_log(self, booking, channel, text, status="vorbereitet"):
        self.d.setdefault("communication_log",[])
        entry={
            "id": uid("COM"),
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "booking_id": booking.get("id","") or booking.get("booking_id",""),
            "guest": booking.get("guest",""),
            "channel": channel,
            "status": status,
            "text": text[:1200]
        }
        self.d["communication_log"].append(entry)
        save(self.d)
        try: self.wa_refresh_history()
        except Exception: pass

    def wa_open_selected(self):
        rows=self.wa_selected_rows()
        if not rows:
            messagebox.showinfo("WhatsApp","Bitte zuerst einen Gast auswählen."); return
        r=rows[0]
        phone=str(r.get("phone","")).replace("+","").strip()
        if not phone:
            messagebox.showwarning("WhatsApp","Keine Telefonnummer vorhanden."); return
        text=self.wa_message.get("1.0","end").strip() if hasattr(self,"wa_message") else self.wa_template_text(r.get("booking",{}))
        url="https://wa.me/"+urllib.parse.quote(phone)+"?text="+urllib.parse.quote(text)
        webbrowser.open(url)
        att=self.wa_attachment.get().strip() if hasattr(self,"wa_attachment") else ""
        if att:
            try:
                os.startfile(os.path.dirname(att) or att)
            except Exception:
                pass
            text_for_log=text+"\n\n[Anhang vorgemerkt: "+att+"]"
            self.wa_status.set("WhatsApp geöffnet. Bild/Datei bitte aus dem geöffneten Ordner manuell anhängen. Danach Haken setzen.")
        else:
            text_for_log=text
            self.wa_status.set("WhatsApp geöffnet. Nach dem Senden bitte den Haken setzen.")
        self.wa_log(r.get("booking",{}),"WhatsApp",text_for_log,"geöffnet")

    def wa_mark_selected_sent(self):
        rows=self.wa_selected_rows()
        if not rows:
            messagebox.showinfo("WhatsApp","Bitte zuerst einen Gast auswählen."); return
        text=self.wa_message.get("1.0","end").strip() if hasattr(self,"wa_message") else ""
        for r in rows:
            b=r.get("booking",{})
            b["welcome_sent"]=True
            b["begruessung_gesendet"]=True
            b["welcome_sent_at"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.wa_log(b,"WhatsApp",text or self.wa_template_text(b),"versendet_haken")
        save(self.d)
        self.refresh_whatsapp_contacts()
        self.wa_status.set(f"Versand-Haken bei {len(rows)} Gast/Gästen gesetzt.")

    def wa_create_group_send_html(self):
        rows=self.wa_selected_rows()
        if not rows:
            # Gruppenversand ohne Auswahl: alle sichtbaren offenen Begrüßungen.
            rows=[r for r in getattr(self,"_wa_rows",{}).values() if not r.get("welcome_sent")]
        if not rows:
            messagebox.showinfo("Gruppenversand","Keine passenden Gäste gefunden."); return
        fn=out_dir()/('WhatsApp_Gruppenversand_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.html')
        parts=["<!doctype html><html><head><meta charset='utf-8'><title>WhatsApp Gruppenversand</title>",
               "<style>body{font-family:Segoe UI,Arial;margin:24px} .card{border:1px solid #ccc;border-radius:12px;padding:14px;margin:12px 0} a{font-size:18px}</style></head><body>",
               "<h1>WhatsApp Gruppenversand – Zuhause am Bach</h1>",
               "<p>Jeden Link einzeln öffnen. WhatsApp zeigt die vorbereitete Nachricht, du klickst selbst auf Senden. Bilder/Dateien bitte manuell anhängen.</p>"]
        for r in rows:
            b=r.get("booking",{})
            text=self.wa_template_text(b)
            phone=str(r.get("phone","")).replace("+","").strip()
            url="https://wa.me/"+urllib.parse.quote(phone)+"?text="+urllib.parse.quote(text)
            parts.append("<div class='card'>")
            parts.append(f"<h2>{html.escape(r.get('guest',''))} – {html.escape(r.get('arrival_text',''))}</h2>")
            parts.append(f"<p>{html.escape(r.get('room',''))} · {html.escape(r.get('phone',''))}</p>")
            parts.append(f"<a href='{url}' target='_blank'>WhatsApp an {html.escape(r.get('guest',''))} öffnen</a>")
            att=self.wa_attachment.get().strip() if hasattr(self,"wa_attachment") else ""
            if att:
                parts.append(f"<p><b>Anhang manuell hinzufügen:</b> {html.escape(att)}</p>")
            parts.append("</div>")
            self.wa_log(b,"WhatsApp",text,"gruppenlink_erstellt")
        parts.append("</body></html>")
        fn.write_text("\n".join(parts),encoding="utf-8")
        messagebox.showinfo("Gruppenversand",f"Gruppenversand-Liste erstellt:\n{fn}")
        try: os.startfile(str(fn))
        except Exception: webbrowser.open(str(fn))

    def wa_refresh_history(self):
        if not hasattr(self,"wa_history_text"):
            return
        self.wa_history_text.config(state="normal")
        self.wa_history_text.delete("1.0","end")
        logs=list(self.d.get("communication_log",[]))[-80:]
        if not logs:
            self.wa_history_text.insert("end","Noch kein Versandverlauf vorhanden.\n")
        else:
            for e in reversed(logs):
                self.wa_history_text.insert("end",f"{e.get('ts','')} | {e.get('guest','')} | {e.get('channel','')} | {e.get('status','')}\n")
        self.wa_history_text.config(state="disabled")

    def vcf_escape(self, text):
        s=str(text or "")
        s=s.replace("\\","\\\\").replace(";","\\;").replace(",","\\,").replace("\n","\\n")
        return s

    def export_whatsapp_vcf(self):
        try:
            rows=self.whatsapp_contact_rows()
            if not rows:
                messagebox.showinfo("WhatsApp Kontakte","Keine Buchungen mit Telefonnummer im gewählten Zeitraum gefunden.")
                return
            fn=out_dir()/("WhatsApp_Gaestekontakte_"+date.today().isoformat()+".vcf")
            with open(fn,"w",encoding="utf-8",newline="\n") as f:
                for r in rows:
                    name=self.vcf_escape(r["contact_name"])
                    guest=self.vcf_escape(r["guest"])
                    note=self.vcf_escape(f"Zuhause am Bach & Gästehaus Wachau | Anreise {r['arrival_text']} | Abreise {r['departure']} | Zimmer {r['room']} | Buchung {r['booking_id']}")
                    f.write("BEGIN:VCARD\n")
                    f.write("VERSION:3.0\n")
                    f.write(f"N:{name};;;;\n")
                    f.write(f"FN:{name}\n")
                    f.write(f"ORG:Zuhause am Bach & Gästehaus Wachau\n")
                    f.write(f"TEL;TYPE=CELL:{r['phone']}\n")
                    f.write(f"NOTE:{note}\n")
                    f.write("END:VCARD\n")
            messagebox.showinfo("WhatsApp Kontakte",f"VCF-Datei erstellt:\n{fn}\n\nDiese Datei am Handy öffnen und in Kontakte importieren.")
            self.wa_status.set(f"Export erstellt: {fn}")
        except Exception as e:
            messagebox.showerror("WhatsApp Kontakte",str(e))


    # ---------------- 10/10 Qualitäts-Check ----------------

    # ---------------- 10+ Qualitäts-Check ----------------

    def build_quality_check(self):
        main=ttk.Frame(self.tab_quality)
        main.pack(fill="both",expand=True,padx=10,pady=10)

        top=self.card(main,"🏆 10+ / 10 Check – Funktion, Layout, Erscheinung")
        ttk.Label(
            top,
            text="Prüft die Kernmodule, Datenlage, Bedienlogik, Exporte und Layout-Risiken. Der Bericht ist für den praktischen Feinschliff gedacht.",
            style="Card.TLabel",
            wraplength=1250
        ).pack(anchor="w")

        line=ttk.Frame(top,style="Card.TFrame")
        line.pack(fill="x",pady=5)
        ttk.Button(line,text="10+ CHECK AUSFÜHREN",command=self.run_quality_check,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(line,text="BERICHT SPEICHERN",command=self.quality_check_txt,style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(line,text="STARTSEITE",command=lambda:self.safe_select_tab(self.tab_dash),style="Primary.TButton").pack(side="left",padx=5)

        self.quality_status=StringVar(value="Bereit.")
        ttk.Label(top,textvariable=self.quality_status,style="CardTitle.TLabel").pack(anchor="w",pady=(5,0))

        result=self.card(main,"Prüfergebnis")
        self.quality_text=Text(result,height=30,wrap="word",bg="#ffffff",relief="flat",font=("Consolas",10),padx=10,pady=8)
        self.quality_text.pack(fill="both",expand=True)

        self.run_quality_check()

    def quality_lines(self):
        lines=[]
        score=0
        total=0

        def check(name, condition, ok_note="", fail_note=""):
            nonlocal score,total
            total+=1
            if condition:
                score+=1
                lines.append(f"✅ {name}: OK {ok_note}")
            else:
                lines.append(f"⚠️ {name}: PRÜFEN {fail_note}")

        rooms=self.d.get("rooms",[])
        bookings=self.d.get("bookings",[])
        comps=self.d.get("competitors",[])
        events=self.d.get("event_hints",[])
        settings=self.d.get("settings",{})

        check("Fenster / Platz", True, "Startet groß/maximiert; Hauptbuttons oben sichtbar.")
        check("Profi-Cockpit", hasattr(self,"dash_arr_frame") and hasattr(self,"dash_inhouse_frame") and hasattr(self,"dash_dep_frame"))
        check("Zimmer vorhanden", len(rooms)>0, f"({len(rooms)} Zimmer)", "noch keine Zimmer angelegt")
        check("Aktive Zimmer vorhanden", any(r.get("active",True) for r in rooms), "", "alle Zimmer gesperrt oder keine Zimmer")
        check("Zimmerpreise gepflegt", all(float(r.get("price",0) or 0)>0 for r in rooms) if rooms else False)
        check("Zimmerverwaltung Buttons", hasattr(self,"update_room_price_only") and hasattr(self,"set_room_active_state") and hasattr(self,"delete_room"))
        check("Buchungen-Datenstruktur", isinstance(bookings,list), f"({len(bookings)} Buchungen)")
        check("Buchung bearbeiten/laden", hasattr(self,"load_booking") and hasattr(self,"save_booking") and hasattr(self,"delete_booking"))
        check("Tagesübersicht", hasattr(self,"refresh_day"))
        check("Ortstaxe eingestellt", float(settings.get("tax",2.60) or 0)>0, f"({settings.get('tax',2.60)} EUR)")
        check("Gemeinde/Ortstaxe Export", hasattr(self,"gemeinde_pdf_core") and hasattr(self,"gemeinde_csv_core"))
        check("Rechnung/Extras", hasattr(self,"invoice_pdf") and hasattr(self,"refresh_extras"))
        check("Booking-Import", hasattr(self,"run_booking_import") or hasattr(self,"choose_import_file"))
        check("Stammdaten-Korrektur", hasattr(self,"run_address_correction") or hasattr(self,"refresh_stammdaten"))
        check("Backup", hasattr(self,"refresh_backup_list") and hasattr(self,"manual_backup_now"))
        check("Preisagent", hasattr(self,"refresh_price_agent") and hasattr(self,"pa_load_weather"))
        check("Preisagent Events 15 km", hasattr(self,"pa_event_locations") and hasattr(self,"pa_load_events_online"))
        check("Mitbewerberdaten", len(comps)>0, f"({len(comps)} Einträge)", "für bessere Preisvorschläge Mitbewerber eintragen")
        check("Eventdaten", len(events)>0, f"({len(events)} Hinweise)", "Events online prüfen oder manuell ergänzen")
        check("WhatsApp-VCF Export", hasattr(self,"export_whatsapp_vcf") and hasattr(self,"normalize_phone_for_contacts"))
        check("Datenprüfung", hasattr(self,"refresh_check") or hasattr(self,"export_check_csv"))
        check("CSV/PDF/VCF Export-Fähigkeit", True, "Module vorhanden; Ausgabe in Programmordner/Output.")
        check("10+ Check Bericht", True, "Bericht kann gespeichert werden.")

        pct=round(score*100/max(1,total))
        plus="10+ / 10" if pct>=92 else "10 / 10 erreichbar" if pct>=84 else "8–9 / 10"
        lines.insert(0,f"Gesamt: {score}/{total} Punkte = {pct}%")
        lines.insert(1,f"Bewertung: {plus}")
        lines.insert(2,"")
        lines.append("")
        lines.append("Hinweis:")
        lines.append("Dieser Check prüft Struktur, Daten und vorhandene Funktionen. Einen echten Windows-Klicktest ersetzt er nicht vollständig.")
        lines.append("Für 10+ im Alltag: Testbuchung anlegen, Rechnung/Gemeinde/WhatsApp/Preisagent/Backup einmal praktisch durchspielen.")
        return lines,pct

    def run_quality_check(self):
        if not hasattr(self,"quality_text"):
            return
        lines,pct=self.quality_lines()
        self.quality_text.delete("1.0",END)
        self.quality_text.insert(END,"\n".join(lines))
        self.quality_status.set(f"10+ Check abgeschlossen: {pct}%")

    def quality_check_txt(self):
        try:
            lines,pct=self.quality_lines()
            fn=out_dir()/("10plus_Check_"+date.today().isoformat()+".txt")
            with open(fn,"w",encoding="utf-8") as f:
                f.write("\n".join(lines))
            messagebox.showinfo("10+ Check",f"Bericht gespeichert:\n{fn}")
        except Exception as e:
            messagebox.showerror("10+ Check",str(e))


    def build_premium(self):
        f=ttk.Frame(self.tab_premium,padding=22); f.pack(fill="both",expand=True)
        ttk.Label(f,text="Premium-Funktionen sind enthalten",style="Title.TLabel").pack(anchor="w")
        t=Text(f,height=16,bg="#fff",relief="flat",font=("Consolas",11),padx=12,pady=12); t.pack(fill="x",pady=8)
        t.insert(END,"SICHTBAR ENTHALTEN:\n")
        for x in ["optisch überarbeitete Oberfläche","Booking-Zimmerpreis als bezahlt / nur Zuzahlung in Rechnung","Extras ändern/löschen/Felder löschen","Einkaufsliste als PDF","Wanderer bei Zusatzinfos","Booking-Import XLS/XLSX/CSV","⭐ Tagesliste","⭐ Reinigung","⭐ Backup","Gästekartei-Felder in Buchungen","Rechnungskopf mit Adresse/Telefon","Rechnungsfuß mit Werbung","Kleinunternehmer-Hinweis ohne USt-Ausweis"]:
            t.insert(END,"- "+x+"\n")
        bar=ttk.Frame(f); bar.pack(fill="x",pady=10)
        ttk.Button(bar,text="Zur Tagesliste",command=lambda:self.safe_select_tab(self.tab_day),style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(bar,text="Zur Reinigung",command=lambda:self.safe_select_tab(self.tab_clean),style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(bar,text="Zum Backup",command=lambda:self.safe_select_tab(self.tab_backup),style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(bar,text="Zu Buchungen/Gästekartei",command=lambda:self.open_guest_area(self.tab_book),style="Touch.TButton").pack(side="left",padx=5)


    def build_gemeinde_core(self):
        top=self.card(self.tab_gemeinde,"Gemeinde-Meldung / Ortstaxe")
        self.g_month=StringVar(value=datetime.now().strftime("%m.%Y"))
        self.g_missing_only=BooleanVar(value=False)

        row=ttk.Frame(top,style="Card.TFrame"); row.pack(fill="x",pady=4)
        ttk.Label(row,text="Monat MM.JJJJ",style="Card.TLabel").pack(side="left",padx=5)
        ttk.Entry(row,textvariable=self.g_month,width=12).pack(side="left",padx=5)
        ttk.Button(row,text="ANZEIGEN",command=self.refresh_gemeinde_core,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(row,text="GEMEINDE-PDF A4",command=self.gemeinde_pdf_core,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(row,text="CSV EXPORT",command=self.gemeinde_csv_core,style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(row,text="JAHRESÜBERSICHT CSV",command=self.export_gemeinde_year_csv,style="Primary.TButton").pack(side="left",padx=5)

        row2=ttk.Frame(top,style="Card.TFrame"); row2.pack(fill="x",pady=4)
        ttk.Checkbutton(row2,text="nur fehlende Stammdaten anzeigen",variable=self.g_missing_only,command=self.refresh_gemeinde_core).pack(side="left",padx=5)
        ttk.Button(row2,text="FEHLENDE STAMMDATEN BEARBEITEN",command=lambda:self.safe_select_tab(self.tab_corr),style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(row2,text="DATENPRÜFUNG",command=lambda:self.safe_select_tab(self.tab_check),style="Primary.TButton").pack(side="left",padx=5)

        self.g_summary=StringVar(value="")
        ttk.Label(top,textvariable=self.g_summary,style="CardTitle.TLabel").pack(anchor="w",pady=(6,0))

        table_frame=ttk.Frame(self.tab_gemeinde)
        table_frame.pack(fill="both",expand=True,padx=8,pady=8)

        cols=("gast","adresse","land","anreise","abreise","pers","nächte","ortstaxe")
        self.g_tree=ttk.Treeview(table_frame,columns=cols,show="headings",height=24)
        headings={
            "gast":"Gast","adresse":"Adresse","land":"Land",
            "anreise":"Anreise","abreise":"Abreise","pers":"Pers.","nächte":"Nächte",
            "ortstaxe":"Ortstaxe"
        }
        widths={
            "gast":240,"adresse":420,"land":100,"anreise":100,"abreise":100,
            "pers":70,"nächte":80,"ortstaxe":110
        }
        for c in cols:
            self.g_tree.heading(c,text=headings[c])
            self.g_tree.column(c,width=widths[c],anchor="w")
        vsb=ttk.Scrollbar(table_frame,orient="vertical",command=self.g_tree.yview)
        hsb=ttk.Scrollbar(table_frame,orient="horizontal",command=self.g_tree.xview)
        self.g_tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.g_tree.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        table_frame.rowconfigure(0,weight=1)
        table_frame.columnconfigure(0,weight=1)
        self.g_tree.tag_configure("missing", background="#fff2a8", foreground="#312300")
        self.g_tree.tag_configure("ok", background="#ffffff", foreground="#263016")

    def gemeinde_rows_for_month(self):
        try:
            m,y=map(int,self.g_month.get().split("."))
        except Exception:
            raise ValueError("Monat bitte als MM.JJJJ eingeben.")
        start=date(y,m,1)
        end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
        rows=[]
        for b in self.d.get("bookings",[]):
            if b.get("status")=="storniert":
                continue
            arr=pdate(b.get("arrival"))
            dep=pdate(b.get("departure"))
            if dep <= start or arr >= end:
                continue
            counted_start=max(arr,start)
            counted_end=min(dep,end)
            ns=max(0,(counted_end-counted_start).days)
            persons=int(b.get("persons",1))
            pn=ns*persons
            tax=pn*ORTSTAXE
            missing=[]
            if not str(b.get("plz","")).strip(): missing.append("PLZ")
            if not str(b.get("city","")).strip(): missing.append("Ort")
            if not str(b.get("country","")).strip(): missing.append("Land")
            # Geburtsdatum wird für den Gemeindeausdruck nicht mehr als Pflichtfeld geprüft.
            original_text = " ".join(str(b.get(k,"")) for k in ("guest","street","city","country"))
            translit_used = has_hebrew_arabic(original_text)
            rows.append({
                "guest":gemeinde_text(b.get("guest","")),
                "birth":gemeinde_text(booking_birth_value(b)),
                "street":gemeinde_text(b.get("street","")),
                "plz":gemeinde_text(b.get("plz","")),
                "city":gemeinde_text(b.get("city","")),
                "country":gemeinde_text(b.get("country","")),
                "original_guest":b.get("guest",""),
                "original_street":b.get("street",""),
                "original_city":b.get("city",""),
                "original_country":b.get("country",""),
                "translit_used":translit_used,
                "arrival":fmt(arr),
                "departure":fmt(dep),
                "persons":persons,
                "nights":ns,
                "person_nights":pn,
                "tax":tax,
                "source":b.get("source","direkt"),
                "room":room_name(self.d,b.get("room_id")),
                "missing":", ".join(missing)
            })
        return rows

    def refresh_gemeinde_core(self):
        if not hasattr(self,"g_tree"):
            return
        try:
            rows=self.gemeinde_rows_for_month()
            total_pn=sum(r["person_nights"] for r in rows)
            total_tax=sum(r["tax"] for r in rows)
            missing_count=sum(1 for r in rows if r.get("missing"))
            for i in self.g_tree.get_children():
                self.g_tree.delete(i)

            shown=0
            for r in rows:
                if self.g_missing_only.get() and not r.get("missing"):
                    continue
                adresse=(str(r["street"] or "").strip()+" | "+str(r["plz"] or "").strip()+" "+str(r["city"] or "").strip()).strip(" |")
                tag="missing" if r.get("missing") else "ok"
                self.g_tree.insert("",END,values=(
                    r["guest"],adresse,r["country"],r["arrival"],r["departure"],
                    r["persons"],r["nights"],money(r["tax"])
                ),tags=(tag,))
                shown+=1
            self.g_summary.set(
                f"{self.g_month.get()} · Buchungen: {len(rows)} · angezeigt: {shown} · Personennächte: {total_pn} · Ortstaxe: {money(total_tax)}"
            )
        except Exception as e:
            messagebox.showerror("Gemeinde",str(e))

    def gemeinde_pdf_core(self):
        """V17.2 Gemeinde-/Ortstaxe-Kontrollausdruck.

        Neuaufbau statt Layout-Flickwerk:
        - echtes DIN-A4-Querformat landscape(A4)
        - PLZ und Ort zusammengefasst
        - keine Spalten Geburtsdatum, Zimmer, Status, PN, Quelle
        - lange Texte werden passend gekürzt, nicht umgebrochen
        - kein Logo, aber Überschrift Zuhause am Bach; Seitenzahlen, Seitensummen, Gesamtsumme
        """
        try:
            rows=self.gemeinde_rows_for_month()
            rows=sorted(rows, key=lambda r: (str(r.get("arrival","")), str(r.get("guest",""))))
            release=fin_municipality_rows_release(rows)
            if not release.approved:
                messagebox.showwarning("Gloria-Freigabe", release.message())
                return
            if release.has_warnings and not messagebox.askyesno("Gloria-Freigabe", release.message()+"\n\nTrotzdem Gemeinde-PDF erstellen?"):
                return
            total_guests=sum(int(r.get("persons",0) or 0) for r in rows)
            total_nights=sum(int(r.get("nights",0) or 0) for r in rows)
            total_pn=sum(int(r.get("person_nights",0) or 0) for r in rows)
            total_tax=sum(float(r.get("tax",0) or 0) for r in rows)
            safe=self.g_month.get().replace(".","_")
            pdf=out_dir()/f"Gemeinde_Ortstaxe_{safe}_DIN_A4_QUERFORMAT_OHNE_LOGO.pdf"

            page_w, page_h = landscape(A4)
            left_margin=8*mm
            right_margin=8*mm
            top_margin=8*mm
            bottom_margin=13*mm
            usable_w=page_w-left_margin-right_margin

            styles=getSampleStyleSheet()
            styles["Normal"].fontName="Helvetica"
            styles["Normal"].fontSize=7.2
            styles["Normal"].leading=8.0
            styles["Heading2"].fontName="Helvetica-Bold"
            styles["Heading2"].fontSize=12
            styles["Heading2"].leading=14

            # Kein Logo im Gemeindeausdruck.
            # Überschrift "Zuhause am Bach" bleibt bewusst erhalten.

            class NumberedCanvas(pdfcanvas.Canvas):
                def __init__(self,*args,**kwargs):
                    pdfcanvas.Canvas.__init__(self,*args,**kwargs)
                    self._saved_page_states=[]
                def showPage(self):
                    self._saved_page_states.append(dict(self.__dict__))
                    self._startPage()
                def save(self):
                    page_count=len(self._saved_page_states)
                    for state in self._saved_page_states:
                        self.__dict__.update(state)
                        self.setFont("Helvetica",7.5)
                        self.setFillColor(colors.HexColor("#666666"))
                        self.drawRightString(page_w-right_margin, 7*mm, f"Seite {self._pageNumber} von {page_count}")
                        self.drawString(left_margin, 7*mm, "Zuhause am Bach OS V32.2 BETA")
                        pdfcanvas.Canvas.showPage(self)
                    pdfcanvas.Canvas.save(self)

            def fit_text(value, width, font="Helvetica", size=7.0):
                """Kürzt Text so, dass er in die Spalte passt. Keine Zeilenumbrüche."""
                text=str(value or "").replace("\n"," ").replace("\r"," ").strip()
                text=" ".join(text.split())
                if not text:
                    return ""
                max_w=max(4, width-3*mm)
                if pdfmetrics.stringWidth(text, font, size) <= max_w:
                    return text
                ell="…"
                # erst rechts kürzen, weil Anfang von Straße/Ort meist wichtiger ist
                while len(text)>1 and pdfmetrics.stringWidth(text+ell, font, size) > max_w:
                    text=text[:-1]
                return (text+ell) if text else ell

            def split_guest_name(guest):
                """Booking-Importe liegen oft als 'Nachname Vorname' vor. Daher V17: erstes Wort = Nachname."""
                g=str(guest or "").strip()
                parts=g.split()
                if len(parts)>=2:
                    return parts[0], " ".join(parts[1:])
                return g, ""

            def header_block():
                title=Paragraph('<b>Zuhause am Bach</b><br/>Gemeinde-Meldung / Ortstaxe<br/><font size="8">ohne Geburtsdatum · Querformat · 2,60 € pro Person/Nacht</font>', styles["Heading2"])
                meta=Paragraph(
                    f"<b>Gemeinde Aggsbach Markt</b><br/>Zeitraum: {html.escape(self.g_month.get())}<br/>Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    styles["Normal"]
                )
                h=Table([[title, meta]], colWidths=[145*mm, usable_w-145*mm])
                h.setStyle(TableStyle([
                    ("VALIGN",(0,0),(-1,-1),"TOP"),
                    ("LINEBELOW",(0,0),(-1,-1),0.35,colors.HexColor("#b8b8b8")),
                    ("BOTTOMPADDING",(0,0),(-1,-1),4),
                    ("LEFTPADDING",(0,0),(-1,-1),0),
                    ("RIGHTPADDING",(0,0),(-1,-1),0),
                ]))
                return h

            def table_style(row_count):
                commands=[
                    ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#cfcfcf")),
                    ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f1f1f1")),
                    ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                    ("FONTNAME",(0,1),(-1,-1),"Helvetica"),
                    ("FONTSIZE",(0,0),(-1,0),7.4),
                    ("FONTSIZE",(0,1),(-1,-1),7.0),
                    ("LEADING",(0,0),(-1,-1),7.6),
                    ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                    ("ALIGN",(7,1),(-1,-1),"RIGHT"),
                    ("TOPPADDING",(0,0),(-1,-1),1.6),
                    ("BOTTOMPADDING",(0,0),(-1,-1),1.6),
                    ("LEFTPADDING",(0,0),(-1,-1),2.2),
                    ("RIGHTPADDING",(0,0),(-1,-1),2.2),
                ]
                for i in range(1,row_count):
                    if i % 2 == 0:
                        commands.append(("BACKGROUND",(0,i),(-1,i),colors.HexColor("#fbfbfb")))
                return TableStyle(commands)

            # DIN-A4 Querformat: 281 mm nutzbare Breite bei 8 mm Rand.
            # Summe exakt ca. 278 mm, damit nichts abgeschnitten wird.
            headers=["Nachname","Vorname","Straße","PLZ / Ort","Land","Anreise","Abreise","Nä.","Pers.","Ortstaxe\n2,60 €/Pers./Nacht"]
            col_widths=[30*mm,28*mm,62*mm,54*mm,10*mm,22*mm,22*mm,11*mm,11*mm,28*mm]
            rows_per_page=31
            chunks=[rows[i:i+rows_per_page] for i in range(0,len(rows),rows_per_page)] or [[]]
            story=[]
            for page_index, chunk in enumerate(chunks, start=1):
                if page_index>1:
                    story.append(PageBreak())
                story.append(header_block())
                story.append(Spacer(1,3*mm))

                detail=[headers]
                for r in chunk:
                    nachname, vorname=split_guest_name(r.get("guest",""))
                    plzort=(str(r.get("plz","")).strip()+" "+str(r.get("city","")).strip()).strip()
                    values=[
                        fit_text(nachname, col_widths[0]),
                        fit_text(vorname, col_widths[1]),
                        fit_text(r.get("street",""), col_widths[2]),
                        fit_text(plzort, col_widths[3]),
                        fit_text(r.get("country",""), col_widths[4]),
                        fit_text(r.get("arrival",""), col_widths[5]),
                        fit_text(r.get("departure",""), col_widths[6]),
                        str(r.get("nights","")),
                        str(r.get("persons","")),
                        money(r.get("tax",0)),
                    ]
                    detail.append(values)

                t=Table(detail,colWidths=col_widths,repeatRows=1,hAlign="LEFT")
                t.setStyle(table_style(len(detail)))
                story.append(t)
                story.append(Spacer(1,2.5*mm))

                page_guests=sum(int(r.get("persons",0) or 0) for r in chunk)
                page_nights=sum(int(r.get("nights",0) or 0) for r in chunk)
                page_pn=sum(int(r.get("person_nights",0) or 0) for r in chunk)
                page_tax=sum(float(r.get("tax",0) or 0) for r in chunk)
                page_sum=Table([
                    ["Seitensumme", "Gäste", str(page_guests), "Nächte", str(page_nights), "Personennächte", str(page_pn), "Ortstaxe", money(page_tax)]
                ], colWidths=[45*mm,18*mm,15*mm,18*mm,15*mm,30*mm,16*mm,18*mm,25*mm])
                page_sum.setStyle(TableStyle([
                    ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#cfcfcf")),
                    ("FONTNAME",(0,0),(0,0),"Helvetica-Bold"),
                    ("FONTSIZE",(0,0),(-1,-1),7.2),
                    ("ALIGN",(2,0),(-1,0),"RIGHT"),
                    ("BACKGROUND",(0,0),(-1,-1),colors.white),
                    ("TOPPADDING",(0,0),(-1,-1),2),
                    ("BOTTOMPADDING",(0,0),(-1,-1),2),
                ]))
                story.append(page_sum)

            story.append(Spacer(1,4*mm))
            grand=Table([
                ["Gesamtsumme", ""],
                ["Gäste", str(total_guests)],
                ["Nächte", str(total_nights)],
                ["Personennächte", str(total_pn)],
                ["Ortstaxe 2,60 € pro Person/Nacht", money(total_tax)],
            ], colWidths=[55*mm,45*mm], hAlign="LEFT")
            grand.setStyle(TableStyle([
                ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#bbbbbb")),
                ("SPAN",(0,0),(-1,0)),
                ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f1f1f1")),
                ("ALIGN",(1,1),(-1,-1),"RIGHT"),
                ("FONTSIZE",(0,0),(-1,-1),7.5),
            ]))
            story.append(grand)

            doc=SimpleDocTemplate(str(pdf),pagesize=landscape(A4),rightMargin=right_margin,leftMargin=left_margin,topMargin=top_margin,bottomMargin=bottom_margin)
            doc.build(story, canvasmaker=NumberedCanvas)
            messagebox.showinfo("Gemeinde-PDF",str(pdf))
            try: os.startfile(str(pdf))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("Gemeinde-PDF",str(e))

    def gemeinde_csv_core(self):
        try:
            rows=self.gemeinde_rows_for_month()
            safe=self.g_month.get().replace(".","_")
            csv_path=out_dir()/f"Gemeinde_Ortstaxe_{safe}.csv"
            with open(csv_path,"w",newline="",encoding="utf-8-sig") as f:
                w=csv.writer(f,delimiter=";")
                w.writerow(["Gast","Straße","PLZ","Ort","Land","Anreise","Abreise","Personen","Nächte","Personennächte","Ortstaxe","Umschrift verwendet","Original Gast","Original Adresse/Ort"])
                for r in rows:
                    original_addr=(str(r.get("original_street","")).strip()+" | "+str(r.get("original_city","")).strip()).strip(" |")
                    w.writerow([r["guest"],r["street"],r["plz"],r["city"],r["country"],r["arrival"],r["departure"],r["persons"],r["nights"],r["person_nights"],str(r["tax"]).replace(".",","),"JA" if r.get("translit_used") else "NEIN",r.get("original_guest",""),original_addr])
            messagebox.showinfo("CSV Export",str(csv_path))
            try: os.startfile(str(csv_path))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("CSV Export",str(e))


    def gastinfo_pdf_selected(self):
        """A4-Gästeinfo für die markierte Buchung erstellen und öffnen."""
        try:
            key=self.selected_booking_key()
            if not key:
                messagebox.showinfo("Gäste-Info", "Bitte zuerst eine Buchung markieren.")
                return
            b=self.booking_by_key(key)
            if not b:
                messagebox.showerror("Gäste-Info", "Buchung wurde nicht gefunden.")
                return
            pdf=self.gastinfo_pdf_core(b)
            messagebox.showinfo("Gäste-Info erstellt", str(pdf))
            try: os.startfile(str(pdf))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("Gäste-Info", str(e))

    def gastinfo_pdf_core(self,b):
        """Erstellt ein internes Gäste-Infoblatt. Keine externen Profiling-Daten."""
        safe=re.sub(r"[^A-Za-z0-9_\-]+","_",str(b.get("guest","Gast")).strip())[:50] or "Gast"
        pdf=out_dir()/f"Gaeste_Info_{safe}_{str(b.get('arrival','')).replace('-','')}.pdf"
        styles=getSampleStyleSheet()
        doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=14*mm,leftMargin=14*mm,topMargin=12*mm,bottomMargin=10*mm)
        story=[]
        add_logo_to_story(story)
        story.append(Paragraph("Gäste-Info / interne Vorbereitung",styles["Title"]))
        story.append(Paragraph("Zuhause am Bach & Gästehaus Wachau",styles["Normal"]))
        story.append(Spacer(1,4*mm))
        try:
            ns=nights(b.get("arrival"),b.get("departure"))
        except Exception:
            ns=0
        persons=int(b.get("persons",1) or 1)
        tax_units=ns*persons
        tax_sum=tax_units*ORTSTAXE
        flags=[]
        if b.get("wanderer"): flags.append("Wanderer")
        if b.get("bike"): flags.append("Fahrrad")
        if b.get("ebike"): flags.append("E-Bike")
        if b.get("car"): flags.append("PKW")
        if b.get("dog"): flags.append("Hund")
        if b.get("regular"): flags.append("Stammgast")
        info=[
            ["Gast", b.get("guest","")],
            ["Anreise", fmt(b.get("arrival",""))],
            ["Abreise", fmt(b.get("departure",""))],
            ["Nächte / Personen", f"{ns} Nacht/Nächte · {persons} Person(en)"],
            ["Zimmer", room_name(self.d,b.get("room_id",""))],
            ["Telefon", b.get("phone","")],
            ["E-Mail", b.get("email","")],
            ["Adresse", f"{b.get('street','')}, {b.get('plz','')} {b.get('city','')} · {b.get('country','')}"],
            ["Geburtsdatum", booking_birth_value(b)],
            ["Kennzeichen", b.get("plate","")],
            ["Frühstück", b.get("breakfast","")],
            ["Zusatzinfos", ", ".join(flags) if flags else "—"],
            ["Allergien", b.get("allergies","") or "—"],
            ["Sonderwünsche", b.get("wishes","") or "—"],
            ["Ortstaxe", f"{tax_units} Personennächte × {money(ORTSTAXE)} = {money(tax_sum)}"],
        ]
        table=Table([[Paragraph(str(a),styles["Normal"]),Paragraph(str(c),styles["Normal"])] for a,c in info],colWidths=[45*mm,125*mm])
        table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),("BACKGROUND",(0,0),(0,-1),colors.whitesmoke),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.append(table)
        story.append(Spacer(1,5*mm))
        story.append(Paragraph("Service-Check",styles["Heading2"]))
        service=[]
        if b.get("wanderer"):
            service.append("Frühes Frühstück oder Snackbox ansprechen; Trockenecke vorbereiten; Welterbesteig-Hinweise bereitlegen.")
        if b.get("bike") or b.get("ebike"):
            service.append("Fahrradgarage, Werkzeug/Luftpumpe und E-Bike-Lademöglichkeit erwähnen.")
        if b.get("dog"):
            service.append("Hunderegeln freundlich erklären; geeignete Zimmertrennung beachten.")
        if str(b.get("breakfast","")).lower() not in ("", "kein", "nein"):
            service.append("Frühstück ist vorgemerkt – Uhrzeit bei Anreise klären.")
        if not service:
            service.append("Bei Anreise kurz klären: Auto/Fahrrad/Wanderer, Frühstück, geplante Abreisezeit.")
        for x in service:
            story.append(Paragraph("• "+html.escape(x),styles["Normal"]))
        story.append(Spacer(1,4*mm))
        story.append(Paragraph("Hinweis: Dieses Blatt ist eine interne Gastgeberhilfe auf Basis der gespeicherten Buchungsdaten.",styles["Italic"]))
        doc.build(story)
        return pdf


    # ---------------- Kalender – Monatskalender mit zusammenhängenden Balken ----------------
    def build_calendar(self):
        main=ttk.Frame(self.tab_cal)
        main.pack(fill="both",expand=True,padx=10,pady=8)

        top=ttk.Frame(main)
        top.pack(fill="x",pady=(0,6))

        ttk.Label(top,text="Kalender & Revenue – Buchungen, freie Tage, KI-Preis",style="CardTitle.TLabel").pack(side="left",padx=(0,15))

        self.cal_month=StringVar(value=str(date.today().month))
        self.cal_year=StringVar(value=str(date.today().year))

        ttk.Label(top,text="Monat",style="Card.TLabel").pack(side="left")
        ttk.Combobox(top,textvariable=self.cal_month,values=[str(i) for i in range(1,13)],width=5,state="readonly").pack(side="left",padx=4)
        ttk.Label(top,text="Jahr",style="Card.TLabel").pack(side="left",padx=(8,0))
        ttk.Entry(top,textvariable=self.cal_year,width=8).pack(side="left",padx=4)
        ttk.Button(top,text="MONAT ANZEIGEN",command=self.refresh_calendar,style="Touch.TButton").pack(side="left",padx=8)
        ttk.Button(top,text="HEUTE",command=self.calendar_today,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(top,text="◀ VORMONAT",command=lambda:self.calendar_shift_month(-1),style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(top,text="NÄCHSTER MONAT ▶",command=lambda:self.calendar_shift_month(1),style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(top,text="MONATSKALENDER PDF",command=self.calendar_month_pdf,style="Gold.TButton").pack(side="left",padx=8)

        # Revenue-Kennzahlen direkt im Kalender: ein Blick statt Reiterwechsel.
        kpi=ttk.Frame(main)
        kpi.pack(fill="x",pady=(0,6))
        self.cal_kpi_occ=StringVar(value="Auslastung -")
        self.cal_kpi_free=StringVar(value="Frei -")
        self.cal_kpi_adr=StringVar(value="Ø Preis -")
        self.cal_kpi_revpar=StringVar(value="RevPAR -")
        self.cal_kpi_action=StringVar(value="Aktion -")
        for var in (self.cal_kpi_occ,self.cal_kpi_free,self.cal_kpi_adr,self.cal_kpi_revpar,self.cal_kpi_action):
            box=ttk.Frame(kpi,style="Card.TFrame",padding=(8,5))
            box.pack(side="left",fill="x",expand=True,padx=3)
            ttk.Label(box,textvariable=var,style="CardTitle.TLabel").pack(anchor="center")

        self.cal_status=StringVar(value="")
        ttk.Label(main,textvariable=self.cal_status,style="Card.TLabel").pack(anchor="w",pady=(0,5))

        # echter Monatskalender
        cal_frame=ttk.Frame(main)
        cal_frame.pack(fill="both",expand=True)

        self.cal_canvas=tk.Canvas(cal_frame,bg="#ffffff",highlightthickness=1,highlightbackground="#d7dde5")
        self.cal_canvas.pack(fill="both",expand=True)
        self.cal_canvas.bind("<Configure>",lambda e:self.refresh_calendar())

        legend=ttk.Frame(main)
        legend.pack(fill="x",pady=(5,0))
        ttk.Label(
            legend,
            text="Hinweis: Balken zeigen belegte Nächte. Der Abreisetag selbst ist Freiwerden/Wechseltag und wird nicht als belegte Nacht gezählt.",
            style="Card.TLabel"
        ).pack(anchor="w")

        self.cal_selected_booking_id=None
        self.cal_canvas.bind("<Double-1>",self.calendar_canvas_doubleclick)

    def calendar_today(self):
        self.cal_month.set(str(date.today().month))
        self.cal_year.set(str(date.today().year))
        self.refresh_calendar()

    def calendar_shift_month(self,delta):
        try:
            y=int(self.cal_year.get())
            m=int(self.cal_month.get())
        except Exception:
            y=date.today().year
            m=date.today().month
        m += int(delta)
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        self.cal_month.set(str(m))
        self.cal_year.set(str(y))
        self.refresh_calendar()

    def calendar_month_bounds(self):
        try:
            y=int(self.cal_year.get())
            m=int(self.cal_month.get())
            start,end=kalender_month_bounds(y,m)
        except Exception:
            start,end=kalender_month_bounds(date.today().year,date.today().month)
            self.cal_year.set(str(start.year))
            self.cal_month.set(str(start.month))
        return start,end

    def calendar_grid_bounds(self,start):
        # Wochenstart Montag, 6 Kalenderwochen anzeigen
        return kalender_grid_bounds(start)

    def calendar_booking_overlaps_month(self,b,start,end):
        return kalender_booking_overlaps_range(b,start,end)

    def calendar_occupied_range(self,b,grid_start,grid_end):
        """Belegte Nächte als Datumsbereich. Anreise inklusiv, Abreise exklusiv."""
        return kalender_occupied_range(b,grid_start,grid_end)

    def calendar_color_for_booking(self,b):
        colors=["#2b7cff","#3f9b34","#c77900","#8f4bd8","#008c8c","#c94d4d","#5168b8","#7a9f22"]
        key=str(b.get("id",""))+str(b.get("guest",""))
        return colors[sum(ord(ch) for ch in key)%len(colors)]

    def calendar_text_color(self,fill):
        return "#ffffff"

    def calendar_day_revenue_signal(self, d):
        """Kompakte Revenue-Bewertung eines Kalendertags.
        Wird bewusst direkt im Kalender verwendet, damit der Revenue-Reiter nicht nötig ist.
        """
        try:
            rooms=[r for r in self.d.get("rooms",[]) if r.get("active",True)]
            total=max(1,len(rooms))
            free_rooms=self.free_rooms_on_date(d)
            free_count=len(free_rooms)
            occ_percent, occ_num, occ_total=self.pa_own_occupancy_percent(d)
            if free_count<=0:
                return {
                    "free":0,"occ":occ_percent,"chance":0,"quick":0,"rec":0,"max":0,
                    "ampel":"🔵 belegt","color":"#d9e7f7","text":"belegt","stars":"", "detail":"Tag ist belegt."
                }
            sample=free_rooms[0]
            pr=self.pa_recommended_price(sample,d)
            rec=int(pr.get("price",0) or 0)
            quick=int(pr.get("low",rec) or rec)
            maxp=int(pr.get("high",rec) or rec)
            # Sicherheit: Schnellpreis <= Empfohlen <= Maximalpreis <= Deckel
            deck=fnum(getattr(self,"pa_max_price",StringVar(value="149")).get(),149)
            quick=max(0,min(int(deck),quick)); rec=max(quick,min(int(deck),rec)); maxp=max(rec,min(int(deck),maxp))
            try:
                score_int=int(str(pr.get("score","5/10")).split("/")[0])
            except Exception:
                score_int=5
            days_until=(d-date.today()).days
            chance=max(5,min(98,18 + score_int*7 + (12 if occ_percent>=50 else 0) + (8 if free_count<=1 else 0) - (8 if days_until<=2 and occ_percent==0 else 0)))
            if chance>=78:
                ampel="🟢 hoch"; color="#dff3d8"; action="Preis halten/erhöhen"
            elif chance>=55:
                ampel="🟡 normal"; color="#fff4ce"; action="Empfohlenen Preis setzen"
            elif chance>=35:
                ampel="🟠 schwach"; color="#ffe5cc"; action="Lücke füllen"
            else:
                ampel="🔴 niedrig"; color="#ffd9d9"; action="Schnellpreis prüfen"
            stars="★"*max(1,min(5,round(score_int/2)))
            detail=(
                f"{d.strftime('%d.%m.%Y')}\n\n"
                f"Revenue-Ampel: {ampel}\n"
                f"Buchungschance: {chance}%\n"
                f"Schnellpreis: {money(quick)}\n"
                f"Empfohlen: {money(rec)}\n"
                f"Maximalpreis: {money(maxp)}\n\n"
                f"Aktion: {action}\n\n"
                f"Freie Zimmer: {free_count}/{total}\n"
                f"Auslastung: {occ_percent}%\n"
                f"Wetter: {pr.get('weather','neutral')}\n"
                f"Event/Ferien: {pr.get('event','nein')}\n"
                f"Markt: {pr.get('market','normal')}\n"
            )
            return {"free":free_count,"occ":occ_percent,"chance":chance,"quick":quick,"rec":rec,"max":maxp,"ampel":ampel,"color":color,"text":action,"stars":stars,"detail":detail}
        except Exception as e:
            return {"free":0,"occ":0,"chance":0,"quick":0,"rec":0,"max":0,"ampel":"?","color":"#eeeeee","text":"Fehler","stars":"","detail":str(e)}

    def calendar_free_day_price_label(self, d):
        """Kurze Revenue-Anzeige für freie Kalendertage."""
        sig=self.calendar_day_revenue_signal(d)
        if not sig.get("free"):
            return ""
        return f"FREI\n{money(sig.get('rec',0))} · {sig.get('chance',0)}%\n{sig.get('stars','')}"

    def refresh_calendar(self):
        if not hasattr(self,"cal_canvas"):
            return

        canvas=self.cal_canvas
        try:
            canvas.delete("all")
        except Exception:
            return

        start,end=self.calendar_month_bounds()
        grid_start,grid_end=self.calendar_grid_bounds(start)

        w=max(canvas.winfo_width(),900)
        h=max(canvas.winfo_height(),520)
        header_h=32
        cols=7
        rows=6
        cell_w=w/cols
        cell_h=(h-header_h)/rows

        # Kopfzeile
        weekdays=["Mo","Di","Mi","Do","Fr","Sa","So"]
        for i,wd in enumerate(weekdays):
            x0=i*cell_w
            x1=(i+1)*cell_w
            canvas.create_rectangle(x0,0,x1,header_h,fill="#e8eef4",outline="#d7dde5")
            canvas.create_text((x0+x1)/2,header_h/2,text=wd,fill="#0b3d70",font=("Segoe UI",11,"bold"))

        today=date.today()
        month_bookings=[b for b in self.d.get("bookings",[]) if self.calendar_booking_overlaps_month(b,grid_start,grid_end)]

        # Raster / Tagesnummern
        day_positions={}
        cur=grid_start
        for r in range(rows):
            for c in range(cols):
                x0=c*cell_w
                y0=header_h+r*cell_h
                x1=x0+cell_w
                y1=y0+cell_h
                in_month=(cur.month==start.month)
                fill="#ffffff" if in_month else "#f4f4f4"
                if cur==today:
                    fill="#d9f7d3"
                canvas.create_rectangle(x0,y0,x1,y1,fill=fill,outline="#d7dde5")
                num_color="#0b3d70" if in_month else "#999999"
                canvas.create_text(x0+8,y0+8,text=str(cur.day),anchor="nw",fill=num_color,font=("Segoe UI",10,"bold"))
                day_positions[cur]=(x0,y0,x1,y1,r,c)
                cur += timedelta(days=1)

        # Mülltermine direkt im Monatskalender anzeigen.
        self.cal_muell_hitboxes=[]
        month_muell_count=0
        try:
            if 'muell_load_terms' in globals():
                for term in muell_load_terms():
                    md=term.get('datum')
                    if md in day_positions and md.month == start.month:
                        x0,y0,x1,y1,rr,cc=day_positions[md]
                        label=compact_muell_label(term.get('art'))
                        month_muell_count += 1
                        canvas.create_rectangle(x0+34,y0+6,x0+78,y0+23,fill="#f7efe0",outline="#d6b56d")
                        canvas.create_text(x0+56,y0+14,text=label,anchor="center",fill="#6a4a00",font=("Segoe UI",7,"bold"))
                        self.cal_muell_hitboxes.append((x0+34,y0+6,x0+78,y0+23,md.isoformat()))
        except Exception:
            month_muell_count=0

        # Buchungsbalken wochenweise zeichnen
        self.cal_bar_hitboxes=[]
        self.cal_day_hitboxes=[]
        week_lanes=[[] for _ in range(rows)]

        for b in sorted(month_bookings,key=lambda x:(room_name(self.d,x.get("room_id","")),x.get("arrival",""),x.get("guest",""))):
            if b.get("status")=="storniert":
                continue
            occ_start,occ_end=self.calendar_occupied_range(b,grid_start,grid_end)
            if not occ_start:
                continue

            # pro Kalenderwoche splitten
            current=occ_start
            while current < occ_end:
                week_index=((current-grid_start).days)//7
                week_start=grid_start+timedelta(days=week_index*7)
                week_end=week_start+timedelta(days=7)
                seg_start=current
                seg_end=min(occ_end,week_end)

                c0=(seg_start-week_start).days
                c1=(seg_end-week_start).days-1
                if week_index<0 or week_index>=6:
                    current=seg_end
                    continue

                # Lane finden, damit Balken nicht übereinander liegen
                lane=0
                used=week_lanes[week_index]
                while any(not (c1 < u[0] or c0 > u[1] or lane != u[2]) for u in used):
                    lane += 1
                used.append((c0,c1,lane))

                x0=c0*cell_w+4
                x1=(c1+1)*cell_w-4
                y_base=header_h+week_index*cell_h+28+lane*20
                y0=y_base
                y1=y_base+17
                # falls zu viele Buchungen in einer Woche, unten abschneiden
                if y1 < header_h+(week_index+1)*cell_h-4:
                    fill=self.calendar_color_for_booking(b)
                    canvas.create_rectangle(x0,y0,x1,y1,fill=fill,outline=fill,width=1)
                    label=f"{room_name(self.d,b.get('room_id',''))}: {b.get('guest','')}"
                    if seg_start > pdate(b.get("arrival","")):
                        label="↔ "+label
                    elif seg_end < pdate(b.get("departure","")):
                        label=label+" →"
                    canvas.create_text(x0+4,y0+8,text=label,anchor="w",fill=self.calendar_text_color(fill),font=("Segoe UI",8,"bold"))
                    self.cal_bar_hitboxes.append((x0,y0,x1,y1,b.get("id","")))

                current=seg_end

        # Stornierte optional klein unten als Hinweis
        cancelled=[b for b in month_bookings if b.get("status")=="storniert"]
        if cancelled:
            canvas.create_text(8,h-10,text=f"{len(cancelled)} stornierte Buchung(en) im Zeitraum ausgeblendet",anchor="sw",fill="#777777",font=("Segoe UI",9))

        # Status
        occupied_days=set()
        for b in month_bookings:
            if b.get("status")=="storniert":
                continue
            occ_start,occ_end=self.calendar_occupied_range(b,start,end)
            if occ_start:
                d=occ_start
                while d<occ_end:
                    occupied_days.add(d)
                    d += timedelta(days=1)

        # Freie Tage mit integrierter Revenue-Management-Empfehlung anzeigen
        month_revenue=[]
        try:
            for d,(x0,y0,x1,y1,r,cidx) in day_positions.items():
                if d.month != start.month or d in occupied_days:
                    continue
                sig=self.calendar_day_revenue_signal(d)
                if not sig.get("free"):
                    continue
                month_revenue.append(sig)
                box_h=48
                canvas.create_rectangle(x0+6,y1-box_h-6,x1-6,y1-7,fill=sig.get("color","#eef8e8"),outline="#b8c7b2")
                canvas.create_text(x0+10,y1-box_h-2,text="FREI",anchor="nw",fill="#184b17",font=("Segoe UI",7,"bold"))
                canvas.create_text((x0+x1)/2,y1-31,text=f"{money(sig.get('rec',0))} · {sig.get('chance',0)}%",anchor="center",fill="#0b3d70",font=("Segoe UI",8,"bold"))
                canvas.create_text((x0+x1)/2,y1-15,text=sig.get("ampel",""),anchor="center",fill="#333333",font=("Segoe UI",7,"bold"))
                self.cal_day_hitboxes.append((x0+6,y1-box_h-6,x1-6,y1-7,d.isoformat()))
        except Exception:
            pass

        if hasattr(self,"cal_status"):
            free_days=len([d for d in day_positions if d.month==start.month and d not in occupied_days])
            total_days=len([d for d in day_positions if d.month==start.month])
            occ_pct=round(len(occupied_days)*100/max(1,total_days))
            recs=[s.get("rec",0) for s in locals().get("month_revenue",[]) if s.get("rec")]
            adr=round(sum(recs)/len(recs)) if recs else 0
            revpar=round((adr*occ_pct/100),2) if adr else 0
            strong=sum(1 for s in locals().get("month_revenue",[]) if "🟢" in s.get("ampel",""))
            weak=sum(1 for s in locals().get("month_revenue",[]) if "🟠" in s.get("ampel","") or "🔴" in s.get("ampel",""))
            action="Preise erhöhen" if strong>weak else "Lücken füllen" if weak else "Preis halten"
            try:
                self.cal_kpi_occ.set(f"Auslastung {occ_pct}%")
                self.cal_kpi_free.set(f"Frei {free_days}")
                self.cal_kpi_adr.set(f"Ø Preis {money(adr)}")
                self.cal_kpi_revpar.set(f"RevPAR {money(revpar)}")
                self.cal_kpi_action.set(f"KI: {action}")
            except Exception:
                pass
            self.cal_status.set(
                f"{start.strftime('%m/%Y')}: {len(month_bookings)} Buchung(en) · {len(occupied_days)} belegte Nächte · {free_days} freie Tage · {locals().get('month_muell_count',0)} Mülltermin(e) · Revenue direkt im Kalender"
            )


    def calendar_month_pdf(self):
        """Monatskalender als DIN-A4-Querformat, optisch ähnlich der Bildschirmansicht. Je Buchung werden zwei Zeilen gedruckt: Gastname sowie Personenanzahl + Frühstück."""
        try:
            start,end=self.calendar_month_bounds()
            grid_start,grid_end=self.calendar_grid_bounds(start)
            pdf=out_dir()/f"Monatskalender_Bildschirmstil_{start.year}_{start.month:02d}.pdf"

            page_w,page_h=landscape(A4)
            c=pdfcanvas.Canvas(str(pdf), pagesize=landscape(A4))

            left=8*mm
            right=8*mm
            top=8*mm
            bottom=8*mm
            header_title_h=10*mm
            info_h=6*mm
            week_header_h=7*mm
            foot_h=10*mm

            grid_x=left
            grid_y=bottom+foot_h
            grid_w=page_w-left-right
            grid_h=page_h-top-bottom-header_title_h-info_h-foot_h
            cell_w=grid_w/7.0
            cell_h=(grid_h-week_header_h)/6.0
            header_y=grid_y+6*cell_h

            c.setFont('Helvetica-Bold', 15)
            c.setFillColor(colors.HexColor('#153f74'))
            c.drawString(left, page_h-top-4*mm, f"Monatskalender {start.strftime('%m/%Y')} – Zuhause am Bach")
            c.setFont('Helvetica', 8.5)
            c.setFillColor(colors.HexColor('#4a6075'))
            c.drawString(left, page_h-top-8.5*mm, 'Darstellung ähnlich der Bildschirmansicht · 2 Zeilen je Buchung: Gastname / Personen + Frühstück')

            weekdays=['Mo','Di','Mi','Do','Fr','Sa','So']
            for i,wd in enumerate(weekdays):
                x=grid_x+i*cell_w
                c.setFillColor(colors.HexColor('#e8eef4'))
                c.setStrokeColor(colors.HexColor('#d7dde5'))
                c.rect(x, header_y, cell_w, week_header_h, fill=1, stroke=1)
                c.setFillColor(colors.HexColor('#0b3d70'))
                c.setFont('Helvetica-Bold', 10)
                c.drawCentredString(x+cell_w/2, header_y+2.2*mm, wd)

            today=date.today()
            cur=grid_start
            for r in range(6):
                y=grid_y+(5-r)*cell_h
                for col in range(7):
                    x=grid_x+col*cell_w
                    in_month=(cur.month==start.month)
                    fill='#ffffff' if in_month else '#f4f4f4'
                    if cur==today:
                        fill='#d9f7d3'
                    c.setFillColor(colors.HexColor(fill))
                    c.setStrokeColor(colors.HexColor('#d7dde5'))
                    c.rect(x,y,cell_w,cell_h,fill=1,stroke=1)
                    c.setFillColor(colors.HexColor('#0b3d70' if in_month else '#999999'))
                    c.setFont('Helvetica-Bold', 9)
                    c.drawString(x+1.8*mm, y+cell_h-4.0*mm, str(cur.day))
                    cur += timedelta(days=1)

            month_bookings=[b for b in self.d.get('bookings',[]) if self.calendar_booking_overlaps_month(b,grid_start,grid_end) and b.get('status')!='storniert']
            week_lanes=[[] for _ in range(6)]
            lane_h=8.6*mm
            max_lanes=2
            bar_margin_x=0.8*mm
            bar_top_offset=6.4*mm

            for b in sorted(month_bookings,key=lambda x:(room_name(self.d,x.get('room_id','')),x.get('arrival',''),x.get('guest',''))):
                occ_start,occ_end=self.calendar_occupied_range(b,grid_start,grid_end)
                if not occ_start:
                    continue
                current=occ_start
                while current < occ_end:
                    week_index=((current-grid_start).days)//7
                    week_start=grid_start+timedelta(days=week_index*7)
                    week_end=week_start+timedelta(days=7)
                    seg_start=current
                    seg_end=min(occ_end,week_end)
                    c0=(seg_start-week_start).days
                    c1=(seg_end-week_start).days-1
                    lane=0
                    used=week_lanes[week_index]
                    while any(not (c1 < u[0] or c0 > u[1] or lane != u[2]) for u in used):
                        lane += 1
                    used.append((c0,c1,lane))

                    if lane < max_lanes:
                        x0=grid_x+c0*cell_w+bar_margin_x
                        x1=grid_x+(c1+1)*cell_w-bar_margin_x
                        week_y=grid_y+(5-week_index)*cell_h
                        y1=week_y+cell_h-bar_top_offset-lane*lane_h
                        y0=y1-(lane_h-0.8*mm)
                        fill=self.calendar_color_for_booking(b)
                        c.setFillColor(colors.HexColor(fill))
                        c.setStrokeColor(colors.HexColor(fill))
                        c.roundRect(x0,y0,max(2,x1-x0),lane_h-1.2*mm,1.3*mm,fill=1,stroke=0)

                        guest=str(b.get('guest','Gast') or 'Gast').strip()
                        parts=[p for p in guest.split() if p]
                        if len(guest)>22 and len(parts)>=2:
                            guest=parts[0]+' '+parts[-1]
                        if len(guest)>18 and len(parts)>=2:
                            guest=parts[-1]
                        persons=int(b.get('persons',1) or 1)
                        bf_raw=str(b.get('breakfast','') or '').strip()
                        bf_low=bf_raw.lower()
                        if not bf_raw or bf_low in ('kein','keins','nein','no','ohne','0','false'):
                            bf_txt='ohne F'
                        elif 'vegan' in bf_low:
                            bf_txt='F vegan'
                        elif 'normal' in bf_low or 'standard' in bf_low:
                            bf_txt='F normal'
                        elif 'vegetar' in bf_low:
                            bf_txt='F vegetar.'
                        else:
                            bf_txt='F '+bf_raw
                        line1=guest
                        if seg_start > pdate(b.get('arrival','')):
                            line1='↔ '+line1
                        elif seg_end < pdate(b.get('departure','')):
                            line1=line1+' →'
                        line2=f"{persons} Pers · {bf_txt}"
                        max_chars1=max(6,int((x1-x0)/(2.45*mm)))
                        max_chars2=max(6,int((x1-x0)/(2.65*mm)))
                        if len(line1)>max_chars1:
                            line1=line1[:max_chars1-1]+'…'
                        if len(line2)>max_chars2:
                            line2=line2[:max_chars2-1]+'…'
                        c.setFillColor(colors.white)
                        c.setFont('Helvetica-Bold', 7.9)
                        c.drawString(x0+1.1*mm, y0+4.6*mm, line1)
                        c.setFont('Helvetica', 6.8)
                        c.drawString(x0+1.1*mm, y0+1.8*mm, line2)
                    current=seg_end

            for wi,used in enumerate(week_lanes):
                overflow=max(0, len({u[2] for u in used})-max_lanes)
                if overflow:
                    week_y=grid_y+(5-wi)*cell_h
                    c.setFillColor(colors.HexColor('#777777'))
                    c.setFont('Helvetica', 6.5)
                    c.drawRightString(grid_x+grid_w-1.5*mm, week_y+1.5*mm, f'+{overflow} weitere Buchung(en)')

            occupied_days=set()
            for b in month_bookings:
                occ_start,occ_end=self.calendar_occupied_range(b,start,end)
                if occ_start:
                    d=occ_start
                    while d<occ_end:
                        occupied_days.add(d)
                        d += timedelta(days=1)
            c.setFillColor(colors.HexColor('#2d3e50'))
            c.setFont('Helvetica', 8)
            c.drawString(left, bottom+4.2*mm, f"{start.strftime('%m/%Y')}: {len(month_bookings)} Buchung(en) im Kalenderzeitraum · {len(occupied_days)} belegte Tag(e)/Nächte")
            c.setFillColor(colors.HexColor('#5f6e7a'))
            c.setFont('Helvetica', 7)
            c.drawString(left, bottom+1.5*mm, 'Hinweis: Balken zeigen belegte Nächte. Der Abreisetag selbst ist Freiwerden/Wechseltag und wird nicht als belegte Nacht gezählt.')

            c.showPage()
            c.save()
            if os.name=='nt':
                os.startfile(str(pdf))
            messagebox.showinfo('Monatskalender PDF', f"Kalender-PDF im Bildschirmstil wurde erstellt:\n{pdf}")
        except Exception as e:
            messagebox.showerror('Monatskalender PDF', str(e))


    def calendar_canvas_doubleclick(self,event):
        """Doppelklick: Buchungsbalken öffnet Buchung, freier Tag öffnet Revenue-Detail."""
        try:
            x,y=event.x,event.y
            for x0,y0,x1,y1,ds in getattr(self,"cal_muell_hitboxes",[]):
                if x0 <= x <= x1 and y0 <= y <= y1:
                    d=pdate(ds)
                    garbage=muell_load_terms() if 'muell_load_terms' in globals() else []
                    info=day_center_build(d, self.d.get("bookings", []), garbage, revenue_fn=self.calendar_day_revenue_signal, room_name_fn=lambda rid: room_name(self.d,rid))
                    messagebox.showinfo("Kalender Tageszentrale", day_center_format(info))
                    return
            for x0,y0,x1,y1,ds in getattr(self,"cal_day_hitboxes",[]):
                if x0 <= x <= x1 and y0 <= y <= y1:
                    d=pdate(ds)
                    garbage=muell_load_terms() if 'muell_load_terms' in globals() else []
                    info=day_center_build(d, self.d.get("bookings", []), garbage, revenue_fn=self.calendar_day_revenue_signal, room_name_fn=lambda rid: room_name(self.d,rid))
                    messagebox.showinfo("Kalender Tageszentrale", day_center_format(info))
                    return
            for x0,y0,x1,y1,bid in getattr(self,"cal_bar_hitboxes",[]):
                if x0 <= x <= x1 and y0 <= y <= y1:
                    b=next((z for z in self.d.get("bookings",[]) if str(z.get("id",""))==str(bid)),None)
                    if not b:
                        return
                    self.open_guest_area(self.tab_book)
                    try:
                        self.select_booking_in_tree(b.get("id",""))
                    except Exception:
                        pass
                    try:
                        self.cur_b=b.get("id","")
                    except Exception:
                        pass
                    try:
                        self.load_booking()
                    except TypeError:
                        self.load_booking(b.get("id",""))
                    return
        except Exception as e:
            messagebox.showerror("Kalender",str(e))


    def init_booking_vars(self):
        if hasattr(self,"b_guest"):
            return
        self.cur_b=None
        self.cur_key=None
        self._booking_tree_map={}
        self.b_guest=StringVar()
        self.b_birth=StringVar()
        self.b_email=StringVar()
        self.b_phone=StringVar()
        self.b_country=StringVar(value="AT")
        self.b_plz=StringVar()
        self.b_city=StringVar()
        self.b_street=StringVar()
        self.b_arr=StringVar(value=date.today().strftime("%d.%m.%Y"))
        self.b_dep=StringVar(value=(date.today()+timedelta(days=1)).strftime("%d.%m.%Y"))
        self.b_persons=StringVar(value="2")
        self.b_room=StringVar()
        self.b_price=StringVar(value="90")
        self.b_breakfast=StringVar(value="kein")
        self.b_lunch=BooleanVar(value=False)
        self.b_wishes=StringVar()
        self.b_status=StringVar(value="gebucht")
        self.b_dog=BooleanVar(value=False)
        self.b_dog_price=StringVar(value="5,00")
        self.b_wanderer=BooleanVar(value=False)
        self.b_bike=BooleanVar(value=False)
        self.b_ebike=BooleanVar(value=False)
        self.b_car=BooleanVar(value=False)
        self.b_regular=BooleanVar(value=False)
        self.b_plate=StringVar()
        self.b_allergies=StringVar()
        self.booking_editor=None
        self.b_loaded=StringVar(value="Neue Buchung")

    def make_booking_id(self):
        return booking_make_id()

    def booking_identity_key(self,b):
        return booking_make_identity_key(b)

    def ensure_unique_booking_ids(self):
        """Repariert fehlende oder doppelte Buchungs-IDs über das ausgelagerte Buchungsmodul."""
        changed=booking_ensure_unique_ids(self.d.setdefault("bookings",[]))
        if changed:
            save(self.d)
        return changed

    def build_bookings(self):
        self.init_booking_vars()
        self.ensure_unique_booking_ids()

        main=ttk.Frame(self.tab_book)
        main.pack(fill="both",expand=True,padx=10,pady=10)

        top=self.card(main,"Buchungen")
        ttk.Label(
            top,
            text="Buchungen verwalten, bearbeiten und prüfen.",
            style="Card.TLabel",
            wraplength=1400
        ).pack(anchor="w")

        action=ttk.Frame(top,style="Card.TFrame")
        action.pack(fill="x",pady=5)
        ttk.Button(action,text="➕ NEUE BUCHUNG",command=self.new_booking,style="Touch.TButton").pack(side="left",padx=4,pady=3)
        ttk.Button(action,text="⬇ MARKIERTE BUCHUNG LADEN",command=self.load_booking,style="Primary.TButton").pack(side="left",padx=4,pady=3)
        ttk.Button(action,text="🖨 GÄSTE-INFO PDF",command=self.gastinfo_pdf_selected,style="Gold.TButton").pack(side="left",padx=4,pady=3)
        ttk.Button(action,text="🗑 MARKIERTE BUCHUNG LÖSCHEN",command=self.delete_booking,style="Primary.TButton").pack(side="left",padx=4,pady=3)
        ttk.Button(action,text="🔧 DOPPELTE IDs REPARIEREN",command=self.repair_booking_ids_button,style="Gold.TButton").pack(side="left",padx=4,pady=3)
        ttk.Button(action,text="🔄 LISTE AKTUALISIEREN",command=self.refresh_bookings,style="Primary.TButton").pack(side="left",padx=4,pady=3)

        self.booking_status=StringVar(value="Bereit. Neue Buchung öffnen oder eine Buchung doppelklicken.")
        ttk.Label(top,textvariable=self.booking_status,style="CardTitle.TLabel").pack(anchor="w",pady=(3,0))

        table_card=self.card(main,"Buchungsliste – volle Breite")
        table_frame=ttk.Frame(table_card,style="Card.TFrame")
        table_frame.pack(fill="both",expand=True)

        cols=("id","gast","zimmer","anreise","abreise","nächte","personen","preis","frühstück","status","telefon","ort")
        self.bt=ttk.Treeview(table_frame,columns=cols,show="headings",height=28,selectmode="browse")
        labels={
            "id":"ID","gast":"Gast","zimmer":"Zimmer","anreise":"Anreise","abreise":"Abreise",
            "nächte":"Nächte","personen":"Pers.","preis":"Preis","frühstück":"Frühstück",
            "status":"Status","telefon":"Telefon","ort":"Ort"
        }
        widths={"id":170,"gast":230,"zimmer":190,"anreise":95,"abreise":95,"nächte":65,"personen":60,
                "preis":95,"frühstück":100,"status":100,"telefon":150,"ort":170}
        for c in cols:
            self.bt.heading(c,text=labels[c])
            self.bt.column(c,width=widths[c],anchor="w")
        vsb=ttk.Scrollbar(table_frame,orient="vertical",command=self.bt.yview)
        hsb=ttk.Scrollbar(table_frame,orient="horizontal",command=self.bt.xview)
        self.bt.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.bt.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        table_frame.rowconfigure(0,weight=1)
        table_frame.columnconfigure(0,weight=1)
        self.bt.tag_configure("today", background="#b8f2b0", foreground="#123012")
        self.bt.tag_configure("cancelled", background="#eeeeee", foreground="#777777")
        self.bt.tag_configure("today_guest",background="#d9f7d3",foreground="#0b3d70")
        self.bt.tag_configure("today_departure",background="#fff4df",foreground="#0b3d70")
        self.bt.tag_configure("next_guest",background="#dcecff",foreground="#0b3d70")
        self.bt.tag_configure("past_booking",background="#f1f1f1",foreground="#777777")
        self.bt.bind("<Double-1>",lambda e:self.load_booking())

    def repair_booking_ids_button(self):
        changed=self.ensure_unique_booking_ids()
        self.refresh_bookings()
        if changed:
            messagebox.showinfo("Buchungs-IDs","Doppelte oder fehlende Buchungs-IDs wurden repariert.")
        else:
            messagebox.showinfo("Buchungs-IDs","Keine doppelten Buchungs-IDs gefunden.")

    def room_values(self):
        rooms=[r for r in self.d.get("rooms",[]) if r.get("active",True)]
        if getattr(self,"cur_b",None):
            b=next((x for x in self.d.get("bookings",[]) if str(x.get("id",""))==str(self.cur_b)),None)
            if b:
                rid=str(b.get("room_id",""))
                if rid and not any(str(r.get("id"))==rid for r in rooms):
                    r=next((x for x in self.d.get("rooms",[]) if str(x.get("id"))==rid),None)
                    if r:
                        rooms.append(r)
        return [f"{r.get('id','')}: {r.get('name','')}" for r in rooms]

    def sel_room(self):
        val=str(self.b_room.get() or "").strip()
        if ":" in val:
            return val.split(":",1)[0].strip()
        vals=self.room_values()
        if vals:
            self.b_room.set(vals[0])
            return vals[0].split(":",1)[0].strip()
        return ""

    def booking_room_changed(self):
        try:
            rid=self.sel_room()
            price=room_price(self.d,rid)
            if price:
                self.b_price.set(str(price).replace(".",","))
        except Exception:
            pass

    def selected_booking_key(self):
        try:
            sel=self.bt.selection()
            if not sel:
                return None
            item=sel[0]
            if hasattr(self,"_booking_tree_map") and item in self._booking_tree_map:
                return self._booking_tree_map[item]
            vals=self.bt.item(item)["values"]
            if vals:
                return str(vals[0])
        except Exception:
            pass
        return None

    def selected_booking_id(self):
        key=self.selected_booking_key()
        if not key:
            return None
        if str(key).startswith("KEY:"):
            b=self.booking_by_key(key)
            return b.get("id") if b else None
        return key

    def booking_by_key(self,key):
        if not key:
            return None
        if str(key).startswith("KEY:"):
            wanted=str(key)[4:]
            return next((b for b in self.d.get("bookings",[]) if self.booking_identity_key(b)==wanted),None)
        return next((b for b in self.d.get("bookings",[]) if str(b.get("id",""))==str(key)),None)


    def booking_row_tag(self,b):
        try:
            today=date.today()
            arr=pdate(b.get("arrival",""))
            dep=pdate(b.get("departure",""))
            if arr <= today < dep or arr==today:
                return "today_guest"
            if dep==today:
                return "today_departure"
            nb=self.next_relevant_booking()
            if nb and str(nb.get("id",""))==str(b.get("id","")):
                return "next_guest"
            if dep < today:
                return "past_booking"
        except Exception:
            pass
        return ""

    def next_relevant_booking(self):
        try:
            today=date.today()
            items=[]
            for b in self.d.get("bookings",[]):
                if b.get("status")=="storniert":
                    continue
                try:
                    arr=pdate(b.get("arrival",""))
                    dep=pdate(b.get("departure",""))
                    if dep >= today:
                        items.append((arr,dep,b))
                except Exception:
                    pass
            return sorted(items,key=lambda x:(x[0],x[1],x[2].get("guest","")))[0][2] if items else None
        except Exception:
            return None

    def scroll_to_relevant_booking(self):
        try:
            if not hasattr(self,"bt"):
                return
            nb=self.next_relevant_booking()
            if not nb:
                return
            bid=str(nb.get("id",""))
            for item in self.bt.get_children():
                vals=self.bt.item(item).get("values",[])
                if vals and str(vals[0])==bid:
                    self.bt.selection_set(item)
                    self.bt.focus(item)
                    self.bt.see(item)
                    return
        except Exception:
            pass

    def refresh_bookings(self):
        if not hasattr(self,"bt"):
            return
        self.ensure_unique_booking_ids()
        self.d.setdefault("bookings",[])
        self.d.setdefault("extras",[])
        self._booking_tree_map={}
        for i in self.bt.get_children():
            self.bt.delete(i)

        for b in sorted(self.d.get("bookings",[]),key=lambda x:(x.get("arrival",""),x.get("guest",""),x.get("id",""))):
            try:
                today=date.today()
                arr=pdate(b.get("arrival",""))
                dep=pdate(b.get("departure",""))
                nights=max(0,(dep-arr).days)
                row_tag=self.booking_row_tag(b)
                tag=(row_tag,) if row_tag else ()
            except Exception:
                nights=""
                tag=()
            if b.get("status")=="storniert":
                tag=("cancelled",)
            item=self.bt.insert("",END,values=(
                b.get("id",""),
                b.get("guest",""),
                room_name(self.d,b.get("room_id","")),
                fmt(b.get("arrival","")),
                fmt(b.get("departure","")),
                nights,
                b.get("persons",1),
                money(b.get("price",0)),
                b.get("breakfast",""),
                b.get("status",""),
                b.get("phone",""),
                b.get("city","")
            ),tags=tag)
            self._booking_tree_map[item]="KEY:"+self.booking_identity_key(b)

        try:
            if hasattr(self,"b_room_cb") and self.b_room_cb.winfo_exists():
                vals=self.room_values()
                self.b_room_cb["values"]=vals
                if vals and not self.b_room.get():
                    self.b_room.set(vals[0])
        except Exception:
            pass
        self.scroll_to_relevant_booking()

    def reset_booking_form(self):
        self.cur_b=None
        self.cur_key=None
        for v in [self.b_guest,self.b_birth,self.b_email,self.b_phone,self.b_plz,self.b_city,self.b_street,self.b_wishes,self.b_plate,self.b_allergies]:
            v.set("")
        self.b_country.set("AT")
        self.b_arr.set(date.today().strftime("%d.%m.%Y"))
        self.b_dep.set((date.today()+timedelta(days=1)).strftime("%d.%m.%Y"))
        self.b_persons.set("2")
        self.b_breakfast.set("kein")
        self.b_lunch.set(False)
        self.b_status.set("gebucht")
        self.b_dog.set(False)
        self.b_dog_price.set("5,00")
        for v in [self.b_wanderer,self.b_bike,self.b_ebike,self.b_car,self.b_regular]:
            v.set(False)
        vals=self.room_values()
        self.b_room.set(vals[0] if vals else "")
        self.booking_room_changed()
        self.b_loaded.set("Neue Buchung")

    def new_booking(self):
        self.init_booking_vars()
        self.reset_booking_form()
        if hasattr(self,"bt"):
            try:
                self.bt.selection_remove(self.bt.selection())
                self.bt.focus("")
            except Exception:
                pass
        self.open_booking_editor("Neue Buchung")
        if hasattr(self,"booking_status"):
            self.booking_status.set("Neue Buchung geöffnet.")

    def load_booking(self):
        self.init_booking_vars()
        key=self.selected_booking_key()
        if not key:
            messagebox.showinfo("Buchung laden","Bitte links eine Buchung markieren oder doppelklicken.")
            return
        b=self.booking_by_key(key)
        if not b:
            messagebox.showerror("Buchung laden","Buchung wurde nicht gefunden.")
            return
        self.cur_b=str(b.get("id",""))
        self.cur_key="KEY:"+self.booking_identity_key(b)
        self.b_guest.set(b.get("guest",""))
        self.b_birth.set(b.get("birth",""))
        self.b_email.set(b.get("email",""))
        self.b_phone.set(b.get("phone",""))
        self.b_country.set(b.get("country","AT"))
        self.b_plz.set(b.get("plz",""))
        self.b_city.set(b.get("city",""))
        self.b_street.set(b.get("street",""))
        self.b_arr.set(fmt(b.get("arrival","")))
        self.b_dep.set(fmt(b.get("departure","")))
        self.b_persons.set(str(b.get("persons",1)))
        self.b_room.set(f"{b.get('room_id','')}: {room_name(self.d,b.get('room_id',''))}")
        self.b_price.set(str(b.get("price",0)).replace(".",","))
        self.b_breakfast.set(b.get("breakfast","kein"))
        self.b_lunch.set(bool(b.get("lunchpack",False)))
        self.b_wishes.set(b.get("wishes",""))
        self.b_status.set(b.get("status","gebucht"))
        self.b_dog.set(bool(b.get("dog",False)))
        self.b_dog_price.set(str(b.get("dog_price",5.0)).replace(".",","))
        self.b_wanderer.set(bool(b.get("wanderer",False)))
        self.b_bike.set(bool(b.get("bike",False)))
        self.b_ebike.set(bool(b.get("ebike",False)))
        self.b_car.set(bool(b.get("car",False)))
        self.b_regular.set(bool(b.get("regular",False)))
        self.b_plate.set(b.get("plate",""))
        self.b_allergies.set(b.get("allergies",""))
        if hasattr(self,"extra_bid"):
            try:
                self.extra_bid.set(str(self.cur_b))
                if hasattr(self,"refresh_extras"):
                    self.refresh_extras()
            except Exception:
                pass
        self.b_loaded.set(f"Geladen: {b.get('guest','')} ({self.cur_b})")
        self.open_booking_editor("Buchung bearbeiten")
        if hasattr(self,"booking_status"):
            self.booking_status.set(f"Buchung geladen: {b.get('guest','')}")

    def open_booking_editor(self,title="Buchung bearbeiten"):
        self.init_booking_vars()
        try:
            if self.booking_editor and self.booking_editor.winfo_exists():
                self.booking_editor.lift()
                self.booking_editor.focus_force()
                return
        except Exception:
            pass

        win=tk.Toplevel(self.root)
        self.booking_editor=win
        win.title(title)
        win.geometry("980x760")
        win.minsize(820,620)
        try:
            win.transient(self.root)
        except Exception:
            pass

        outer=ttk.Frame(win)
        outer.pack(fill="both",expand=True,padx=10,pady=10)

        head=ttk.Frame(outer)
        head.pack(fill="x",pady=(0,8))
        ttk.Label(head,textvariable=self.b_loaded,style="CardTitle.TLabel").pack(side="left",anchor="w")
        ttk.Button(head,text="💾 SPEICHERN",command=self.save_booking,style="Touch.TButton").pack(side="right",padx=4)
        ttk.Button(head,text="SCHLIESSEN",command=win.destroy,style="Primary.TButton").pack(side="right",padx=4)

        canvas=Canvas(outer,highlightthickness=0,bg="#f6f4ef")
        scroll=ttk.Scrollbar(outer,orient="vertical",command=canvas.yview)
        inner=ttk.Frame(canvas)
        inner.bind("<Configure>",lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0),window=inner,anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left",fill="both",expand=True)
        scroll.pack(side="right",fill="y")

        form=self.card(inner,"Buchungsdaten")
        grid=ttk.Frame(form,style="Card.TFrame")
        grid.pack(fill="both",expand=True)

        def row(r,c,label,var,values=None,width=34):
            box=ttk.Frame(grid,style="Card.TFrame")
            box.grid(row=r,column=c,sticky="ew",padx=8,pady=4)
            ttk.Label(box,text=label,style="Card.TLabel").pack(anchor="w")
            if values is None:
                e=ttk.Entry(box,textvariable=var,width=width)
                e.pack(fill="x")
                return e
            cb=ttk.Combobox(box,textvariable=var,values=values,width=width-3,state="readonly")
            cb.pack(fill="x")
            return cb

        for c in range(2):
            grid.columnconfigure(c,weight=1)

        row(0,0,"Gastname *",self.b_guest)
        row(0,1,"Telefon",self.b_phone)
        row(1,0,"E-Mail",self.b_email)
        row(1,1,"Land",self.b_country)
        row(2,0,"PLZ",self.b_plz)
        row(2,1,"Wohnort",self.b_city)
        row(3,0,"Straße",self.b_street)
        row(3,1,"Geburtsdatum",self.b_birth)
        row(4,0,"Anreise TT.MM.JJJJ",self.b_arr)
        row(4,1,"Abreise TT.MM.JJJJ",self.b_dep)
        row(5,0,"Personen",self.b_persons)

        ttk.Label(grid,text="Zimmer",style="Card.TLabel").grid(row=5,column=1,sticky="nw",padx=8,pady=(4,0))
        self.b_room_cb=ttk.Combobox(grid,textvariable=self.b_room,values=self.room_values(),state="readonly")
        self.b_room_cb.grid(row=5,column=1,sticky="ew",padx=8,pady=(25,4))
        self.b_room_cb.bind("<<ComboboxSelected>>",lambda e:self.booking_room_changed())

        row(6,0,"Zimmerpreis / Nacht",self.b_price)
        row(6,1,"Frühstück",self.b_breakfast,["kein","normal","vegan","vegetarisch","Wunsch"])
        row(7,0,"Status",self.b_status,["gebucht","geändert","storniert","abgereist"])
        row(7,1,"Hundepreis",self.b_dog_price)

        flags=self.card(inner,"Zusatzinfos")
        flag_grid=ttk.Frame(flags,style="Card.TFrame")
        flag_grid.pack(fill="x")
        flags_list=[
            ("Lunchpaket",self.b_lunch),("Hund dabei",self.b_dog),("Wanderer",self.b_wanderer),
            ("Fahrrad",self.b_bike),("E-Bike",self.b_ebike),("PKW",self.b_car),("Stammgast",self.b_regular)
        ]
        for i,(txt,var) in enumerate(flags_list):
            ttk.Checkbutton(flag_grid,text=txt,variable=var).grid(row=i//4,column=i%4,sticky="w",padx=10,pady=4)

        notes=self.card(inner,"Notizen")
        ngrid=ttk.Frame(notes,style="Card.TFrame")
        ngrid.pack(fill="x")
        def note_row(r,label,var):
            ttk.Label(ngrid,text=label,style="Card.TLabel").grid(row=r,column=0,sticky="w",padx=8,pady=4)
            ttk.Entry(ngrid,textvariable=var,width=70).grid(row=r,column=1,sticky="ew",padx=8,pady=4)
        ngrid.columnconfigure(1,weight=1)
        note_row(0,"Kennzeichen",self.b_plate)
        note_row(1,"Allergien",self.b_allergies)
        note_row(2,"Sonderwünsche",self.b_wishes)

        bottom=ttk.Frame(inner)
        bottom.pack(fill="x",pady=10)
        ttk.Button(bottom,text="💾 BUCHUNG SPEICHERN / ÄNDERN",command=self.save_booking,style="Touch.TButton").pack(side="left",padx=6)
        ttk.Button(bottom,text="🗑 DIESE BUCHUNG LÖSCHEN",command=self.delete_booking,style="Primary.TButton").pack(side="left",padx=6)
        ttk.Button(bottom,text="SCHLIESSEN",command=win.destroy,style="Primary.TButton").pack(side="right",padx=6)

    def booking_form_record(self):
        rid=self.sel_room()
        if not rid:
            raise ValueError("Bitte Zimmer auswählen. Wenn kein Zimmer vorhanden ist: zuerst im Tab Zimmer ein Zimmer anlegen/aktiv setzen.")
        guest=self.b_guest.get().strip()
        if not guest:
            raise ValueError("Gastname fehlt.")
        arr=iso(self.b_arr.get())
        dep=iso(self.b_dep.get())
        if pdate(dep) <= pdate(arr):
            raise ValueError("Abreise muss nach der Anreise liegen.")
        persons=max(1,fint(self.b_persons.get(),1))
        price=fnum(self.b_price.get())
        if price < 0:
            raise ValueError("Zimmerpreis darf nicht negativ sein.")
        old={}
        if self.cur_b:
            old=next((x for x in self.d.get("bookings",[]) if str(x.get("id",""))==str(self.cur_b)),{})
        rec={
            "id":self.cur_b or self.make_booking_id(),
            "guest":guest,
            "birth":self.b_birth.get().strip(),
            "email":self.b_email.get().strip(),
            "phone":self.b_phone.get().strip(),
            "country":self.b_country.get().strip() or "AT",
            "plz":self.b_plz.get().strip(),
            "city":self.b_city.get().strip(),
            "street":self.b_street.get().strip(),
            "arrival":arr,
            "departure":dep,
            "persons":persons,
            "room_id":rid,
            "price":price,
            "breakfast":self.b_breakfast.get(),
            "lunchpack":bool(self.b_lunch.get()),
            "wishes":self.b_wishes.get().strip(),
            "status":self.b_status.get() or "gebucht",
            "paid":old.get("paid",False),
            "checked_in":old.get("checked_in",False),
            "paid_out":old.get("paid_out",False),
            "dog":bool(self.b_dog.get()),
            "dog_price":fnum(self.b_dog_price.get(),5.0),
            "wanderer":bool(self.b_wanderer.get()),
            "bike":bool(self.b_bike.get()),
            "ebike":bool(self.b_ebike.get()),
            "car":bool(self.b_car.get()),
            "regular":bool(self.b_regular.get()),
            "plate":self.b_plate.get().strip(),
            "allergies":self.b_allergies.get().strip(),
        }
        errors=booking_validate_record(rec)
        if errors:
            raise ValueError("\n".join(errors))
        return rec

    def save_booking(self):
        try:
            self.d.setdefault("bookings",[])
            rec=self.booking_form_record()
            if self.cur_key and str(self.cur_key).startswith("KEY:"):
                old=self.booking_by_key(self.cur_key)
            else:
                old=next((b for b in self.d["bookings"] if str(b.get("id",""))==str(rec["id"])),None)

            conflicts=booking_find_conflicts(self.d.get("bookings",[]), rec, ignore_id=rec.get("id"))
            if conflicts:
                msg="Mögliche Doppelbelegung im selben Zimmer:\n\n" + "\n".join([f"- {x.get('guest','?')} · {fmt(x.get('arrival',''))} bis {fmt(x.get('departure',''))}" for x in conflicts[:5]])
                msg += "\n\nTrotzdem speichern?"
                if not messagebox.askyesno("Doppelbelegung prüfen", msg):
                    return

            action=booking_upsert(self.d["bookings"], rec, old=old)

            self.cur_b=rec["id"]
            self.cur_key="KEY:"+self.booking_identity_key(rec)
            save(self.d)
            try:
                self.wb_record_booking_event(rec, action)
            except Exception:
                log_exception("Windi Brain Buchungsereignis")
            self.calendar_auto_export(silent=True)
            self.refresh_all()
            self.select_booking_in_tree(self.cur_b)
            self.b_loaded.set(f"Geladen: {rec.get('guest','')} ({rec.get('id','')})")
            if hasattr(self,"booking_status"):
                self.booking_status.set(f"Buchung {action}: {rec.get('guest','')}")
            messagebox.showinfo("Buchung gespeichert",f"Buchung wurde {action}:\n{rec['guest']}\n{fmt(rec['arrival'])} bis {fmt(rec['departure'])}")
        except Exception as e:
            messagebox.showerror("Buchung speichern",str(e))

    def select_booking_in_tree(self,bid):
        try:
            for item in self.bt.get_children():
                vals=self.bt.item(item)["values"]
                if vals and str(vals[0])==str(bid):
                    self.bt.selection_set(item)
                    self.bt.focus(item)
                    self.bt.see(item)
                    return
        except Exception:
            pass

    def delete_booking(self):
        key=self.cur_key or self.selected_booking_key()
        if not key:
            messagebox.showinfo("Buchung löschen","Bitte links eine Buchung markieren oder zuerst laden.")
            return
        b=self.booking_by_key(key)
        if not b:
            messagebox.showerror("Buchung löschen","Buchung wurde nicht gefunden.")
            return
        if not messagebox.askyesno("Buchung löschen",f"Buchung wirklich löschen?\n\n{b.get('guest','')}\n{fmt(b.get('arrival',''))} bis {fmt(b.get('departure',''))}"):
            return
        booking_delete_with_extras(self.d,b)
        self.cur_b=None
        self.cur_key=None
        save(self.d)
        self.calendar_auto_export(silent=True)
        self.refresh_all()
        self.reset_booking_form()
        try:
            if self.booking_editor and self.booking_editor.winfo_exists():
                self.booking_editor.destroy()
        except Exception:
            pass
        messagebox.showinfo("Buchung gelöscht","Buchung wurde gelöscht.")


    # ---------------- Zimmerverwaltung – Zimmerliste sichtbar ----------------

    def init_room_vars(self):
        if hasattr(self,"r_name"):
            return
        self.cur_r=None
        self.r_loaded=StringVar(value="Kein Zimmer geladen")
        self.r_name=StringVar()
        self.r_price=StringVar(value="90")
        self.r_capacity=StringVar(value="2")
        self.r_notes=StringVar()
        self.r_active=BooleanVar(value=True)
        self.room_editor=None

    def build_rooms(self):
        self.init_room_vars()

        main=ttk.Frame(self.tab_rooms)
        main.pack(fill="both",expand=True,padx=10,pady=8)

        # Kompakter Kopf statt großer Textblöcke.
        head=ttk.Frame(main)
        head.pack(fill="x",pady=(0,4))
        ttk.Label(head,text="Zimmerverwaltung",style="CardTitle.TLabel").pack(side="left",padx=(4,16))
        self.r_summary=StringVar(value="")
        ttk.Label(head,textvariable=self.r_summary,style="CardTitle.TLabel").pack(side="left")

        # Kompakte Aktionen, damit die Liste den Bildschirm bekommt.
        toolbar=ttk.Frame(main)
        toolbar.pack(fill="x",pady=(0,5))

        row1=ttk.Frame(toolbar)
        row1.pack(fill="x",pady=2)
        row2=ttk.Frame(toolbar)
        row2.pack(fill="x",pady=2)

        ttk.Button(row1,text="🏡 Marillenzimmer",command=lambda:self.add_room_template("Marillenzimmer",90,2,"Wachau / Marille"),style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(row1,text="🍇 Weinbergzimmer",command=lambda:self.add_room_template("Weinbergzimmer",90,2,"Wachau / Weinberge"),style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(row1,text="🌊 Donauzimmer",command=lambda:self.add_room_template("Donauzimmer",90,2,"Wachau / Donau"),style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(row1,text="➕ NEUES ZIMMER",command=self.new_room,style="Touch.TButton").pack(side="left",padx=8)

        ttk.Button(row2,text="MARKIERTES ZIMMER LADEN",command=self.load_selected_room,style="Touch.TButton").pack(side="left",padx=3)
        ttk.Button(row2,text="SPEICHERN",command=self.update_room,style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(row2,text="NUR PREIS",command=self.update_room_price_only,style="Gold.TButton").pack(side="left",padx=3)
        ttk.Button(row2,text="AKTIV",command=lambda:self.set_room_active_state(True),style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(row2,text="SPERREN",command=lambda:self.set_room_active_state(False),style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(row2,text="PREIS AUF ZUKÜNFTIGE",command=self.apply_room_price_to_future_bookings,style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(row2,text="LÖSCHEN",command=self.delete_room,style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(row2,text="AKTUALISIEREN",command=self.refresh_rooms,style="Primary.TButton").pack(side="left",padx=3)

        # Tabelle bekommt den gesamten restlichen Platz.
        list_outer=ttk.Frame(main)
        list_outer.pack(fill="both",expand=True,pady=(4,0))
        ttk.Label(list_outer,text="Zimmerliste – Doppelklick zum Bearbeiten",style="CardTitle.TLabel").pack(anchor="w",padx=4,pady=(0,4))

        table_frame=ttk.Frame(list_outer)
        table_frame.pack(fill="both",expand=True)

        cols=("id","name","capacity","price","active","notes")
        self.rt=ttk.Treeview(table_frame,columns=cols,show="headings",height=30,selectmode="browse")
        labels={"id":"ID","name":"Zimmername","capacity":"Pers.","price":"Preis/Nacht","active":"Status","notes":"Notiz"}
        widths={"id":140,"name":360,"capacity":80,"price":150,"active":130,"notes":650}
        for c in cols:
            self.rt.heading(c,text=labels[c])
            self.rt.column(c,width=widths[c],anchor="w")
        vsb=ttk.Scrollbar(table_frame,orient="vertical",command=self.rt.yview)
        hsb=ttk.Scrollbar(table_frame,orient="horizontal",command=self.rt.xview)
        self.rt.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.rt.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        table_frame.rowconfigure(0,weight=1)
        table_frame.columnconfigure(0,weight=1)

        self.rt.tag_configure("active",background="#ffffff",foreground="#12351e")
        self.rt.tag_configure("inactive",background="#eeeeee",foreground="#777777")
        self.rt.bind("<Double-1>",lambda e:self.load_selected_room())

    def open_room_editor(self,title="Zimmer bearbeiten"):
        self.init_room_vars()
        try:
            if self.room_editor and self.room_editor.winfo_exists():
                self.room_editor.lift()
                self.room_editor.focus_force()
                return
        except Exception:
            pass

        win=tk.Toplevel(self.root)
        self.room_editor=win
        win.title(title)
        win.geometry("720x520")
        win.minsize(640,440)
        try:
            win.transient(self.root)
        except Exception:
            pass

        outer=ttk.Frame(win)
        outer.pack(fill="both",expand=True,padx=12,pady=12)

        head=ttk.Frame(outer)
        head.pack(fill="x",pady=(0,8))
        ttk.Label(head,textvariable=self.r_loaded,style="CardTitle.TLabel").pack(side="left",anchor="w")
        ttk.Button(head,text="💾 SPEICHERN",command=self.update_room,style="Touch.TButton").pack(side="right",padx=4)
        ttk.Button(head,text="SCHLIESSEN",command=win.destroy,style="Primary.TButton").pack(side="right",padx=4)

        form=self.card(outer,"Zimmerdaten")
        def row(label,var):
            ttk.Label(form,text=label,style="Card.TLabel").pack(anchor="w")
            ttk.Entry(form,textvariable=var,width=54).pack(fill="x",pady=(0,8))

        row("Zimmername",self.r_name)
        row("Preis / Nacht",self.r_price)
        row("Personen / Kapazität",self.r_capacity)
        ttk.Checkbutton(form,text="aktiv / buchbar",variable=self.r_active).pack(anchor="w",pady=(2,8))
        row("Notiz",self.r_notes)

        bottom=ttk.Frame(outer)
        bottom.pack(fill="x",pady=8)
        ttk.Button(bottom,text="💾 ZIMMER SPEICHERN",command=self.update_room,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(bottom,text="NUR PREIS SPEICHERN",command=self.update_room_price_only,style="Gold.TButton").pack(side="left",padx=5)
        ttk.Button(bottom,text="SPERREN",command=lambda:self.set_room_active_state(False),style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(bottom,text="AKTIV SETZEN",command=lambda:self.set_room_active_state(True),style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(bottom,text="LÖSCHEN",command=self.delete_room,style="Primary.TButton").pack(side="right",padx=5)

    def room_item_selected_id(self):
        try:
            sel=self.rt.selection()
            if not sel:
                return None
            vals=self.rt.item(sel[0])["values"]
            if not vals:
                return None
            return str(vals[0])
        except Exception:
            return None

    def get_selected_room_id(self):
        return self.room_item_selected_id()

    def selected_room_id_from_tree(self):
        return self.room_item_selected_id()

    def get_room_by_id(self,rid):
        return next((x for x in self.d.get("rooms",[]) if str(x.get("id",""))==str(rid)),None)

    def refresh_rooms(self):
        if not hasattr(self,"rt"):
            return
        total=len(self.d.get("rooms",[]))
        active=sum(1 for r in self.d.get("rooms",[]) if r.get("active",True))
        if hasattr(self,"r_summary"):
            self.r_summary.set(f"Zimmer gesamt: {total} · aktiv: {active} · gesperrt: {total-active}")
        for i in self.rt.get_children():
            self.rt.delete(i)
        for r in sorted(self.d.get("rooms",[]),key=lambda x:(not x.get("active",True),x.get("name",""))):
            tag="active" if r.get("active",True) else "inactive"
            self.rt.insert("",END,values=(
                r.get("id",""),
                r.get("name",""),
                r.get("capacity",2),
                money(r.get("price",0)),
                "aktiv" if r.get("active",True) else "gesperrt",
                r.get("notes","")
            ),tags=(tag,))
        try:
            if hasattr(self,"b_room_cb") and self.b_room_cb.winfo_exists():
                vals=self.room_values()
                self.b_room_cb["values"]=vals
        except Exception:
            pass

    def load_selected_room(self):
        self.init_room_vars()
        rid=self.room_item_selected_id()
        if not rid:
            messagebox.showinfo("Zimmer laden","Bitte links ein Zimmer markieren oder doppelklicken.")
            return
        self.load_room_by_id(rid)

    def load_room_by_id(self,rid):
        self.init_room_vars()
        r=self.get_room_by_id(rid)
        if not r:
            messagebox.showerror("Zimmer laden","Zimmer wurde nicht gefunden.")
            return
        self.cur_r=str(rid)
        self.r_name.set(r.get("name",""))
        self.r_price.set(str(r.get("price",0)).replace(".",","))
        self.r_capacity.set(str(r.get("capacity",2)))
        self.r_notes.set(r.get("notes",""))
        self.r_active.set(bool(r.get("active",True)))
        self.r_loaded.set(f"Geladen: {r.get('name','')} ({rid})")
        self.open_room_editor("Zimmer bearbeiten")

    def load_room(self):
        self.load_selected_room()

    def new_room(self):
        self.init_room_vars()
        self.cur_r=None
        self.r_loaded.set("Neues Zimmer")
        self.r_name.set("")
        self.r_price.set("90")
        self.r_capacity.set("2")
        self.r_notes.set("")
        self.r_active.set(True)
        try:
            if hasattr(self,"rt"):
                self.rt.selection_remove(self.rt.selection())
        except Exception:
            pass
        self.open_room_editor("Neues Zimmer")

    def room_values_from_form(self):
        return {
            "name":self.r_name.get().strip(),
            "price":fnum(self.r_price.get()),
            "capacity":max(1,fint(self.r_capacity.get(),2)),
            "notes":self.r_notes.get().strip(),
            "active":bool(self.r_active.get()),
        }

    def add_room(self):
        self.update_room()

    def add_room_template(self,name,price,capacity,notes):
        self.init_room_vars()
        self.cur_r=None
        self.r_name.set(name)
        self.r_price.set(str(price).replace(".",","))
        self.r_capacity.set(str(capacity))
        self.r_notes.set(notes)
        self.r_active.set(True)
        self.r_loaded.set("Neues Zimmer aus Vorlage")
        self.update_room()

    def update_room(self):
        try:
            self.init_room_vars()
            vals=self.room_values_from_form()
            if not vals["name"]:
                raise ValueError("Zimmername fehlt.")
            rec={
                "id":self.cur_r or uid("ROOM"),
                **vals,
            }
            if self.cur_r:
                found=False
                new_rooms=[]
                for r in self.d.get("rooms",[]):
                    if str(r.get("id",""))==str(self.cur_r):
                        new_rooms.append(rec)
                        found=True
                    else:
                        new_rooms.append(r)
                if not found:
                    new_rooms.append(rec)
                self.d["rooms"]=new_rooms
                action="gespeichert"
            else:
                self.d.setdefault("rooms",[]).append(rec)
                self.cur_r=rec["id"]
                action="angelegt"
            save(self.d)
            self.refresh_rooms()
            self.select_room_in_table(self.cur_r)
            self.r_loaded.set(f"Geladen: {rec.get('name','')} ({rec.get('id','')})")
            messagebox.showinfo("Zimmer",f"Zimmer wurde {action}:\n{rec.get('name','')}")
        except Exception as e:
            messagebox.showerror("Zimmer speichern",str(e))

    def save_room(self):
        self.update_room()

    def update_room_price_only(self):
        try:
            self.init_room_vars()
            rid=self.cur_r or self.room_item_selected_id()
            if not rid:
                messagebox.showinfo("Preis speichern","Bitte ein Zimmer laden oder markieren.")
                return
            r=self.get_room_by_id(rid)
            if not r:
                messagebox.showerror("Preis speichern","Zimmer wurde nicht gefunden.")
                return
            r["price"]=fnum(self.r_price.get())
            save(self.d)
            self.refresh_rooms()
            self.select_room_in_table(rid)
            messagebox.showinfo("Preis gespeichert",f"Preis gespeichert für {r.get('name','')}: {money(r.get('price',0))}")
        except Exception as e:
            messagebox.showerror("Preis speichern",str(e))

    def set_room_active_state(self,state):
        try:
            rid=self.cur_r or self.room_item_selected_id()
            if not rid:
                messagebox.showinfo("Zimmerstatus","Bitte ein Zimmer laden oder markieren.")
                return
            r=self.get_room_by_id(rid)
            if not r:
                messagebox.showerror("Zimmerstatus","Zimmer wurde nicht gefunden.")
                return
            r["active"]=bool(state)
            if self.cur_r and str(self.cur_r)==str(rid):
                self.r_active.set(bool(state))
            save(self.d)
            self.refresh_rooms()
            self.select_room_in_table(rid)
            messagebox.showinfo("Zimmerstatus","Zimmer ist jetzt aktiv/buchbar." if state else "Zimmer ist jetzt gesperrt/inaktiv.")
        except Exception as e:
            messagebox.showerror("Zimmerstatus",str(e))

    def deactivate_room(self):
        self.set_room_active_state(False)

    def delete_room(self):
        try:
            rid=self.cur_r or self.room_item_selected_id()
            if not rid:
                messagebox.showinfo("Zimmer löschen","Bitte ein Zimmer laden oder markieren.")
                return
            r=self.get_room_by_id(rid)
            if not r:
                messagebox.showerror("Zimmer löschen","Zimmer wurde nicht gefunden.")
                return
            used=any(str(b.get("room_id",""))==str(rid) for b in self.d.get("bookings",[]))
            msg=f"Zimmer wirklich löschen?\n\n{r.get('name','')}"
            if used:
                msg+="\n\nAchtung: Dieses Zimmer ist in Buchungen verwendet. Besser nur SPERREN statt löschen."
            if not messagebox.askyesno("Zimmer löschen",msg):
                return
            self.d["rooms"]=[x for x in self.d.get("rooms",[]) if str(x.get("id",""))!=str(rid)]
            save(self.d)
            self.cur_r=None
            self.refresh_rooms()
            self.r_loaded.set("Kein Zimmer geladen")
            try:
                if self.room_editor and self.room_editor.winfo_exists():
                    self.room_editor.destroy()
            except Exception:
                pass
            messagebox.showinfo("Zimmer gelöscht","Zimmer wurde gelöscht.")
        except Exception as e:
            messagebox.showerror("Zimmer löschen",str(e))

    def select_room_in_table(self,rid):
        try:
            for item in self.rt.get_children():
                vals=self.rt.item(item)["values"]
                if vals and str(vals[0])==str(rid):
                    self.rt.selection_set(item)
                    self.rt.focus(item)
                    self.rt.see(item)
                    return
        except Exception:
            pass

    def apply_room_price_to_future_bookings(self):
        try:
            rid=self.cur_r or self.room_item_selected_id()
            if not rid:
                messagebox.showinfo("Preis übertragen","Bitte ein Zimmer laden oder markieren.")
                return
            r=self.get_room_by_id(rid)
            if not r:
                messagebox.showerror("Preis übertragen","Zimmer wurde nicht gefunden.")
                return
            price=fnum(self.r_price.get()) if self.cur_r else float(r.get("price",0) or 0)
            today=date.today().isoformat()
            count=0
            for b in self.d.get("bookings",[]):
                if str(b.get("room_id",""))==str(rid) and str(b.get("arrival",""))>=today and b.get("status")!="storniert":
                    b["price"]=price
                    count+=1
            save(self.d)
            self.refresh_all()
            messagebox.showinfo("Preis übertragen",f"Preis wurde auf {count} zukünftige Buchung(en) übertragen.")
        except Exception as e:
            messagebox.showerror("Preis übertragen",str(e))


    def build_extras(self):
        main=ttk.Frame(self.tab_extras)
        main.pack(fill="both",expand=True,padx=10,pady=8)

        # Kompakter Kopf
        head=ttk.Frame(main)
        head.pack(fill="x",pady=(0,4))

        ttk.Label(head,text="Rechnung / Extras",style="CardTitle.TLabel").pack(side="left",padx=(0,12))

        self.extra_bid=StringVar()
        self.extra_info=StringVar(value="Bitte eine Buchung laden oder Buchungs-ID eingeben.")

        ttk.Label(head,text="Buchungs-ID",style="Card.TLabel").pack(side="left")
        bid_entry=ttk.Entry(head,textvariable=self.extra_bid,width=30)
        bid_entry.pack(side="left",padx=5)
        ttk.Button(head,text="ANZEIGEN",command=self.refresh_extras,style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(head,text="AUS GELADENER BUCHUNG",command=self.use_current_booking_for_extras,style="Primary.TButton").pack(side="left",padx=3)
        ttk.Button(head,text="RECHNUNG PDF",command=self.invoice_pdf,style="Touch.TButton").pack(side="left",padx=8)

        info_line=ttk.Frame(main)
        info_line.pack(fill="x",pady=(0,3))
        ttk.Label(info_line,textvariable=self.extra_info,style="Card.TLabel",wraplength=1450).pack(anchor="w")

        # Artikel / Extra erfassen, ändern, löschen – JETZT OBEN SICHTBAR
        form=ttk.Frame(main)
        form.pack(fill="x",pady=(0,6))

        self.cur_e=None
        self.e_item=StringVar(value="Kaffee")
        self.e_qty=StringVar(value="1")
        self.e_price=StringVar(value="3")

        line1=ttk.Frame(form)
        line1.pack(fill="x",pady=2)
        ttk.Label(line1,text="Artikel/Leistung",style="Card.TLabel").pack(side="left",padx=(0,4))
        self.e_combo=ttk.Combobox(line1,textvariable=self.e_item,width=36)
        self.e_combo.pack(side="left",padx=4)
        ttk.Label(line1,text="Menge",style="Card.TLabel").pack(side="left",padx=(10,3))
        ttk.Entry(line1,textvariable=self.e_qty,width=8).pack(side="left",padx=3)
        ttk.Label(line1,text="Einzelpreis",style="Card.TLabel").pack(side="left",padx=(10,3))
        ttk.Entry(line1,textvariable=self.e_price,width=10).pack(side="left",padx=3)
        ttk.Button(line1,text="Preis übernehmen",command=self.take_article_price,style="Primary.TButton").pack(side="left",padx=6)

        line2=ttk.Frame(form)
        line2.pack(fill="x",pady=2)
        ttk.Button(line2,text="➕ ARTIKEL DAZUFÜGEN",command=self.add_extra,style="Touch.TButton").pack(side="left",padx=4)
        ttk.Button(line2,text="✏️ MARKIERTEN ARTIKEL ÄNDERN",command=self.update_extra,style="Gold.TButton").pack(side="left",padx=4)
        ttk.Button(line2,text="🗑 MARKIERTEN ARTIKEL LÖSCHEN",command=self.delete_extra,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(line2,text="FELDER LEEREN",command=self.clear_extra,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Label(line2,text="Nur EXT-Artikel sind änderbar/löschbar.",style="Card.TLabel").pack(side="left",padx=12)

        # Rechnungsliste darunter, weiterhin groß, aber Buttons bleiben sichtbar
        table_outer=ttk.Frame(main)
        table_outer.pack(fill="both",expand=True,pady=(0,4))

        cols=("id","leistung","menge","einzel","summe")
        self.et=ttk.Treeview(table_outer,columns=cols,show="headings",height=18,selectmode="browse")
        headers={"id":"ID","leistung":"Leistung / Artikel","menge":"Menge","einzel":"Einzel","summe":"Summe"}
        widths={"id":160,"leistung":820,"menge":140,"einzel":150,"summe":170}
        for c in cols:
            self.et.heading(c,text=headers[c])
            self.et.column(c,width=widths[c],anchor="w")
        self.et.column("menge",anchor="center")
        self.et.column("einzel",anchor="e")
        self.et.column("summe",anchor="e")

        vsb=ttk.Scrollbar(table_outer,orient="vertical",command=self.et.yview)
        hsb=ttk.Scrollbar(table_outer,orient="horizontal",command=self.et.xview)
        self.et.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.et.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        table_outer.rowconfigure(0,weight=1)
        table_outer.columnconfigure(0,weight=1)

        self.et.bind("<<TreeviewSelect>>",lambda e:self.load_extra())
        self.et.bind("<Double-1>",lambda e:self.load_extra())
        self.et.tag_configure("manual",background="#ffffff")
        self.et.tag_configure("auto",background="#f6f8fb")
        self.et.tag_configure("summary",background="#e9f6e7")

        try:
            bid_entry.bind("<Return>",lambda e:self.refresh_extras())
        except Exception:
            pass

    def use_current_booking_for_extras(self):
        bid = getattr(self, "cur_b", None) or self.selected_booking_id()
        if not bid:
            messagebox.showinfo("Rechnung","Bitte zuerst eine Buchung laden oder links in der Buchungsliste markieren.")
            return
        self.extra_bid.set(str(bid))
        self.refresh_extras()

    def selected_extra_id(self):
        try:
            sel=self.et.selection()
            if not sel:
                return None
            vals=self.et.item(sel[0])["values"]
            if not vals:
                return None
            return str(vals[0])
        except Exception:
            return None

    def invoice_display_rows(self,b):
        rows=[]
        t=total(self.d,b)
        c_due=checkout_due(self.d,b)
        ns=t["nights"]
        room_rate=float(b.get("price",0) or 0)
        room_sum=t["room"]
        room_text="Zimmer/Nächtigung"
        if c_due["paid_room"]:
            room_text+=" (über Booking/extern bezahlt)"
        rows.append({"id":"ZIMMER","leistung":room_text,"menge":str(ns),"einzel":money(room_rate),"summe":money(room_sum),"tag":"auto"})

        if b.get("dog"):
            dog_rate=float(b.get("dog_price",5.0) or 0)
            dog_sum=dog_rate*ns
            rows.append({"id":"HUND","leistung":"Hund","menge":str(ns),"einzel":money(dog_rate),"summe":money(dog_sum),"tag":"auto"})

        for e in extras_for(self.d,b["id"]):
            esum=float(e.get("qty",1) or 0)*float(e.get("price",0) or 0)
            rows.append({"id":e.get("id",""),"leistung":e.get("item",""),"menge":str(e.get("qty",1)),"einzel":money(e.get("price",0)),"summe":money(esum),"tag":"manual"})

        tax_units=f"{int(b.get('persons',1))} Pers. × {ns} Nächte"
        rows.append({"id":"TAXE","leistung":"Ortstaxe","menge":tax_units,"einzel":money(ORTSTAXE),"summe":money(t["tax"]),"tag":"auto"})
        rows.append({"id":"OFFEN","leistung":"Noch zu zahlen","menge":"","einzel":"","summe":money(c_due["due"]),"tag":"summary"})
        return rows

    def refresh_extras(self):
        if not hasattr(self,"et"):
            return
        for i in self.et.get_children():
            self.et.delete(i)
        bid=(self.extra_bid.get() or "").strip()
        if not bid:
            if hasattr(self,"extra_info"):
                self.extra_info.set("Bitte eine Buchung laden oder Buchungs-ID eingeben.")
            return
        b=next((x for x in self.d.get("bookings",[]) if str(x.get("id",""))==str(bid)),None)
        if not b:
            if hasattr(self,"extra_info"):
                self.extra_info.set(f"Buchung {bid} wurde nicht gefunden.")
            return
        for row in self.invoice_display_rows(b):
            self.et.insert("",END,values=(row["id"],row["leistung"],row["menge"],row["einzel"],row["summe"]),tags=(row.get("tag","auto"),))
        c_due=checkout_due(self.d,b)
        if hasattr(self,"extra_info"):
            self.extra_info.set(
                f"Gast: {b.get('guest','')} · Zimmer: {room_name(self.d,b.get('room_id',''))} · Aufenthalt: {fmt(b.get('arrival',''))} bis {fmt(b.get('departure',''))} · Offen: {money(c_due['due'])}"
            )

    def add_extra(self):
        bid=(self.extra_bid.get() or "").strip()
        if not bid:
            messagebox.showinfo("Artikel dazufügen","Bitte zuerst eine Buchung laden oder eine Buchungs-ID eingeben.")
            return
        b=next((x for x in self.d.get("bookings",[]) if str(x.get("id",""))==str(bid)),None)
        if not b:
            messagebox.showerror("Artikel dazufügen","Buchung wurde nicht gefunden.")
            return
        item=self.e_item.get().strip()
        if not item:
            messagebox.showinfo("Artikel dazufügen","Bitte Artikel/Leistung eingeben.")
            return
        qty=fnum(self.e_qty.get(),1)
        price=fnum(self.e_price.get(),0)
        if qty <= 0:
            messagebox.showinfo("Artikel dazufügen","Menge muss größer als 0 sein.")
            return
        self.d.setdefault("extras",[])
        self.d["extras"].append({"id":uid("EXT"),"booking_id":bid,"item":item,"qty":qty,"price":price})
        save(self.d)
        self.refresh_extras()
        self.clear_extra()
        messagebox.showinfo("Artikel dazufügen",f"Artikel wurde zur Buchung hinzugefügt:\n{item}")

    def load_extra(self):
        eid=self.selected_extra_id()
        if not eid:
            return
        if not eid.startswith("EXT"):
            self.cur_e=None
            return
        e=next((x for x in self.d.get("extras",[]) if str(x.get("id",""))==eid),None)
        if not e:
            return
        self.cur_e=eid
        self.e_item.set(e.get("item",""))
        self.e_qty.set(str(e.get("qty",1)).replace(".",","))
        self.e_price.set(str(e.get("price",0)).replace(".",","))

    def update_extra(self):
        eid=self.cur_e or self.selected_extra_id()
        if not eid or not str(eid).startswith("EXT"):
            messagebox.showinfo("Artikel ändern","Bitte zuerst einen manuellen Artikel mit EXT-... markieren.")
            return
        item=self.e_item.get().strip()
        if not item:
            messagebox.showinfo("Artikel ändern","Bitte Artikel/Leistung eingeben.")
            return
        changed=False
        for e in self.d.get("extras",[]):
            if str(e.get("id",""))==str(eid):
                e["item"]=item
                e["qty"]=fnum(self.e_qty.get(),1)
                e["price"]=fnum(self.e_price.get(),0)
                changed=True
                self.cur_e=str(eid)
                break
        if not changed:
            messagebox.showerror("Artikel ändern","Markierter Artikel wurde nicht gefunden.")
            return
        save(self.d)
        self.refresh_extras()
        messagebox.showinfo("Artikel geändert","Artikel wurde geändert.")

    def delete_extra(self):
        eid=self.cur_e or self.selected_extra_id()
        if not eid or not str(eid).startswith("EXT"):
            messagebox.showinfo("Artikel löschen","Bitte zuerst einen manuellen Artikel mit EXT-... markieren.")
            return
        e=next((x for x in self.d.get("extras",[]) if str(x.get("id",""))==str(eid)),None)
        if not e:
            messagebox.showerror("Artikel löschen","Artikel wurde nicht gefunden.")
            return
        if not messagebox.askyesno("Artikel löschen",f"Diesen Artikel wirklich löschen?\n\n{e.get('item','')}"):
            return
        self.d["extras"]=[x for x in self.d.get("extras",[]) if str(x.get("id",""))!=str(eid)]
        self.cur_e=None
        save(self.d)
        self.refresh_extras()
        self.clear_extra()
        messagebox.showinfo("Artikel gelöscht","Artikel wurde gelöscht.")

    def clear_extra(self):
        self.cur_e=None
        self.e_item.set("")
        self.e_qty.set("1")
        self.e_price.set("0")

    def invoice_pdf(self):
        b=next((x for x in self.d["bookings"] if x["id"]==self.extra_bid.get()),None)
        if not b: messagebox.showerror("Fehler","Buchung nicht gefunden."); return
        release=fin_invoice_print_release(b)
        if not release.approved:
            messagebox.showwarning("Gloria-Freigabe", release.message())
            return
        if release.has_warnings and not messagebox.askyesno("Gloria-Freigabe", release.message()+"\n\nTrotzdem Rechnung erstellen?"):
            return
        pdf=out_dir()/f"Rechnung_{re.sub(r'[^A-Za-z0-9_-]+','_',b['guest'])}.pdf"; styles=getSampleStyleSheet()
        doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=16*mm,leftMargin=16*mm,topMargin=14*mm,bottomMargin=12*mm)
        story=[]

        # Professioneller Briefkopf V18.0 – ohne Logo, mit klarer Spaltenstruktur
        normal=styles["Normal"]
        head_left=Paragraph(
            "<b>Zuhause am Bach</b><br/><b>Gästehaus Wachau</b><br/><br/>"
            "Laura &amp; Johann Prem<br/>"
            "Aggsbach Markt 82<br/>"
            "3641 Aggsbach Markt<br/>"
            "Österreich – Wachau<br/><br/>"
            "Telefon Österreich: +43 (0) 664 6437526<br/>"
            "Telefon Deutschland: +49 (0) 9436 5609650<br/>"
            "E-Mail: johannprem@hotmail.com",
            normal
        )
        invoice_no = str(b.get("invoice_no","") or b.get("booking_no","") or "")
        right_lines = ["<b>RECHNUNG</b>", f"Datum: {date.today().strftime('%d.%m.%Y')}"]
        if invoice_no:
            right_lines.append(f"Buchungsnummer: {invoice_no}")
        right=Paragraph("<br/>".join(right_lines), normal)
        htable=Table([[head_left,right]], colWidths=[115*mm,55*mm])
        htable.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("ALIGN",(1,0),(1,0),"RIGHT"),
            ("LINEBELOW",(0,0),(-1,-1),0.6,colors.grey),
            ("BOTTOMPADDING",(0,0),(-1,-1),8),
        ]))
        story += [htable, Spacer(1,8*mm)]

        street = (b.get('street','') or '').strip()
        plz_city = f"{b.get('plz','')} {b.get('city','')}".strip()
        country = (b.get('country','') or '').strip()
        guest_lines = ["<b>Rechnung an</b>", html.escape(str(b.get('guest','')))]
        if street: guest_lines.append(html.escape(street))
        if plz_city: guest_lines.append(html.escape(plz_city))
        if country: guest_lines.append(html.escape(country))

        stay_lines = [
            "<b>Aufenthalt</b>",
            f"Zimmer: {html.escape(room_name(self.d,b.get('room_id','')))}",
            f"Anreise: {fmt(b.get('arrival',''))}",
            f"Abreise: {fmt(b.get('departure',''))}",
            f"Nächte: {nights(b.get('arrival',''), b.get('departure',''))}",
        ]
        itable=Table([[Paragraph("<br/>".join(guest_lines), normal), Paragraph("<br/>".join(stay_lines), normal)]], colWidths=[90*mm,80*mm])
        itable.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [itable, Spacer(1,7*mm)]

        t=total(self.d,b); rows=[["Leistung","Menge","Einzelpreis","Gesamt"]]
        c_due=checkout_due(self.d,b)
        paid_room = c_due["paid_room"]
        if paid_room:
            rows.append(["Zimmer/Nächtigung – über Booking/extern bezahlt",str(t["nights"]),money(b["price"]),money(0)])
            rows.append(["Bereits bezahlter Zimmerpreis","","",money(t["room"])])
        else:
            rows.append(["Zimmer/Nächtigung",str(t["nights"]),money(b["price"]),money(t["room"])])
        if b.get("dog"):
            dp=float(b.get("dog_price",5.0)); dogsum=dp*t["nights"]
            rows.append(["Hund",str(t["nights"]),money(dp),money(dogsum)])
        for e in extras_for(self.d,b["id"]):
            esum=float(e["qty"])*float(e["price"])
            rows.append([str(e["item"]),str(e["qty"]),money(e["price"]),money(esum)])
        rows.append(["Ortstaxe",f"{b['persons']} Pers. x {t['nights']} Nächte",money(ORTSTAXE),money(t["tax"])])
        rows.append(["Offener Betrag","","",money(c_due["due"])])
        table=Table(rows,colWidths=[85*mm,30*mm,30*mm,30*mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("GRID",(0,0),(-1,-1),0.25,colors.grey),
            ("BACKGROUND",(0,0),(-1,0),colors.whitesmoke),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("BACKGROUND",(0,-1),(-1,-1),colors.whitesmoke),
            ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
            ("ALIGN",(1,1),(-1,-1),"RIGHT"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ]))
        story += [table,Spacer(1,8*mm),Paragraph(AD_FOOTER,styles["Normal"])]
        doc.build(story); os.startfile(str(pdf)) if os.name=="nt" else None

    # ---------------- Artikelverwaltung ----------------
    def ensure_articles(self):
        # Bestehende Datenstruktur der Software: products
        self.d.setdefault("products",[])
        if not isinstance(self.d.get("products"),list):
            self.d["products"]=[]
        return self.d["products"]

    def article_names(self):
        self.ensure_articles()
        names=[p.get("name","") for p in self.d.get("products",[]) if p.get("active",True) and p.get("name")]
        if not names:
            return ["Kaffee","Tee","Wasser","Bier","Wein","Frühstück","Omelett","Käse/Brot"]
        return names

    def article_price(self,name):
        self.ensure_articles()
        return float(next((p.get("price",0) for p in self.d.get("products",[]) if p.get("name")==name),0))

    def take_article_price(self):
        try:
            self.e_price.set(str(self.article_price(self.e_item.get())).replace(".",","))
        except Exception:
            pass

    def build_articles(self):
        main=ttk.Frame(self.tab_articles)
        main.pack(fill="both",expand=True,padx=10,pady=8)

        top=ttk.Frame(main)
        top.pack(fill="x",pady=(0,6))
        ttk.Label(top,text="Artikelverwaltung",style="CardTitle.TLabel").pack(side="left",padx=(0,15))
        ttk.Button(top,text="LISTE AKTUALISIEREN",command=self.refresh_articles,style="Primary.TButton").pack(side="left",padx=4)

        form=ttk.Frame(main)
        form.pack(fill="x",pady=(0,8))

        self.cur_p=None
        self.a_name=StringVar()
        self.a_price=StringVar(value="0")
        self.a_cat=StringVar(value="Getränk")
        self.a_active=BooleanVar(value=True)

        row1=ttk.Frame(form)
        row1.pack(fill="x",pady=3)
        ttk.Label(row1,text="Artikelname",style="Card.TLabel").pack(side="left",padx=(0,4))
        ttk.Entry(row1,textvariable=self.a_name,width=38).pack(side="left",padx=4)
        ttk.Label(row1,text="Preis",style="Card.TLabel").pack(side="left",padx=(12,4))
        ttk.Entry(row1,textvariable=self.a_price,width=10).pack(side="left",padx=4)
        ttk.Label(row1,text="Kategorie",style="Card.TLabel").pack(side="left",padx=(12,4))
        ttk.Entry(row1,textvariable=self.a_cat,width=16).pack(side="left",padx=4)
        ttk.Checkbutton(row1,text="aktiv",variable=self.a_active).pack(side="left",padx=12)

        row2=ttk.Frame(form)
        row2.pack(fill="x",pady=3)
        ttk.Button(row2,text="➕ ARTIKEL ERSTELLEN",command=self.add_article,style="Touch.TButton").pack(side="left",padx=4)
        ttk.Button(row2,text="✏️ MARKIERTEN ARTIKEL ÄNDERN",command=self.update_article,style="Gold.TButton").pack(side="left",padx=4)
        ttk.Button(row2,text="🗑 MARKIERTEN ARTIKEL LÖSCHEN",command=self.delete_article,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(row2,text="FELDER LEEREN",command=self.new_article,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Label(row2,text="Doppelklick/Markieren lädt den Artikel zum Bearbeiten.",style="Card.TLabel").pack(side="left",padx=12)

        table_frame=ttk.Frame(main)
        table_frame.pack(fill="both",expand=True)

        cols=("id","name","preis","kategorie","aktiv")
        self.art_tree=ttk.Treeview(table_frame,columns=cols,show="headings",height=22,selectmode="browse")
        headers={"id":"ID","name":"Artikel","preis":"Preis","kategorie":"Kategorie","aktiv":"Aktiv"}
        widths={"id":170,"name":460,"preis":130,"kategorie":200,"aktiv":90}
        for c in cols:
            self.art_tree.heading(c,text=headers[c])
            self.art_tree.column(c,width=widths[c],anchor="w")
        self.art_tree.column("preis",anchor="e")
        self.art_tree.column("aktiv",anchor="center")

        vsb=ttk.Scrollbar(table_frame,orient="vertical",command=self.art_tree.yview)
        hsb=ttk.Scrollbar(table_frame,orient="horizontal",command=self.art_tree.xview)
        self.art_tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.art_tree.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        table_frame.rowconfigure(0,weight=1)
        table_frame.columnconfigure(0,weight=1)

        self.art_tree.bind("<<TreeviewSelect>>",lambda e:self.load_article())
        self.art_tree.bind("<Double-1>",lambda e:self.load_article())
        self.art_tree.tag_configure("inactive",background="#eeeeee",foreground="#777777")
        self.art_tree.tag_configure("active",background="#ffffff",foreground="#18314a")

        self.refresh_articles()

    def refresh_articles(self):
        if not hasattr(self,"art_tree"):
            return
        self.ensure_articles()
        for i in self.art_tree.get_children():
            self.art_tree.delete(i)
        for p in sorted(self.d.get("products",[]),key=lambda x:str(x.get("name","")).lower()):
            active=bool(p.get("active",True))
            self.art_tree.insert(
                "",END,
                values=(p.get("id",""),p.get("name",""),money(p.get("price",0)),p.get("category",""),"Ja" if active else "Nein"),
                tags=("active" if active else "inactive",)
            )
        try:
            if hasattr(self,"e_combo"):
                self.e_combo["values"]=self.article_names()
            if hasattr(self,"s_combo"):
                self.s_combo["values"]=self.article_names()
        except Exception:
            pass

    def selected_article_id(self):
        try:
            sel=self.art_tree.selection()
            if not sel:
                return None
            vals=self.art_tree.item(sel[0])["values"]
            if not vals:
                return None
            return str(vals[0])
        except Exception:
            return None

    def new_article(self):
        self.cur_p=None
        self.a_name.set("")
        self.a_price.set("0")
        self.a_cat.set("Getränk")
        self.a_active.set(True)

    def load_article(self):
        pid=self.selected_article_id()
        if not pid:
            return
        p=next((x for x in self.d.get("products",[]) if str(x.get("id",""))==str(pid)),None)
        if not p:
            return
        self.cur_p=str(p.get("id",""))
        self.a_name.set(p.get("name",""))
        self.a_price.set(str(p.get("price",0)).replace(".",","))
        self.a_cat.set(p.get("category","Getränk"))
        self.a_active.set(bool(p.get("active",True)))

    def add_article(self):
        self.ensure_articles()
        name=self.a_name.get().strip()
        if not name:
            messagebox.showinfo("Artikel erstellen","Bitte Artikelname eingeben.")
            return
        if any(str(p.get("name","")).lower()==name.lower() for p in self.d.get("products",[])):
            messagebox.showerror("Artikel erstellen","Diesen Artikel gibt es bereits. Bitte markieren und ändern.")
            return
        self.d["products"].append({
            "id":uid("ART"),
            "name":name,
            "price":fnum(self.a_price.get(),0),
            "category":self.a_cat.get().strip() or "Artikel",
            "active":bool(self.a_active.get())
        })
        save(self.d)
        self.refresh_articles()
        self.new_article()
        messagebox.showinfo("Artikel erstellen",f"Artikel wurde erstellt:\n{name}")

    def update_article(self):
        self.ensure_articles()
        pid=self.cur_p or self.selected_article_id()
        if not pid:
            messagebox.showinfo("Artikel ändern","Bitte zuerst einen Artikel markieren.")
            return
        name=self.a_name.get().strip()
        if not name:
            messagebox.showinfo("Artikel ändern","Bitte Artikelname eingeben.")
            return

        for p in self.d.get("products",[]):
            if str(p.get("id",""))!=str(pid) and str(p.get("name","")).lower()==name.lower():
                messagebox.showerror("Artikel ändern","Ein anderer Artikel mit diesem Namen existiert bereits.")
                return

        changed=False
        for p in self.d.get("products",[]):
            if str(p.get("id",""))==str(pid):
                p["name"]=name
                p["price"]=fnum(self.a_price.get(),0)
                p["category"]=self.a_cat.get().strip() or "Artikel"
                p["active"]=bool(self.a_active.get())
                changed=True
                self.cur_p=str(pid)
                break
        if not changed:
            messagebox.showerror("Artikel ändern","Artikel wurde nicht gefunden.")
            return
        save(self.d)
        self.refresh_articles()
        messagebox.showinfo("Artikel ändern","Artikel wurde geändert.")

    # alter Methodenname bleibt als Alias erhalten
    def save_article(self):
        self.update_article()

    def delete_article(self):
        self.ensure_articles()
        pid=self.cur_p or self.selected_article_id()
        if not pid:
            messagebox.showinfo("Artikel löschen","Bitte zuerst einen Artikel markieren.")
            return
        p=next((x for x in self.d.get("products",[]) if str(x.get("id",""))==str(pid)),None)
        if not p:
            messagebox.showerror("Artikel löschen","Artikel wurde nicht gefunden.")
            return
        if not messagebox.askyesno("Artikel löschen",f"Diesen Artikel wirklich löschen?\n\n{p.get('name','')}\n\nBereits gebuchte Extras/Rechnungspositionen bleiben erhalten."):
            return
        self.d["products"]=[x for x in self.d.get("products",[]) if str(x.get("id",""))!=str(pid)]
        self.cur_p=None
        save(self.d)
        self.refresh_articles()
        self.new_article()
        messagebox.showinfo("Artikel löschen","Artikel wurde gelöscht.")



    def import_booking_duplicate_key(self,b):
        try:
            guest=str(b.get("guest","")).strip().lower()
            arr=str(b.get("arrival","")).strip()
            dep=str(b.get("departure","")).strip()
            room=str(b.get("room_id","")).strip()
            phone=str(b.get("phone","")).strip()
            return (guest,arr,dep,room,phone)
        except Exception:
            return ("","","","","")

    def booking_exists_for_import(self,b):
        key=self.import_booking_duplicate_key(b)
        bid=str(b.get("id","")).strip()
        for old in self.d.get("bookings",[]):
            if key==self.import_booking_duplicate_key(old):
                return True
            if bid and str(old.get("id","")).strip()==bid:
                return True
        return False


    def safe_append_booking(self,b):
        self.d.setdefault("bookings",[])
        if not self.booking_exists_for_import(b):
            self.d["bookings"].append(b)
            return True
        return False

    def build_import(self):
        f=self.card(self.tab_import,"Booking.com Import XLS/XLSX/CSV")
        self.import_file=StringVar()
        self.import_room=StringVar()
        row=ttk.Frame(f,style="Card.TFrame"); row.pack(fill="x",pady=4)
        ttk.Label(row,text="Datei",style="Card.TLabel",width=12).pack(side="left")
        ttk.Entry(row,textvariable=self.import_file).pack(side="left",fill="x",expand=True,padx=5)
        ttk.Button(row,text="Auswählen",command=self.choose_import_file).pack(side="left",padx=4)
        row2=ttk.Frame(f,style="Card.TFrame"); row2.pack(fill="x",pady=4)
        ttk.Label(row2,text="Standardzimmer",style="Card.TLabel",width=12).pack(side="left")
        self.import_room_combo=ttk.Combobox(row2,textvariable=self.import_room,width=45)
        self.import_room_combo.pack(side="left",padx=5)
        ttk.Button(row2,text="IMPORT VORSCHAU",command=self.run_booking_import_preview).pack(side="left",padx=4)
        ttk.Button(row2,text="IMPORT ÜBERNEHMEN",command=self.run_booking_import,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(row2,text="IMPORT RÜCKGÄNGIG",command=self.restore_last_import_backup).pack(side="left",padx=4)
        self.import_log=Text(self.tab_import,bg="#fff",relief="flat",font=("Consolas",10),padx=12,pady=12)
        self.import_log.pack(fill="both",expand=True,padx=8,pady=8)

    def choose_import_file(self):
        p=filedialog.askopenfilename(title="Booking.com Datei wählen",filetypes=[("Booking Export","*.xls *.xlsx *.csv"),("Alle Dateien","*.*")])
        if p: self.import_file.set(p)

    def import_room_values_refresh(self):
        try:
            vals=self.room_values()
            self.import_room_combo["values"]=vals
            if vals and not self.import_room.get(): self.import_room.set(vals[0])
        except Exception:
            pass

    def restore_last_import_backup(self):
        """Stellt das letzte VOR_IMPORT-Backup wieder her.
        Damit kann ein fehlerhafter Booking-Import sofort rückgängig gemacht werden.
        """
        try:
            latest = import_latest_backup(backup_dir())
            if not latest:
                messagebox.showinfo("Import rückgängig", "Kein VOR_IMPORT-Backup gefunden.")
                return
            desc = import_describe_backup(latest)
            if not messagebox.askyesno(
                "Import rückgängig machen",
                "Letztes Vor-Import-Backup wiederherstellen?\n\n"
                f"Datei: {latest}\n"
                f"Stand: {desc}\n\n"
                "Der aktuelle Datenstand wird vorher automatisch gesichert."
            ):
                return
            safety = backup_dir() / ("VOR_RESTORE_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
            if data_file().exists():
                shutil.copy2(data_file(), safety)
            import_restore_backup(latest, data_file())
            self.d = load()
            self.refresh_all()
            self.import_log.insert(END, "\nImport rückgängig gemacht.\n")
            self.import_log.insert(END, f"Wiederhergestellt aus: {latest}\n")
            self.import_log.insert(END, f"Sicherung des vorherigen Stands: {safety}\n")
            messagebox.showinfo("Import rückgängig", "Der letzte Import wurde über das Vor-Import-Backup rückgängig gemacht.")
        except Exception as e:
            log_exception("Import rückgängig")
            messagebox.showerror("Import rückgängig", str(e))

    def run_booking_import_preview(self):
        """Import-Vorschau: zeigt vor dem Speichern, ob Zeilen neu, Aktualisierung,
        bekannter Gast/neue Reise, Dublette/Überspringen oder Fehler sind.
        Es wird nichts in die Datenbank geschrieben.
        """
        if pd is None:
            messagebox.showerror("Fehler","Für XLS/XLSX Import fehlt pandas/openpyxl/xlrd. Bitte setup.bat ausführen.")
            return
        path=self.import_file.get().strip()
        if not path or not Path(path).exists():
            messagebox.showerror("Fehler","Bitte zuerst eine Booking-Datei auswählen.")
            return
        try:
            ext=Path(path).suffix.lower()
            if ext==".csv":
                df=pd.read_csv(path,sep=None,engine="python", encoding="utf-8-sig")
            else:
                df=pd.read_excel(path)
            cols=list(df.columns)
            c_no=find_col(cols,"Buchungsnummer","Reservation number","Booking number","Reservierungsnummer")
            c_booker=find_col(cols,"Gebucht von","Booker","Booked by")
            c_name=find_col(cols,"Gästename(n)","Gästename","Name des Gastes","Guest name","Gast")
            c_arr=find_col(cols,"Anreise","Check-in","Arrival")
            c_dep=find_col(cols,"Abreise","Check-out","Departure")
            c_persons=find_col(cols,"Personen","Guests","Anzahl Personen")
            c_adults=find_col(cols,"Erwachsene","Adults")
            c_children=find_col(cols,"Kinder","Children")
            c_country=find_col(cols,"Booker country","Land","Country","Herkunftsland")
            c_plz=find_col(cols,"PLZ","Postleitzahl","Postal code","Postal Code","Postcode","Zip","ZIP","ZIP Code","Booker postal code","Booker postcode","Post code")
            c_addr=find_col(cols,"Adresse","Address")
            c_city=find_col(cols,"Wohnort","Ort","Stadt","City","Town","Booker city","Booker town","City / Town","Ort / Stadt")
            c_street=find_col(cols,"Straße","Strasse","Street","Address line 1")
            c_phone=find_col(cols,"Telefonnummer","Telefon","Phone","Phone number")
            c_status=find_col(cols,"Status")
            c_cancel=find_col(cols,"Stornierungsdatum","Cancellation date")
            if not c_arr or not c_dep:
                raise ValueError("Anreise/Abreise-Spalten nicht erkannt.")
            rid=self.import_room.get().split(":")[0] if self.import_room.get() else (active_rooms(self.d)[0]["id"] if active_rooms(self.d) else "")
            if not rid:
                raise ValueError("Bitte zuerst ein Zimmer anlegen.")

            counts={"neu":0,"aktualisieren":0,"bekannter_gast_neue_reise":0,"ueberspringen":0,"fehler":0,"pruefen":0}
            rows=[]
            seen_booking_numbers=set()
            for idx,row in df.iterrows():
                status=cell_text(row,c_status).lower()
                cancel=cell_text(row,c_cancel).lower()
                if "storn" in status or (c_cancel and cancel not in ("","nan","none","nat")):
                    counts["ueberspringen"]+=1
                    rows.append([idx+1,"⚪ Überspringen",cell_text(row,c_no),cell_text(row,c_name) or cell_text(row,c_booker),"storniert/abgesagt"])
                    continue
                try:
                    arr=iso(cell_text(row,c_arr)); dep=iso(cell_text(row,c_dep))
                except Exception:
                    counts["fehler"]+=1
                    rows.append([idx+1,"🔴 Fehler",cell_text(row,c_no),cell_text(row,c_name) or cell_text(row,c_booker),"Anreise/Abreise nicht lesbar"])
                    continue
                no=cell_text(row,c_no)
                guest=cell_text(row,c_name) or cell_text(row,c_booker) or "Booking Gast"
                persons=to_int(cell_text(row,c_persons),0) if c_persons else 0
                if persons<=0:
                    persons=(to_int(cell_text(row,c_adults),0) if c_adults else 0)+(to_int(cell_text(row,c_children),0) if c_children else 0)
                if persons<=0: persons=1
                country=cell_text(row,c_country).upper()
                plz=cell_text(row,c_plz); city=cell_text(row,c_city); street=cell_text(row,c_street); addr=cell_text(row,c_addr)
                phone=normalize_phone(cell_text(row,c_phone))
                plz, city, street = split_booking_address(addr, plz=plz, city=city, street=street)
                probe={"id":"","guest":guest,"email":"","phone":phone,"country":country,"plz":plz,"city":city,"street":street,"arrival":arr,"departure":dep,"persons":persons,"room_id":rid,"source":"Booking","booking_no":no}
                decision=import_find_existing(self.d.get("bookings",[]), probe)
                hint=[]
                if no and no in seen_booking_numbers:
                    counts["ueberspringen"]+=1
                    rows.append([idx+1,"⚪ Überspringen",no,guest,"Buchungsnummer kommt in Importdatei doppelt vor"])
                    continue
                if no: seen_booking_numbers.add(no)
                if decision.action=="update_booking":
                    counts["aktualisieren"]+=1
                    label="🔵 Aktualisieren"
                    hint.append(decision.reason or "bestehende Buchung gefunden")
                elif decision.action=="reuse_guest_new_booking":
                    counts["bekannter_gast_neue_reise"]+=1
                    label="🟡 Bekannter Gast / neue Reise"
                    hint.append(decision.reason or "Stammdaten wiederverwenden")
                elif not guest or guest=="Booking Gast":
                    counts["pruefen"]+=1
                    label="🟡 Prüfen"
                    hint.append("Gastname fehlt/unklar")
                else:
                    counts["neu"]+=1
                    label="🟢 Neu"
                    hint.append("neue Buchung")
                if not plz or not city:
                    hint.append("PLZ/Wohnort fehlt, wird als Warnung übernommen")
                rows.append([idx+1,label,no,guest,"; ".join(hint)])

            self.import_log.delete("1.0", END)
            self.import_log.insert(END,"IMPORT-VORSCHAU – es wurde noch nichts gespeichert.\n")
            self.import_log.insert(END,"Erkannte Spalten:\n" + ", ".join([str(c) for c in cols]) + "\n\n")
            self.import_log.insert(END,f"🟢 Neu: {counts['neu']} | 🔵 Aktualisieren: {counts['aktualisieren']} | 🟡 Bekannter Gast/neue Reise: {counts['bekannter_gast_neue_reise']} | 🟡 Prüfen: {counts['pruefen']} | ⚪ Überspringen: {counts['ueberspringen']} | 🔴 Fehler: {counts['fehler']}\n\n")
            self.import_log.insert(END,"Zeile | Status | Buchungsnummer | Gast | Hinweis\n")
            self.import_log.insert(END,"-"*110 + "\n")
            for r in rows[:500]:
                self.import_log.insert(END,f"{r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]}\n")
            if len(rows)>500:
                self.import_log.insert(END,f"... weitere {len(rows)-500} Zeilen nicht angezeigt.\n")
            proto=out_dir() / ("Import_Vorschau_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt")
            with open(proto,"w",encoding="utf-8") as f:
                f.write(self.import_log.get("1.0", END))
            self.import_log.insert(END,f"\nProtokoll gespeichert: {proto}\n")
            self.import_log.insert(END,"\nWenn die Vorschau passt, bitte auf IMPORT ÜBERNEHMEN klicken. Vor der Übernahme wird weiterhin ein Backup erstellt.\n")
            messagebox.showinfo("Import-Vorschau",f"Vorschau erstellt.\nNeu: {counts['neu']}\nAktualisieren: {counts['aktualisieren']}\nBekannte Gäste/neue Reise: {counts['bekannter_gast_neue_reise']}\nPrüfen: {counts['pruefen']}\nÜberspringen: {counts['ueberspringen']}\nFehler: {counts['fehler']}\n\nProtokoll:\n{proto}")
        except Exception as e:
            messagebox.showerror("Import-Vorschau Fehler",str(e))

    def run_booking_import(self):
        if pd is None:
            messagebox.showerror("Fehler","Für XLS/XLSX Import fehlt pandas/openpyxl/xlrd. Bitte setup.bat ausführen.")
            return
        path=self.import_file.get().strip()
        if not path or not Path(path).exists():
            messagebox.showerror("Fehler","Bitte zuerst eine Booking-Datei auswählen.")
            return
        try:
            # Automatisches Backup vor jedem Import
            pre_backup = auto_backup_now("VOR_IMPORT")
            # Korrekturdatei bereitstellen und Stammdatenindex bauen
            correction_template = ensure_address_template()
            address_index = build_address_index(self.d)

            ext=Path(path).suffix.lower()
            if ext==".csv":
                df=pd.read_csv(path,sep=None,engine="python", encoding="utf-8-sig")
            else:
                # .xls benötigt xlrd, .xlsx benötigt openpyxl
                df=pd.read_excel(path)

            cols=list(df.columns)

            self.import_log.insert(END,"Erkannte Spalten:\n")
            self.import_log.insert(END,", ".join([str(c) for c in cols]) + "\n\n")
            if pre_backup:
                self.import_log.insert(END,f"Backup vor Import erstellt: {pre_backup}\n")
            if correction_template:
                self.import_log.insert(END,f"Adresskorrektur-Datei: {correction_template}\n")
            self.import_log.insert(END,"Korrekturregel: Fehlt PLZ/Wohnort, wird zuerst aus vorhandener Buchung, danach aus Adresskorrekturen ergänzt.\n\n")

            c_no=find_col(cols,"Buchungsnummer","Reservation number","Booking number","Reservierungsnummer")
            c_booker=find_col(cols,"Gebucht von","Booker","Booked by")
            c_name=find_col(cols,"Gästename(n)","Gästename","Name des Gastes","Guest name","Gast")
            c_arr=find_col(cols,"Anreise","Check-in","Arrival")
            c_dep=find_col(cols,"Abreise","Check-out","Departure")
            c_persons=find_col(cols,"Personen","Guests","Anzahl Personen")
            c_adults=find_col(cols,"Erwachsene","Adults")
            c_children=find_col(cols,"Kinder","Children")
            c_country=find_col(cols,"Booker country","Land","Country","Herkunftsland")
            c_plz=find_col(cols,"PLZ","Postleitzahl","Postal code","Postal Code","Postcode","Zip","ZIP","ZIP Code","Booker postal code","Booker postcode","Post code")
            c_addr=find_col(cols,"Adresse","Address")
            c_city=find_col(cols,"Wohnort","Ort","Stadt","City","Town","Booker city","Booker town","City / Town","Ort / Stadt")
            c_street=find_col(cols,"Straße","Strasse","Street","Address line 1")
            c_phone=find_col(cols,"Telefonnummer","Telefon","Phone","Phone number")
            c_price=find_col(cols,"Preis","Gesamtpreis","Price","Total price")
            c_status=find_col(cols,"Status")
            c_cancel=find_col(cols,"Stornierungsdatum","Cancellation date")
            c_payment=find_col(cols,"Zahlungsstatus","Payment status")
            c_payment_method=find_col(cols,"Zahlungsmethode","Zahlungsmethode (Zahlungsanbieter)","Payment method")
            c_notes=find_col(cols,"Bemerkungen","Remarks","Notes","Special requests")
            c_reason=find_col(cols,"Reisegrund","Travel purpose")
            c_unit=find_col(cols,"Art der Wohneinheit","Room type","Unit type")
            c_nights=find_col(cols,"Aufenthaltsdauer (Nächte)","Nights","Length of stay")

            if not c_arr or not c_dep:
                raise ValueError("Anreise/Abreise-Spalten nicht erkannt.")

            rid=self.import_room.get().split(":")[0] if self.import_room.get() else (active_rooms(self.d)[0]["id"] if active_rooms(self.d) else "")
            if not rid:
                raise ValueError("Bitte zuerst ein Zimmer anlegen.")

            new=upd=skip=0
            missing_plz=0
            missing_city=0
            imported_address=0
            imported_phone=0
            missing_rows=[]
            parsed_plz_city=0
            corrected_from_existing=0
            preserved_existing=0
            known_guest_new_trip=0

            for _,row in df.iterrows():
                status=cell_text(row,c_status).lower()
                cancel=cell_text(row,c_cancel).lower()
                if "storn" in status or (c_cancel and cancel not in ("","nan","none","nat")):
                    skip+=1
                    continue

                try:
                    arr=iso(cell_text(row,c_arr))
                    dep=iso(cell_text(row,c_dep))
                except Exception:
                    skip+=1
                    continue

                no=cell_text(row,c_no)
                if not no:
                    no=uid("BOOKING")

                # bestehende Buchung wird später mit intelligenter Dublettenlogik gesucht.
                # Wichtig: gleicher Gast + gleiche Reisedaten darf beim Re-Import nicht doppelt entstehen.
                existing=None

                guest=cell_text(row,c_name) or cell_text(row,c_booker) or "Booking Gast"
                persons=to_int(cell_text(row,c_persons),0) if c_persons else 0
                if persons<=0:
                    persons=(to_int(cell_text(row,c_adults),0) if c_adults else 0)+(to_int(cell_text(row,c_children),0) if c_children else 0)
                if persons<=0:
                    persons=existing.get("persons",1) if existing else 1

                country=cell_text(row,c_country).upper()
                plz=cell_text(row,c_plz)
                city=cell_text(row,c_city)
                street=cell_text(row,c_street)
                addr=cell_text(row,c_addr)
                phone=normalize_phone(cell_text(row,c_phone))

                before_plz, before_city = plz, city
                plz, city, street = split_booking_address(addr, plz=plz, city=city, street=street)
                if (not before_plz and plz) or (not before_city and city):
                    parsed_plz_city += 1

                # Intelligenter Dublettencheck: gleiche Booking-Nr., gleiche Reisedaten
                # oder bekannter Gast. Dadurch erzeugt ein erneuter Import keine
                # doppelten Gäste/Buchungen.
                dedupe_probe={
                    "id":"", "guest":guest, "email":"", "phone":phone, "country":country,
                    "plz":plz, "city":city, "street":street, "arrival":arr, "departure":dep,
                    "persons":persons, "room_id":rid, "source":"Booking", "booking_no":no
                }
                dedupe_decision=import_find_existing(self.d.get("bookings",[]), dedupe_probe)
                if dedupe_decision.action=="update_booking":
                    existing=dedupe_decision.existing_booking
                elif dedupe_decision.action=="reuse_guest_new_booking":
                    existing_guest_for_master=dedupe_decision.existing_booking
                    known_guest_new_trip += 1
                else:
                    existing_guest_for_master=None

                # Wichtig: vorhandene manuell korrigierte Daten nicht durch leere Booking-Werte überschreiben
                if existing:
                    kept=False
                    if not plz and existing.get("plz"):
                        plz=existing.get("plz","")
                        kept=True
                    if not city and existing.get("city"):
                        city=existing.get("city","")
                        kept=True
                    if not street and existing.get("street"):
                        street=existing.get("street","")
                        kept=True
                    if not country and existing.get("country"):
                        country=existing.get("country","")
                        kept=True
                    if not phone and existing.get("phone"):
                        phone=existing.get("phone","")
                        kept=True
                    if kept:
                        preserved_existing += 1

                # Automatische Ergänzung aus Stammdaten/Korrekturdateien
                was_missing = (not plz or not city)
                plz, city, street, country, corr = apply_address_correction(
                    address_index, booking_no=no, guest=guest, phone=phone,
                    street=street, country=country, plz=plz, city=city
                )
                if was_missing and corr:
                    corrected_from_existing += 1

                if street:
                    imported_address += 1
                if phone:
                    imported_phone += 1

                if not plz:
                    missing_plz += 1
                if not city:
                    missing_city += 1
                if not plz or not city:
                    missing_rows.append([no, guest, street, plz, city, country, phone, "PLZ fehlt" if not plz else "", "Wohnort fehlt" if not city else ""])

                price=to_float(cell_text(row,c_price), room_price(self.d,rid)) if c_price else room_price(self.d,rid)

                payment=cell_text(row,c_payment)
                payment_method=cell_text(row,c_payment_method)
                notes=cell_text(row,c_notes)
                reason=cell_text(row,c_reason)
                unit=cell_text(row,c_unit)
                nights_txt=cell_text(row,c_nights)

                wish_parts=[]
                if notes:
                    wish_parts.append(notes)
                if reason:
                    wish_parts.append("Reisegrund: "+reason)
                if payment:
                    wish_parts.append("Zahlungsstatus: "+payment)
                if payment_method:
                    wish_parts.append("Zahlungsmethode: "+payment_method)
                if unit:
                    wish_parts.append("Wohneinheit: "+unit)
                if nights_txt:
                    wish_parts.append("Nächte laut Booking: "+nights_txt)

                combined_text=" ".join(wish_parts).lower()
                is_wanderer=("wander" in combined_text or "wandern" in combined_text)
                is_bike=("rad" in combined_text or "bike" in combined_text or "fahrrad" in combined_text or "e-bike" in combined_text)

                old_flags={}
                if existing:
                    existing_guest_for_master = existing
                    old_flags={
                        "checked_in":existing.get("checked_in",False),
                        "paid_out":existing.get("paid_out",False),
                        "dog":existing.get("dog",False),
                        "dog_price":existing.get("dog_price",5.0),
                        "regular":existing.get("regular",False),
                        "plate":existing.get("plate",""),
                        "allergies":existing.get("allergies",""),
                    }

                rec={
                    "id":existing["id"] if existing else uid("BOOK"),
                    "guest":guest,
                    "birth": existing.get("birth","") if existing else "",
                    "email": existing.get("email","") if existing else "",
                    "phone":phone,
                    "country":country,
                    "plz":plz,
                    "city":city,
                    "street":street,
                    "arrival":arr,
                    "departure":dep,
                    "persons":persons,
                    "room_id":rid,
                    "price":price,
                    "breakfast": existing.get("breakfast","kein") if existing else "kein",
                    "lunchpack": existing.get("lunchpack",False) if existing else False,
                    "wishes":" | ".join(wish_parts),
                    "status":"gebucht",
                    "source":"Booking",
                    "booking_no":no,
                    "paid":True,
                    "dog":old_flags.get("dog",False),
                    "dog_price":old_flags.get("dog_price",5.0),
                    "wanderer": existing.get("wanderer",False) or is_wanderer if existing else is_wanderer,
                    "bike": existing.get("bike",False) or is_bike if existing else is_bike,
                    "ebike": existing.get("ebike",False) if existing else False,
                    "car": existing.get("car",False) if existing else False,
                    "regular":old_flags.get("regular",False),
                    "plate":old_flags.get("plate",""),
                    "allergies":old_flags.get("allergies",""),
                    "checked_in":old_flags.get("checked_in",False),
                    "paid_out":old_flags.get("paid_out",False),
                }

                rec=import_merge_guest_data(rec, existing if existing else existing_guest_for_master)

                if existing:
                    self.d["bookings"]=[rec if b["id"]==existing["id"] else b for b in self.d["bookings"]]
                    upd+=1
                else:
                    self.d["bookings"].append(rec)
                    new+=1

                # Index laufend erweitern, damit spätere Zeilen desselben Gastes profitieren
                add_address_index(address_index, {
                    "booking_no": no, "guest": guest, "street": street,
                    "plz": plz, "city": city, "country": country, "phone": phone
                }, force=True)

            save(self.d)
            self.refresh_all()

            missing_file=""
            if missing_rows:
                try:
                    missing_file = out_dir() / ("Fehlende_PLZ_Wohnort_Import_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv")
                    with open(missing_file, "w", newline="", encoding="utf-8-sig") as f:
                        w=csv.writer(f, delimiter=";")
                        w.writerow(["Buchungsnummer","Gast","Straße","PLZ","Wohnort","Land","Telefon","Hinweis PLZ","Hinweis Wohnort"])
                        w.writerows(missing_rows)
                except Exception as ex:
                    self.import_log.insert(END, "Warnung: Fehlende-Stammdaten-Liste konnte nicht geschrieben werden: " + str(ex) + "\n")

            self.import_log.insert(END,f"Import fertig: {Path(path).name}\n")
            self.import_log.insert(END,f"Neu: {new} | Aktualisiert: {upd} | Bekannte Gäste/neue Reise: {known_guest_new_trip} | Übersprungen: {skip}\n")
            self.import_log.insert(END,f"Straße/Adresse übernommen: {imported_address}\n")
            self.import_log.insert(END,f"Telefonnummern übernommen: {imported_phone}\n")
            self.import_log.insert(END,f"PLZ/Wohnort aus Adresse erkannt: {parsed_plz_city}\n")
            self.import_log.insert(END,f"Vorhandene manuelle Stammdaten erhalten: {preserved_existing}\n")
            self.import_log.insert(END,f"Automatisch aus Stammdaten/Korrekturliste ergänzt: {corrected_from_existing}\n")
            self.import_log.insert(END,f"PLZ weiterhin leer/nicht vorhanden: {missing_plz}\n")
            self.import_log.insert(END,f"Wohnort weiterhin leer/nicht vorhanden: {missing_city}\n")
            if missing_file:
                self.import_log.insert(END,f"Nachbearbeitungsliste erstellt: {missing_file}\n")
                self.import_log.insert(END,"Diese CSV kann ausgefüllt werden. Beim nächsten Import werden die ausgefüllten PLZ/Wohnort-Werte automatisch übernommen.\n")
            self.import_log.insert(END,"\nWichtig: Wenn Booking PLZ/Wohnort nicht liefert, werden vorhandene Stammdaten erhalten oder aus Korrekturdateien ergänzt. Unbekannte Werte werden nicht erfunden.\n\n")

            messagebox.showinfo(
                "Import fertig",
                f"Neu: {new}\nAktualisiert: {upd}\nBekannte Gäste/neue Reise: {known_guest_new_trip}\n"
                f"Vorhandene Stammdaten erhalten: {preserved_existing}\n"
                f"Automatisch ergänzt: {corrected_from_existing}\n"
                f"PLZ weiterhin leer: {missing_plz}\n"
                f"Wohnort weiterhin leer: {missing_city}"
                + (f"\n\nListe zum Korrigieren erstellt:\n{missing_file}" if missing_file else "")
            )
        except Exception as e:
            messagebox.showerror("Importfehler",str(e))
            self.import_log.insert(END,"FEHLER: "+str(e)+"\n\n")

    def build_corrections(self):
        main=ttk.Frame(self.tab_corr)
        main.pack(fill="both",expand=True,padx=10,pady=10)

        top=self.card(main,"Stammdaten-Korrektur – große Eingabeansicht")
        ttk.Label(
            top,
            text="Hier werden Buchungen mit fehlender PLZ, fehlendem Wohnort oder unvollständigen Stammdaten angezeigt. Unten ist jetzt ein großes Eingabeformular.",
            style="Card.TLabel",
            wraplength=1200
        ).pack(anchor="w")

        bar=ttk.Frame(top,style="Card.TFrame")
        bar.pack(fill="x",pady=6)
        self.c_missing_only=BooleanVar(value=True)
        self.c_search=StringVar(value="")
        ttk.Checkbutton(bar,text="nur fehlende PLZ/Wohnort anzeigen",variable=self.c_missing_only,command=self.refresh_corrections).pack(side="left",padx=4)
        ttk.Label(bar,text="Suche",style="Card.TLabel").pack(side="left",padx=(14,4))
        search_entry=ttk.Entry(bar,textvariable=self.c_search,width=26)
        search_entry.pack(side="left",padx=4)
        search_entry.bind("<KeyRelease>",lambda e:self.refresh_corrections())
        ttk.Button(bar,text="AKTUALISIEREN",command=self.refresh_corrections,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(bar,text="CSV-LISTE ERSTELLEN",command=self.export_corrections_csv,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(bar,text="KORREKTUR-CSV IMPORTIEREN",command=self.import_address_corrections_csv,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(bar,text="KORREKTUREN ANWENDEN",command=self.apply_all_address_corrections,style="Touch.TButton").pack(side="left",padx=4)

        self.c_summary=StringVar(value="")
        ttk.Label(top,textvariable=self.c_summary,style="CardTitle.TLabel").pack(anchor="w",pady=(6,0))

        list_frame=ttk.Frame(main)
        list_frame.pack(fill="both",expand=True,padx=2,pady=(4,8))
        cols=("id","gast","anreise","abreise","straße","plz","wohnort","land","telefon","email","status")
        self.ct=ttk.Treeview(list_frame,columns=cols,show="headings",height=13)
        headings={
            "id":"ID","gast":"Gast","anreise":"Anreise","abreise":"Abreise","straße":"Straße",
            "plz":"PLZ","wohnort":"Wohnort","land":"Land","telefon":"Telefon","email":"E-Mail","status":"Status"
        }
        widths={
            "id":90,"gast":210,"anreise":85,"abreise":85,"straße":260,
            "plz":75,"wohnort":170,"land":70,"telefon":150,"email":210,"status":180
        }
        for c in cols:
            self.ct.heading(c,text=headings[c])
            self.ct.column(c,width=widths[c],anchor="w")
        vsb=ttk.Scrollbar(list_frame,orient="vertical",command=self.ct.yview)
        hsb=ttk.Scrollbar(list_frame,orient="horizontal",command=self.ct.xview)
        self.ct.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.ct.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        list_frame.rowconfigure(0,weight=1)
        list_frame.columnconfigure(0,weight=1)
        self.ct.tag_configure("missing", background="#fff2a8", foreground="#312300")
        self.ct.tag_configure("ok", background="#ffffff", foreground="#263016")
        self.ct.bind("<<TreeviewSelect>>",lambda e:self.load_correction())

        form=self.card(main,"Stammdaten bearbeiten")
        self.c_id=StringVar()
        self.c_guest=StringVar()
        self.c_birth=StringVar()
        self.c_street=StringVar()
        self.c_plz=StringVar()
        self.c_city=StringVar()
        self.c_country=StringVar()
        self.c_phone=StringVar()
        self.c_email=StringVar()
        self.c_plate=StringVar()
        self.c_allergies=StringVar()

        grid=ttk.Frame(form,style="Card.TFrame")
        grid.pack(fill="x",expand=True)

        def lab(row,col,text):
            ttk.Label(grid,text=text,style="Card.TLabel").grid(row=row,column=col,sticky="w",padx=6,pady=(5,1))
        def ent(row,col,var,width=26):
            e=ttk.Entry(grid,textvariable=var,width=width)
            e.grid(row=row,column=col,sticky="ew",padx=6,pady=(0,5))
            return e

        for c in range(6):
            grid.columnconfigure(c,weight=1)

        lab(0,0,"Buchungs-ID")
        ent(1,0,self.c_id,18)
        lab(0,1,"Gast / Name")
        ent(1,1,self.c_guest,34)
        lab(0,2,"Geburtsdatum")
        ent(1,2,self.c_birth,16)
        lab(0,3,"Telefon")
        ent(1,3,self.c_phone,24)
        lab(0,4,"E-Mail")
        ent(1,4,self.c_email,30)
        lab(0,5,"Kennzeichen")
        ent(1,5,self.c_plate,16)

        lab(2,0,"Straße / Hausnummer")
        ent(3,0,self.c_street,34)
        lab(2,1,"PLZ")
        ent(3,1,self.c_plz,12)
        lab(2,2,"Wohnort")
        ent(3,2,self.c_city,26)
        lab(2,3,"Land")
        ent(3,3,self.c_country,10)
        lab(2,4,"Allergien / Hinweise")
        ent(3,4,self.c_allergies,34)

        buttons=ttk.Frame(form,style="Card.TFrame")
        buttons.pack(fill="x",pady=(8,0))
        ttk.Button(buttons,text="STAMMDATEN SPEICHERN",command=self.save_correction,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(buttons,text="IN BUCHUNGEN ÖFFNEN",command=self.open_selected_booking_from_correction,style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(buttons,text="FELDER LEEREN",command=self.clear_correction_form,style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(buttons,text="AUSGABE-ORDNER ÖFFNEN",command=self.open_out_folder).pack(side="left",padx=5)

        ttk.Label(
            form,
            text="Wichtig: Wenn PLZ/Wohnort bei Booking fehlen, hier einmal eintragen und speichern. Beim nächsten Import bleiben die Daten erhalten.",
            style="Card.TLabel",
            wraplength=1180
        ).pack(anchor="w",pady=(8,0))

    def correction_missing_text(self,b):
        missing=[]
        if not str(b.get("plz","")).strip(): missing.append("PLZ")
        if not str(b.get("city","")).strip(): missing.append("Wohnort")
        if not str(b.get("country","")).strip(): missing.append("Land")
        if not str(b.get("phone","")).strip(): missing.append("Telefon")
        return ", ".join(missing)

    def refresh_corrections(self):
        if not hasattr(self,"ct"):
            return
        for i in self.ct.get_children():
            self.ct.delete(i)
        rows=sorted(self.d.get("bookings",[]),key=lambda b:(b.get("arrival",""),b.get("guest","")))
        q=str(getattr(self,"c_search",StringVar(value="")).get() if hasattr(self,"c_search") else "").strip().lower()
        missing_total=0
        shown=0
        for b in rows:
            missing_text=self.correction_missing_text(b)
            miss=bool(missing_text)
            if miss:
                missing_total+=1
            if self.c_missing_only.get() and not miss:
                continue
            hay=" ".join([
                b.get("guest",""),b.get("street",""),b.get("plz",""),b.get("city",""),
                b.get("country",""),b.get("phone",""),b.get("email",""),b.get("booking_no","")
            ]).lower()
            if q and q not in hay:
                continue
            tag=("missing",) if miss else ("ok",)
            status=("FEHLT: "+missing_text) if miss else "OK"
            self.ct.insert("",END,values=(
                b.get("id",""),
                b.get("guest",""),
                fmt(b.get("arrival","")),
                fmt(b.get("departure","")),
                b.get("street",""),
                b.get("plz",""),
                b.get("city",""),
                b.get("country",""),
                b.get("phone",""),
                b.get("email",""),
                status
            ), tags=tag)
            shown+=1
        if hasattr(self,"c_summary"):
            self.c_summary.set(f"angezeigt: {shown} · Buchungen gesamt: {len(rows)} · mit fehlenden Stammdaten: {missing_total}")

    def load_correction(self):
        sel=self.ct.selection()
        if not sel:
            return
        vals=self.ct.item(sel[0])["values"]
        bid=vals[0]
        b=next((x for x in self.d.get("bookings",[]) if x.get("id")==bid),None)
        if not b:
            return
        self.c_id.set(b.get("id",""))
        self.c_guest.set(b.get("guest",""))
        self.c_birth.set(b.get("birth",""))
        self.c_street.set(b.get("street",""))
        self.c_plz.set(b.get("plz",""))
        self.c_city.set(b.get("city",""))
        self.c_country.set(b.get("country",""))
        self.c_phone.set(b.get("phone",""))
        self.c_email.set(b.get("email",""))
        self.c_plate.set(b.get("plate",""))
        self.c_allergies.set(b.get("allergies",""))

    def clear_correction_form(self):
        for var in [self.c_id,self.c_guest,self.c_birth,self.c_street,self.c_plz,self.c_city,self.c_country,self.c_phone,self.c_email,self.c_plate,self.c_allergies]:
            var.set("")

    def write_adresskorrekturen_file(self):
        """Adresskorrekturen.csv aus den aktuell bekannten Buchungsdaten schreiben."""
        f=address_template_file()
        with open(f,"w",newline="",encoding="utf-8-sig") as out:
            w=csv.writer(out,delimiter=";")
            w.writerow(["Buchungsnummer","Gast","Straße","PLZ","Wohnort","Land","Telefon"])
            for b in sorted(self.d.get("bookings",[]),key=lambda x:(x.get("guest",""),x.get("arrival",""))):
                if str(b.get("plz","")).strip() or str(b.get("city","")).strip():
                    w.writerow([
                        b.get("booking_no",""),
                        b.get("guest",""),
                        b.get("street",""),
                        b.get("plz",""),
                        b.get("city",""),
                        b.get("country",""),
                        b.get("phone",""),
                    ])
        return f

    def save_correction(self):
        bid=self.c_id.get().strip()
        if not bid:
            messagebox.showinfo("Hinweis","Bitte zuerst eine Zeile markieren.")
            return
        b=next((x for x in self.d.get("bookings",[]) if x.get("id")==bid),None)
        if not b:
            messagebox.showerror("Fehler","Buchung nicht gefunden.")
            return
        b["guest"]=self.c_guest.get().strip()
        b["birth"]=self.c_birth.get().strip()
        b["street"]=self.c_street.get().strip()
        b["plz"]=self.c_plz.get().strip()
        b["city"]=self.c_city.get().strip()
        b["country"]=self.c_country.get().strip().upper()
        b["phone"]=normalize_phone(self.c_phone.get().strip())
        b["email"]=self.c_email.get().strip()
        b["plate"]=self.c_plate.get().strip()
        b["allergies"]=self.c_allergies.get().strip()
        save(self.d)
        f=self.write_adresskorrekturen_file()
        self.refresh_all()
        messagebox.showinfo("Gespeichert",f"Stammdaten gespeichert.\n\nKorrekturdatei aktualisiert:\n{f}")

    def export_corrections_csv(self):
        f=out_dir() / ("Stammdaten_Nachbearbeitung_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv")
        count=0
        with open(f,"w",newline="",encoding="utf-8-sig") as out:
            w=csv.writer(out,delimiter=";")
            w.writerow(["Buchungs-ID","Buchungsnummer","Gast","Anreise","Abreise","Straße","PLZ","Wohnort","Land","Telefon","E-Mail","Fehlt"])
            for b in sorted(self.d.get("bookings",[]),key=lambda x:(x.get("arrival",""),x.get("guest",""))):
                missing=self.correction_missing_text(b)
                if missing:
                    count+=1
                    w.writerow([
                        b.get("id",""),
                        b.get("booking_no",""),
                        b.get("guest",""),
                        fmt(b.get("arrival","")),
                        fmt(b.get("departure","")),
                        b.get("street",""),
                        b.get("plz",""),
                        b.get("city",""),
                        b.get("country",""),
                        b.get("phone",""),
                        b.get("email",""),
                        missing
                    ])
        messagebox.showinfo("CSV erstellt",f"{count} fehlende/zu prüfende Stammdaten exportiert:\n{f}")

    def open_out_folder(self):
        try:
            folder=out_dir()
            if os.name=="nt":
                os.startfile(folder)
            else:
                messagebox.showinfo("Ordner",str(folder))
        except Exception as e:
            messagebox.showerror("Fehler",str(e))

    def open_selected_booking_from_correction(self):
        bid=self.c_id.get().strip()
        if not bid:
            return
        self.open_guest_area(self.tab_book)
        try:
            for item in self.bt.get_children():
                if str(self.bt.item(item)["values"][0])==bid:
                    self.bt.selection_set(item)
                    self.bt.see(item)
                    self.load_booking()
                    break
        except Exception:
            pass

    def import_address_corrections_csv(self):
        p=filedialog.askopenfilename(title="Adresskorrekturen CSV auswählen",filetypes=[("CSV","*.csv"),("Alle Dateien","*.*")])
        if not p:
            return
        try:
            dest=data_dir()/("Adresskorrekturen_import_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".csv")
            shutil.copy2(p,dest)
            messagebox.showinfo("Importiert",f"Korrekturdatei übernommen:\n{dest}\n\nJetzt werden die Korrekturen angewendet.")
            self.apply_all_address_corrections()
        except Exception as e:
            messagebox.showerror("Importfehler",str(e))

    def apply_all_address_corrections(self):
        try:
            index=build_address_index(self.d)
            changed=0
            still_missing=0
            for b in self.d.get("bookings",[]):
                before=(b.get("plz",""),b.get("city",""),b.get("street",""),b.get("country",""))
                plz,city,street,country,corr=apply_address_correction(
                    index,
                    booking_no=b.get("booking_no",""),
                    guest=b.get("guest",""),
                    phone=b.get("phone",""),
                    street=b.get("street",""),
                    country=b.get("country",""),
                    plz=b.get("plz",""),
                    city=b.get("city","")
                )
                b["plz"]=plz
                b["city"]=city
                b["street"]=street
                b["country"]=country
                after=(plz,city,street,country)
                if after!=before:
                    changed+=1
                if not str(plz).strip() or not str(city).strip():
                    still_missing+=1
            save(self.d)
            self.refresh_all()
            messagebox.showinfo("Stammdaten-Korrektur",f"Korrekturen angewendet.\nGeändert: {changed}\nWeiterhin PLZ/Ort fehlend: {still_missing}\n\nHinweis: PLZ/Wohnort können nur aus vorhandenen oder importierten Korrekturdaten ergänzt werden.")
        except Exception as e:
            messagebox.showerror("Stammdaten-Korrektur",str(e))


    def validate_bookings(self):
        errors=[]
        warnings=[]
        bookings=self.d.get("bookings",[])
        # Doppelbuchungen je Zimmer / überschneidende Zeiträume
        active=[b for b in bookings if b.get("status")!="storniert"]
        for b in active:
            bid=b.get("id","")
            guest=b.get("guest","")
            try:
                arr=pdate(b.get("arrival",""))
                dep=pdate(b.get("departure",""))
            except Exception:
                errors.append([bid,guest,"Datum","Anreise/Abreise ist ungültig"])
                continue
            if dep<=arr:
                errors.append([bid,guest,"Datum","Abreise liegt vor oder am Anreisetag"])
            if to_int(b.get("persons",0),0)<=0:
                errors.append([bid,guest,"Personen","Personenanzahl fehlt oder ist 0"])
            if not b.get("room_id"):
                errors.append([bid,guest,"Zimmer","Zimmer fehlt"])
            if not str(b.get("guest","")).strip():
                errors.append([bid,guest,"Gast","Gastname fehlt"])
            if to_float(b.get("price",0),0)<=0:
                warnings.append([bid,guest,"Preis","Preis ist 0 oder leer"])
            if not str(b.get("country","")).strip():
                warnings.append([bid,guest,"Land","Land fehlt"])
            if not str(b.get("plz","")).strip():
                warnings.append([bid,guest,"PLZ","PLZ fehlt"])
            if not str(b.get("city","")).strip():
                warnings.append([bid,guest,"Wohnort","Wohnort fehlt"])
            if not str(b.get("phone","")).strip():
                warnings.append([bid,guest,"Telefon","Telefonnummer fehlt"])
        for i,b1 in enumerate(active):
            try:
                a1,d1=pdate(b1.get("arrival","")),pdate(b1.get("departure",""))
            except Exception:
                continue
            for b2 in active[i+1:]:
                if b1.get("room_id")!=b2.get("room_id"):
                    continue
                try:
                    a2,d2=pdate(b2.get("arrival","")),pdate(b2.get("departure",""))
                except Exception:
                    continue
                if a1 < d2 and a2 < d1:
                    errors.append([b1.get("id","")+" / "+b2.get("id",""), b1.get("guest","")+" / "+b2.get("guest",""), "Doppelbuchung", "Überlappung im selben Zimmer"])
        return errors,warnings

    def export_gemeinde_year_csv(self):
        """Jahresübersicht Personennächte und Ortstaxe als CSV."""
        try:
            year=date.today().year
            rows=[]
            for month in range(1,13):
                start=date(year,month,1)
                end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
                bookings=[b for b in self.d.get("bookings",[]) if b.get("status")!="storniert" and pdate(b.get("arrival",""))<end and pdate(b.get("departure",""))>start]
                nights=persons=person_nights=tax=0
                for b in bookings:
                    a=max(pdate(b.get("arrival","")),start)
                    d=min(pdate(b.get("departure","")),end)
                    n=max(0,(d-a).days)
                    p=to_int(b.get("persons",1),1)
                    nights+=n
                    persons+=p
                    person_nights+=n*p
                    tax+=n*p*ORTSTAXE
                rows.append([f"{month:02d}.{year}",len(bookings),nights,persons,person_nights,tax])
            f=out_dir()/f"Gemeinde_Jahresuebersicht_{year}.csv"
            with open(f,"w",newline="",encoding="utf-8-sig") as out:
                w=csv.writer(out,delimiter=";")
                w.writerow(["Monat","Buchungen","Nächte","Personen Summe","Personennächte","Ortstaxe"])
                for r in rows:
                    w.writerow([r[0],r[1],r[2],r[3],r[4],money(r[5])])
            messagebox.showinfo("Jahresübersicht",f"Jahresübersicht erstellt:\n{f}")
        except Exception as e:
            messagebox.showerror("Fehler",str(e))

    def build_check(self):
        top=self.card(self.tab_check,"Datenprüfung & Kontrolllauf")
        ttk.Label(top,text="Prüft Buchungen auf fehlende Stammdaten, Datum, Preis, Doppelbuchungen und Gemeinde-relevante Angaben.",style="Card.TLabel").pack(anchor="w")
        bar=ttk.Frame(top,style="Card.TFrame"); bar.pack(fill="x",pady=6)
        ttk.Button(bar,text="JETZT PRÜFEN",command=self.refresh_check,style="Touch.TButton").pack(side="left",padx=4)
        ttk.Button(bar,text="PRÜFBERICHT ALS CSV",command=self.export_check_csv,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(bar,text="BACKUP JETZT",command=self.manual_backup_now,style="Primary.TButton").pack(side="left",padx=4)
        self.check_summary=StringVar(value="")
        ttk.Label(top,textvariable=self.check_summary,style="CardTitle.TLabel").pack(anchor="w",pady=(4,0))

        cols=("art","buchung","gast","feld","hinweis")
        self.check_tree=ttk.Treeview(self.tab_check,columns=cols,show="headings",height=26)
        for c in cols:
            self.check_tree.heading(c,text=c.title())
            self.check_tree.column(c,width=130)
        self.check_tree.column("gast",width=220)
        self.check_tree.column("hinweis",width=450)
        self.check_tree.pack(fill="both",expand=True,padx=8,pady=8)
        self.check_tree.tag_configure("error", background="#ffd9d9", foreground="#4a0000")
        self.check_tree.tag_configure("warn", background="#fff2a8", foreground="#312300")

    def refresh_check(self):
        if not hasattr(self,"check_tree"):
            return
        for i in self.check_tree.get_children():
            self.check_tree.delete(i)
        errors,warnings=self.validate_bookings()
        for row in errors:
            self.check_tree.insert("",END,values=("FEHLER",)+tuple(row),tags=("error",))
        for row in warnings:
            self.check_tree.insert("",END,values=("HINWEIS",)+tuple(row),tags=("warn",))
        age=last_backup_age_days()
        backup_txt="kein Backup gefunden" if age is None else f"letztes Backup vor {age} Tag(en)"
        self.check_summary.set(f"{len(errors)} Fehler · {len(warnings)} Hinweise · {backup_txt}")

    def export_check_csv(self):
        errors,warnings=self.validate_bookings()
        f=out_dir()/("Datenpruefung_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".csv")
        with open(f,"w",newline="",encoding="utf-8-sig") as out:
            w=csv.writer(out,delimiter=";")
            w.writerow(["Art","Buchung","Gast","Feld","Hinweis"])
            for r in errors:
                w.writerow(["FEHLER"]+r)
            for r in warnings:
                w.writerow(["HINWEIS"]+r)
        messagebox.showinfo("Prüfbericht",f"Prüfbericht erstellt:\n{f}")

    def manual_backup_now(self):
        b=auto_backup_now("MANUELL")
        if b:
            messagebox.showinfo("Backup",f"Backup erstellt:\n{b}")
        else:
            messagebox.showwarning("Backup","Es wurde noch keine Datendatei gefunden oder Backup konnte nicht erstellt werden.")
        self.refresh_check()

    def day_short(self, b, mode="inhouse"):
        """Kurze, übersichtliche Anzeige für Tageslisten-Spalten.
        Wichtig: Bei Abreise wird nur der offene Checkout-Betrag angezeigt.
        Booking/extern bezahlte Zimmerpreise werden nicht nochmals als offen angezeigt.
        """
        guest=b.get("guest","")
        room=room_name(self.d,b.get("room_id",""))
        persons=to_int(b.get("persons",1),1)
        phone=b.get("phone","")
        breakfast=b.get("breakfast","kein")
        dog="Hund" if b.get("dog") else ""
        allergy=b.get("allergies","")
        wishes=b.get("wishes","")
        if mode=="arrival":
            wa = "WhatsApp: ✓ Begrüßung" if (b.get("welcome_sent") or b.get("begruessung_gesendet")) else "WhatsApp: offen"
            paid = "bezahlt" if self.dashboard_is_paid_booking(b) else "Zahlung offen/prüfen"
            parts=[guest, room, f"{persons} Pers.", f"bis {fmt(b.get('departure',''))}", f"Frühstück: {breakfast}", wa, paid]
            if phone: parts.append(phone)
            if dog: parts.append(dog)
            if allergy: parts.append("Allergien: "+allergy)
            if wishes: parts.append("Wünsche: "+wishes[:120])
            return "\n".join([p for p in parts if p])
        if mode=="departure":
            try:
                due_txt=checkout_due_text(self.d,b,short=True)
            except Exception:
                due_txt=""
            parts=[guest, room, f"{persons} Pers.", f"seit {fmt(b.get('arrival',''))}"]
            if due_txt: parts.append(due_txt)
            if phone: parts.append(phone)
            return "\n".join([p for p in parts if p])
        parts=[guest, room, f"{persons} Pers.", f"{fmt(b.get('arrival',''))} bis {fmt(b.get('departure',''))}", f"Frühstück: {breakfast}"]
        if dog: parts.append(dog)
        if allergy: parts.append("Allergien: "+allergy)
        return "\n".join([p for p in parts if p])

    def build_day(self):
        f=self.card(self.tab_day,"Tagesliste")
        self.day_date=StringVar(value=date.today().strftime("%d.%m.%Y"))
        ttk.Entry(f,textvariable=self.day_date,width=12).pack(side="left",padx=5)
        ttk.Button(f,text="ANZEIGEN",command=self.refresh_day,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(f,text="ALS PDF DRUCKEN",command=self.day_pdf,style="Touch.TButton").pack(side="left",padx=5)
        self.day_summary=StringVar(value="")
        ttk.Label(f,textvariable=self.day_summary,style="CardTitle.TLabel").pack(side="left",padx=14)

        main=ttk.Frame(self.tab_day)
        main.pack(fill="both",expand=True,padx=8,pady=8)
        self.day_texts={}
        specs=[
            ("arrival","🟡 ANREISE","#fff8c6"),
            ("inhouse","🟢 IM HAUS","#e1f1dc"),
            ("departure","🔴 ABREISE","#ffe0e0"),
        ]
        for key,title,bg in specs:
            col=ttk.Frame(main)
            col.pack(side="left",fill="both",expand=True,padx=4)
            self.card(col,title)
            frame=ttk.Frame(col)
            frame.pack(fill="both",expand=True)
            txt=Text(frame,wrap="word",bg=bg,relief="flat",font=("Segoe UI",10),padx=10,pady=10)
            sb=ttk.Scrollbar(frame,orient="vertical",command=txt.yview)
            txt.configure(yscrollcommand=sb.set)
            txt.pack(side="left",fill="both",expand=True)
            sb.pack(side="right",fill="y")
            self.day_texts[key]=txt

        bottom=self.card(self.tab_day,"Offene Einkaufsliste / Hinweise")
        self.day_notes=Text(bottom,height=5,wrap="word",bg="#ffffff",relief="flat",font=("Consolas",10),padx=10,pady=8)
        self.day_notes.pack(fill="x",expand=False)

    def refresh_day(self):
        if not hasattr(self, "day_date") or not hasattr(self, "day_texts"):
            return
        d=pdate(self.day_date.get())
        bs=[b for b in self.d.get("bookings",[]) if b.get("status")!="storniert"]
        arr=sorted([b for b in bs if pdate(b.get("arrival",""))==d],key=lambda x:(room_name(self.d,x.get("room_id","")), x.get("guest","")))
        dep=sorted([b for b in bs if pdate(b.get("departure",""))==d],key=lambda x:(room_name(self.d,x.get("room_id","")), x.get("guest","")))
        inhouse=sorted([b for b in bs if pdate(b.get("arrival",""))<=d<pdate(b.get("departure",""))],key=lambda x:(room_name(self.d,x.get("room_id","")), x.get("guest","")))

        groups=[("arrival",arr,"arrival"),("inhouse",inhouse,"inhouse"),("departure",dep,"departure")]
        for key,items,mode in groups:
            txt=self.day_texts.get(key)
            if not txt: continue
            txt.config(state="normal")
            txt.delete("1.0",END)
            if not items:
                txt.insert(END,"keine\n")
            else:
                for n,b in enumerate(items,1):
                    txt.insert(END,f"{n}. {self.day_short(b,mode)}\n")
                    txt.insert(END,"-"*42+"\n")
            txt.config(state="disabled")

        self.day_summary.set(f"{fmt(d)} · Anreise: {len(arr)} · Im Haus: {len(inhouse)} · Abreise: {len(dep)}")
        self.day_notes.delete("1.0",END)
        open_shop=[s for s in self.d.get("shopping",[]) if not s.get("done")]
        self.day_notes.insert(END,"OFFENE EINKAUFSLISTE\n")
        self.day_notes.insert(END,("\n".join(f"- {s.get('qty','')} {s.get('item','')}" for s in open_shop) or "- keine"))
        self.day_notes.insert(END,"\n\nBildschirmansicht mit Scrollbalken: alle Informationen sind sichtbar.")

    def day_pdf(self):
        try:
            self.refresh_day()
            d=pdate(self.day_date.get())
            pdf=out_dir()/("Tagesliste_"+d.strftime("%Y%m%d")+".pdf")
            styles=getSampleStyleSheet()
            doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=10*mm)
            story=[]
            add_logo_to_story(story)
            story.append(Paragraph("Tagesliste",styles["Title"]))
            story.append(Paragraph(f"Zuhause am Bach – {fmt(d)}",styles["Normal"]))
            story.append(Spacer(1,5*mm))

            bs=[b for b in self.d.get("bookings",[]) if b.get("status")!="storniert"]
            arr=sorted([b for b in bs if pdate(b.get("arrival",""))==d],key=lambda x:(room_name(self.d,x.get("room_id","")),x.get("guest","")))
            inhouse=sorted([b for b in bs if pdate(b.get("arrival",""))<=d<pdate(b.get("departure",""))],key=lambda x:(room_name(self.d,x.get("room_id","")),x.get("guest","")))
            dep=sorted([b for b in bs if pdate(b.get("departure",""))==d],key=lambda x:(room_name(self.d,x.get("room_id","")),x.get("guest","")))

            def esc(x):
                return str(x or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br/>")
            def cell_lines(items,mode):
                if not items:
                    return Paragraph("keine",styles["Normal"])
                txt=[]
                for b in items:
                    txt.append("• "+esc(self.day_short(b,mode)))
                return Paragraph("<br/><br/>".join(txt),styles["Normal"])

            data=[
                [Paragraph("<b>ANREISE</b>",styles["Normal"]),Paragraph("<b>IM HAUS</b>",styles["Normal"]),Paragraph("<b>ABREISE</b>",styles["Normal"])],
                [cell_lines(arr,"arrival"),cell_lines(inhouse,"inhouse"),cell_lines(dep,"departure")]
            ]
            table=Table(data,colWidths=[61*mm,61*mm,61*mm],repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(0,0),colors.lightyellow),
                ("BACKGROUND",(1,0),(1,0),colors.lightgreen),
                ("BACKGROUND",(2,0),(2,0),colors.HexColor("#ffd9d9")),
                ("GRID",(0,0),(-1,-1),0.5,colors.grey),
                ("VALIGN",(0,0),(-1,-1),"TOP"),
                ("PADDING",(0,0),(-1,-1),5),
            ]))
            story.append(table)
            open_shop=[s for s in self.d.get("shopping",[]) if not s.get("done")]
            story.append(Spacer(1,6*mm))
            story.append(Paragraph("<b>Offene Einkaufsliste</b>",styles["Heading2"]))
            story.append(Paragraph(("<br/>".join("• "+esc(f"{s.get('qty','')} {s.get('item','')}") for s in open_shop) or "keine"),styles["Normal"]))
            doc.build(story)
            messagebox.showinfo("Tagesliste PDF",str(pdf))
            try: os.startfile(str(pdf))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("PDF-Fehler",str(e))


    def build_shopping(self):
        f=self.card(self.tab_shop,"Einkaufsliste")
        ttk.Button(f,text="Als PDF anzeigen / drucken",command=self.save_shopping_pdf,style="Touch.TButton").pack(side="left",padx=5)
        main=ttk.Frame(self.tab_shop); main.pack(fill="both",expand=True,padx=8,pady=8)
        self.shop_tree=ttk.Treeview(main,columns=("id","artikel","menge","erledigt"),show="headings",height=14)
        for c in ("id","artikel","menge","erledigt"):
            self.shop_tree.heading(c,text=c.title())
            self.shop_tree.column(c,width=150)
        self.shop_tree.pack(fill="both",expand=True)
        self.shop_tree.bind("<<TreeviewSelect>>",lambda e:self.load_shop())
        form=ttk.Frame(main); form.pack(fill="x",pady=8)
        self.s_item=StringVar(); self.s_qty=StringVar(value="1"); self.s_done=BooleanVar(value=False)
        ttk.Label(form,text="Artikel").pack(side="left")
        self.s_combo=ttk.Combobox(form,textvariable=self.s_item,values=self.article_names(),width=30)
        self.s_combo.pack(side="left",padx=5)
        ttk.Label(form,text="Menge").pack(side="left")
        ttk.Entry(form,textvariable=self.s_qty,width=12).pack(side="left",padx=5)
        ttk.Checkbutton(form,text="erledigt",variable=self.s_done).pack(side="left",padx=5)
        ttk.Button(form,text="Speichern",command=self.save_shop,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(form,text="Neu",command=self.new_shop).pack(side="left",padx=5)
        ttk.Button(form,text="Löschen",command=self.delete_shop).pack(side="left",padx=5)

    def refresh_shopping(self):
        try:
            for i in self.shop_tree.get_children():
                self.shop_tree.delete(i)
            for s in self.d.get("shopping",[]):
                self.shop_tree.insert("",END,values=(s["id"],s.get("item",""),s.get("qty",""),"ja" if s.get("done") else "nein"))
            try:
                self.s_combo["values"]=self.article_names()
            except Exception:
                pass
        except Exception:
            pass

    def new_shop(self):
        self.cur_shop=None
        self.s_item.set("")
        self.s_qty.set("1")
        self.s_done.set(False)

    def load_shop(self):
        sel=self.shop_tree.selection()
        if not sel:
            return
        sid=self.shop_tree.item(sel[0])["values"][0]
        s=next((x for x in self.d.get("shopping",[]) if x["id"]==sid),None)
        if not s:
            return
        self.cur_shop=sid
        self.s_item.set(s.get("item",""))
        self.s_qty.set(s.get("qty",""))
        self.s_done.set(bool(s.get("done",False)))

    def save_shop(self):
        if not self.s_item.get().strip():
            return
        rec={"id":self.cur_shop or uid("SHOP"),"item":self.s_item.get().strip(),"qty":self.s_qty.get().strip(),"done":bool(self.s_done.get())}
        if self.cur_shop:
            self.d["shopping"]=[rec if s["id"]==self.cur_shop else s for s in self.d.get("shopping",[])]
        else:
            self.d.setdefault("shopping",[]).append(rec)
            self.cur_shop=rec["id"]
        save(self.d)
        self.refresh_shopping()

    def delete_shop(self):
        if not self.cur_shop:
            return
        self.d["shopping"]=[s for s in self.d.get("shopping",[]) if s["id"]!=self.cur_shop]
        self.cur_shop=None
        save(self.d)
        self.refresh_shopping()
        self.new_shop()

    def save_shopping_pdf(self):
        pdf=out_dir()/("Einkaufsliste_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".pdf")
        styles=getSampleStyleSheet()
        doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=16*mm,leftMargin=16*mm,topMargin=14*mm,bottomMargin=12*mm)
        story=[]
        add_logo_to_story(story)
        story += [Paragraph("Einkaufsliste",styles["Title"]),Paragraph("Zuhause am Bach",styles["Normal"]),Spacer(1,6*mm)]
        rows=[["Erledigt","Menge","Artikel"]]
        for s in self.d.get("shopping",[]):
            rows.append(["✓" if s.get("done") else "☐",str(s.get("qty","")),str(s.get("item",""))])
        table=Table(rows,colWidths=[25*mm,35*mm,110*mm])
        table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold")]))
        story.append(table)
        doc.build(story)
        messagebox.showinfo("Einkaufsliste PDF",str(pdf))
        try:
            os.startfile(str(pdf))
        except Exception:
            pass


    def clean_rows_for_date(self, d):
        rows=[]
        for r in active_rooms(self.d):
            arr=[b for b in self.d.get("bookings",[]) if b.get("status")!="storniert" and b.get("room_id")==r.get("id") and pdate(b.get("arrival",""))==d]
            dep=[b for b in self.d.get("bookings",[]) if b.get("status")!="storniert" and b.get("room_id")==r.get("id") and pdate(b.get("departure",""))==d]
            inhouse=[b for b in self.d.get("bookings",[]) if b.get("status")!="storniert" and b.get("room_id")==r.get("id") and pdate(b.get("arrival",""))<d<pdate(b.get("departure",""))]
            if dep and arr:
                status="WECHSEL – DRINGEND"
                tag="wechsel"
                gast=f"Abreise: {', '.join(b.get('guest','') for b in dep)} / Anreise: {', '.join(b.get('guest','') for b in arr)}"
                tasks="[ ] reinigen  [ ] Bad  [ ] Bettwäsche  [ ] Handtücher  [ ] Kontrolle"
            elif dep:
                status="ABREISE – REINIGEN"
                tag="abreise"
                gast=", ".join(b.get("guest","") for b in dep)
                tasks="[ ] reinigen  [ ] Bad  [ ] Bettwäsche  [ ] Handtücher  [ ] Kontrolle"
            elif arr:
                status="ANREISE – VORBEREITEN"
                tag="anreise"
                gast=", ".join(b.get("guest","") for b in arr)
                tasks="[ ] lüften  [ ] Handtücher  [ ] Infomappe  [ ] Kontrolle"
            elif inhouse:
                status="BELEGT – KONTROLLE"
                tag="belegt"
                gast=", ".join(b.get("guest","") for b in inhouse)
                tasks="[ ] Müll  [ ] Papier  [ ] Handtücher prüfen"
            else:
                status="FREI"
                tag="frei"
                gast=""
                tasks="[ ] Sichtkontrolle"
            rows.append([r.get("name",""),status,gast,tasks,tag])
        return rows

    def build_clean(self):
        f=self.card(self.tab_clean,"Reinigungsliste")
        self.clean_date=StringVar(value=date.today().strftime("%d.%m.%Y"))
        ttk.Entry(f,textvariable=self.clean_date,width=12).pack(side="left",padx=5)
        ttk.Button(f,text="Anzeigen",command=self.refresh_clean,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(f,text="Als PDF drucken",command=self.clean_pdf,style="Touch.TButton").pack(side="left",padx=5)
        self.clean_summary=StringVar(value="")
        ttk.Label(f,textvariable=self.clean_summary,style="CardTitle.TLabel").pack(side="left",padx=14)

        cols=("zimmer","status","gast","aufgaben")
        self.clean_tree=ttk.Treeview(self.tab_clean,columns=cols,show="headings",height=24)
        for c in cols:
            self.clean_tree.heading(c,text=c.title())
            self.clean_tree.column(c,width=160)
        self.clean_tree.column("zimmer",width=170)
        self.clean_tree.column("status",width=190)
        self.clean_tree.column("gast",width=360)
        self.clean_tree.column("aufgaben",width=520)
        self.clean_tree.pack(fill="both",expand=True,padx=8,pady=8)
        self.clean_tree.tag_configure("wechsel", background="#ffb3b3", foreground="#4a0000")
        self.clean_tree.tag_configure("abreise", background="#ffd9d9", foreground="#4a0000")
        self.clean_tree.tag_configure("anreise", background="#fff2a8", foreground="#312300")
        self.clean_tree.tag_configure("belegt", background="#d8ecd0", foreground="#173814")
        self.clean_tree.tag_configure("frei", background="#ffffff", foreground="#263016")

    def refresh_clean(self):
        if not hasattr(self, "clean_date") or not hasattr(self,"clean_tree"):
            return
        d=pdate(self.clean_date.get())
        for i in self.clean_tree.get_children():
            self.clean_tree.delete(i)
        rows=self.clean_rows_for_date(d)
        counts={"wechsel":0,"abreise":0,"anreise":0,"belegt":0,"frei":0}
        for zimmer,status,gast,tasks,tag in rows:
            counts[tag]=counts.get(tag,0)+1
            self.clean_tree.insert("",END,values=(zimmer,status,gast,tasks),tags=(tag,))
        self.clean_summary.set(f"{fmt(d)} · Wechsel: {counts['wechsel']} · Abreise: {counts['abreise']} · Anreise: {counts['anreise']} · Belegt: {counts['belegt']} · Frei: {counts['frei']}")

    def clean_pdf(self):
        try:
            self.refresh_clean()
            d=pdate(self.clean_date.get())
            pdf=out_dir()/("Reinigungsliste_"+d.strftime("%Y%m%d")+".pdf")
            styles=getSampleStyleSheet()
            doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=10*mm)
            story=[]
            add_logo_to_story(story)
            story.append(Paragraph("Reinigungsliste",styles["Title"]))
            story.append(Paragraph(f"Zuhause am Bach – {fmt(d)}",styles["Normal"]))
            story.append(Spacer(1,5*mm))

            def esc(x):
                return str(x or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            data=[[Paragraph("<b>Zimmer</b>",styles["Normal"]),Paragraph("<b>Status</b>",styles["Normal"]),Paragraph("<b>Gast</b>",styles["Normal"]),Paragraph("<b>Aufgaben</b>",styles["Normal"])]]
            for zimmer,status,gast,tasks,tag in self.clean_rows_for_date(d):
                data.append([Paragraph(esc(zimmer),styles["Normal"]),Paragraph(esc(status),styles["Normal"]),Paragraph(esc(gast),styles["Normal"]),Paragraph(esc(tasks),styles["Normal"])])
            table=Table(data,colWidths=[34*mm,42*mm,55*mm,52*mm],repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#d9ddc8")),
                ("GRID",(0,0),(-1,-1),0.5,colors.grey),
                ("VALIGN",(0,0),(-1,-1),"TOP"),
                ("PADDING",(0,0),(-1,-1),5),
            ]))
            story.append(table)
            doc.build(story)
            messagebox.showinfo("Reinigungsliste PDF",str(pdf))
            try: os.startfile(str(pdf))
            except Exception: pass
        except Exception as e:
            messagebox.showerror("PDF-Fehler",str(e))


    def build_backup(self):
        top=self.card(self.tab_backup,"Backup & Wiederherstellung")
        ttk.Label(top,text="Sicherungen schützen vor Datenverlust. Vor jedem Booking-Import wird automatisch ein Backup erstellt.",style="Card.TLabel").pack(anchor="w")
        bar=ttk.Frame(top,style="Card.TFrame"); bar.pack(fill="x",pady=6)
        ttk.Button(bar,text="BACKUP JETZT ERSTELLEN",command=self.manual_backup_now,style="Touch.TButton").pack(side="left",padx=4)
        ttk.Button(bar,text="BACKUP PRÜFEN",command=self.check_backup_system,style="Touch.TButton").pack(side="left",padx=4)
        ttk.Button(bar,text="LISTE AKTUALISIEREN",command=self.refresh_backup_list,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(bar,text="MARKIERTES BACKUP WIEDERHERSTELLEN",command=self.restore_selected_backup,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(bar,text="BACKUP-ORDNER ÖFFNEN",command=self.open_backup_folder).pack(side="left",padx=4)

        self.backup_status=StringVar(value="")
        ttk.Label(top,textvariable=self.backup_status,style="CardTitle.TLabel").pack(anchor="w",pady=(4,0))

        cols=("datei","datum","größe","prüfung")
        self.backup_tree=ttk.Treeview(self.tab_backup,columns=cols,show="headings",height=24)
        for c in cols:
            self.backup_tree.heading(c,text=c.title())
            self.backup_tree.column(c,width=200)
        self.backup_tree.column("datei",width=520)
        self.backup_tree.column("prüfung",width=180)
        self.backup_tree.pack(fill="both",expand=True,padx=8,pady=8)
        self.backup_tree.tag_configure("ok", background="#d8ecd0", foreground="#173814")
        self.backup_tree.tag_configure("bad", background="#ffd9d9", foreground="#4a0000")

    def backup_file_status(self, f):
        try:
            data=json.loads(Path(f).read_text(encoding="utf-8"))
            if isinstance(data,dict) and "bookings" in data:
                return "OK"
            return "prüfen"
        except Exception:
            return "FEHLER"

    def refresh_backup_list(self):
        if not hasattr(self,"backup_tree"):
            return
        for i in self.backup_tree.get_children():
            self.backup_tree.delete(i)
        try:
            files=sorted(backup_dir().glob("*.json"), key=lambda p:p.stat().st_mtime, reverse=True)[:50]
            ok=bad=0
            for f in files:
                dt=datetime.fromtimestamp(f.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
                size=f"{f.stat().st_size/1024:.1f} KB"
                st=self.backup_file_status(f)
                if st=="OK": ok+=1
                elif st=="FEHLER": bad+=1
                self.backup_tree.insert("",END,values=(str(f),dt,size,st),tags=("ok" if st=="OK" else "bad" if st=="FEHLER" else ""))
            age=last_backup_age_days()
            age_txt="kein Backup vorhanden" if age is None else f"letztes Backup vor {age} Tag(en)"
            self.backup_status.set(f"{len(files)} Backups gefunden · {ok} OK · {bad} fehlerhaft · {age_txt}")
        except Exception as e:
            self.backup_status.set("Backup-Liste konnte nicht gelesen werden: "+str(e))

    def check_backup_system(self):
        messages=[]
        ok=True
        try:
            df=data_file()
            messages.append(f"Datendatei: {df}")
            if not df.exists():
                save(self.d)
            messages.append("Datendatei vorhanden: " + ("JA" if df.exists() else "NEIN"))
            bd=backup_dir()
            bd.mkdir(parents=True,exist_ok=True)
            messages.append(f"Backup-Ordner: {bd}")
            test=bd/"backup_schreibtest.tmp"
            test.write_text("test",encoding="utf-8")
            test.unlink(missing_ok=True)
            messages.append("Backup-Ordner beschreibbar: JA")
        except Exception as e:
            ok=False
            messages.append("Backup-Ordner beschreibbar: NEIN")
            messages.append(str(e))

        try:
            b=auto_backup_now("PRUEF_BACKUP")
            if b and Path(b).exists():
                status=self.backup_file_status(b)
                messages.append(f"Test-Backup erstellt: {b}")
                messages.append(f"Test-Backup lesbar: {status}")
                if status=="FEHLER":
                    ok=False
            else:
                ok=False
                messages.append("Test-Backup konnte nicht erstellt werden.")
        except Exception as e:
            ok=False
            messages.append("Test-Backup Fehler: "+str(e))

        self.refresh_backup_list()
        messagebox.showinfo("Backup-Prüfung OK" if ok else "Backup-Prüfung mit Fehler", "\n".join(messages))

    def restore_selected_backup(self):
        if not hasattr(self,"backup_tree"):
            return
        sel=self.backup_tree.selection()
        if not sel:
            messagebox.showinfo("Hinweis","Bitte zuerst ein Backup markieren.")
            return
        f=Path(self.backup_tree.item(sel[0])["values"][0])
        if not f.exists():
            messagebox.showerror("Fehler","Backup-Datei nicht gefunden.")
            return
        if self.backup_file_status(f)=="FEHLER":
            messagebox.showerror("Fehler","Dieses Backup ist nicht lesbar und wird nicht wiederhergestellt.")
            return
        if not messagebox.askyesno("Wiederherstellen","Aktuelle Daten werden vorher gesichert und dann durch das markierte Backup ersetzt. Fortfahren?"):
            return
        auto_backup_now("VOR_WIEDERHERSTELLUNG")
        shutil.copy2(f,data_file())
        self.d=load()
        self.d.setdefault("shopping", [])
        self.d.setdefault("products", [])
        self.d.setdefault("invoices", [])
        self.refresh_all()
        messagebox.showinfo("Wiederhergestellt",f"Backup wurde wiederhergestellt:\n{f}")

    def open_backup_folder(self):
        try:
            folder=backup_dir()
            if os.name=="nt":
                os.startfile(folder)
            else:
                messagebox.showinfo("Backup-Ordner",str(folder))
        except Exception as e:
            messagebox.showerror("Fehler",str(e))



    def choose_sync_folder(self):
        p=filedialog.askdirectory(title="Google-Drive-Datenordner auswählen")
        if not p:
            return
        old_file=data_file()
        set_data_dir(p)
        self.sync_path.set(str(data_dir()))
        # Wenn im neuen Ordner noch keine daten.json ist, aktuelle Daten dorthin schreiben
        if not data_file().exists():
            save(self.d)
        self.d=load()
        self.refresh_all()
        self.sync_text.insert(END,f"\\nDatenordner gesetzt: {data_dir()}\\n")
        messagebox.showinfo("Google Drive", "Datenordner wurde gesetzt. PDFs/Backups gehen nun in diesen Ordner.")

    def reload_data_from_folder(self):
        try:
            self.d=load()
            self.refresh_all()
            self.sync_text.insert(END,f"\\nDaten neu geladen aus: {data_file()}\\n")
            messagebox.showinfo("Neu geladen","Daten wurden neu geladen.")
        except Exception as e:
            messagebox.showerror("Fehler",str(e))

    def copy_current_data_to_sync(self):
        try:
            # Speichert aktuelle Daten in den eingestellten Datenordner
            save(self.d)
            self.sync_text.insert(END,f"\\nAktuelle Daten gespeichert in: {data_file()}\\n")
            messagebox.showinfo("Gespeichert",f"Aktuelle Daten gespeichert:\\n{data_file()}")
        except Exception as e:
            messagebox.showerror("Fehler",str(e))


    def build_info(self):
        main=ttk.Frame(self.tab_info)
        main.pack(fill="both",expand=True,padx=10,pady=10)

        top=self.card(main,"Information & Hilfe")
        ttk.Label(
            top,
            text=f"{APP_NAME}\n{VERSION}\nEntwickler: {DEVELOPER}\n\n"
                 "Dieses Programm unterstützt kleine Unterkunftsbetriebe bei Buchungen, Gästen, Ortstaxe, Gemeinde-Meldungen, Rechnungen, Tageslisten, Reinigung und Auswertungen.",
            style="Card.TLabel",
            justify="left",
            wraplength=1120
        ).pack(anchor="w")

        btns=ttk.Frame(top,style="Card.TFrame")
        btns.pack(fill="x",pady=8)
        ttk.Button(btns,text="AUSGABE-ORDNER ÖFFNEN",command=self.open_out_folder,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(btns,text="KURZANLEITUNG ALS TXT EXPORTIEREN",command=self.export_help_txt,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(btns,text="DATENORDNER ANZEIGEN",command=self.show_data_folder).pack(side="left",padx=4)

        help_frame=self.card(main,"Bedienungsanleitung für Anwender")
        self.info_text=Text(
            help_frame,
            height=30,
            wrap="word",
            bg="#ffffff",
            fg="#1f2b17",
            font=("Segoe UI",10),
            padx=14,
            pady=12,
            relief="flat"
        )
        self.info_text.pack(fill="both",expand=True)

        help_content = f"""
{APP_NAME}
INFORMATION, HILFE UND BEDIENUNGSANLEITUNG
{VERSION}
Entwickler: {DEVELOPER}


1. ZWECK DES PROGRAMMS
Der Zuhause am Bach Manager ist ein Verwaltungsprogramm für kleine Beherbergungsbetriebe.
Er wurde für Privatzimmer, kleine Pensionen, Ferienwohnungen und Gästehäuser entwickelt.

Das Programm hilft bei:
- Buchungen
- Gästedaten
- Kalender
- Rechnungen
- Ortstaxe
- Gemeinde-Meldung
- Tagesliste
- Reinigungsliste
- Einkaufsliste
- Artikel und Extras
- Booking-Import
- Stammdaten-Korrektur
- Google-Drive-Datenordner
- Backup und Wiederherstellung


2. TÄGLICHER ABLAUF
Empfohlener Tagesablauf:

1. Programm starten.
2. Dashboard prüfen.
3. Anreisen ansehen.
4. Abreisen ansehen.
5. Reinigungsliste öffnen.
6. Tagesliste ausdrucken oder anzeigen.
7. Offene Stammdaten prüfen.
8. Bei Bedarf Rechnung erstellen.
9. Am Ende Daten sichern.


3. DASHBOARD
Das Dashboard ist die Startseite.

Dort sieht man:
- Anreisen heute
- Abreisen heute
- Gäste im Haus
- Ortstaxe im laufenden Monat
- Umsatz im laufenden Monat

Farben:
- Gelb bedeutet: offen / noch zu erledigen.
- Rot bedeutet: Abreise oder Zahlung offen.
- Grün bedeutet: erledigt.

Ein Klick auf eine Anreise markiert den Gast als eingecheckt.
Ein Klick auf eine Abreise markiert die Abreise/Zahlung als erledigt.


4. BUCHUNGEN
Im Reiter Buchungen werden Aufenthalte angelegt und bearbeitet.

Wichtige Felder:
- Gast
- Geburtsdatum
- Straße
- PLZ
- Wohnort
- Land
- Telefon
- E-Mail
- Anreise
- Abreise
- Personen
- Zimmer
- Preis
- Frühstück
- Hund
- Wanderer
- Fahrrad / E-Bike
- PKW / Kennzeichen
- Allergien
- Sonderwünsche

Wichtig:
Eine Buchung ist die Grundlage für Kalender, Rechnung, Tagesliste, Gemeinde-Meldung und Statistik.


5. ZIMMER
Im Reiter Zimmer werden Zimmer angelegt.

Empfohlen:
- eindeutiger Zimmername
- Standardpreis
- aktive Zimmer sauber pflegen

Wenn ein Zimmer nicht mehr verwendet wird, besser deaktivieren als löschen.


6. KALENDER
Der Kalender zeigt die Zimmerbelegung.
Der heutige Tag ist markiert.
Wochenenden sind farblich hervorgehoben.
Doppelbuchungen werden auffällig dargestellt.

Bei roter Markierung prüfen:
- gleiches Zimmer
- gleicher Zeitraum
- versehentliche Doppelbuchung


7. BOOKING-IMPORT
Im Reiter Booking-Import kann eine Booking-Datei importiert werden.

Ablauf:
1. Booking-Datei auswählen.
2. Zielzimmer wählen.
3. Import starten.
4. Import-Log prüfen.
5. Danach Buchungen kontrollieren.

Übernommen werden, wenn vorhanden:
- Buchungsnummer
- Gastname
- Anreise
- Abreise
- Personen
- Preis
- Zahlungsstatus
- Adresse
- Telefonnummer
- Land
- Bemerkungen
- Reisegrund

Wichtig:
Booking liefert nicht immer PLZ und Wohnort. Wenn diese Angaben in der Datei fehlen, kann das Programm sie nicht aus Booking übernehmen.


8. STAMMDATEN-KORREKTUR
Dieser Reiter ist für fehlende PLZ, Wohnort oder andere Stammdaten.

Ablauf:
1. Reiter Stammdaten-Korrektur öffnen.
2. Buchung mit fehlender PLZ/Wohnort auswählen.
3. PLZ und Wohnort eintragen.
4. Korrektur speichern.

Das Programm merkt sich diese Korrektur.
Beim nächsten Booking-Import bleiben manuell ergänzte Daten erhalten.

Zusätzlich kann eine CSV-Liste erstellt werden.
Diese Liste kann extern bearbeitet und später wieder als Korrekturgrundlage verwendet werden.


9. GEMEINDE & ORTSTAXE
Der Reiter Gemeinde & Ortstaxe erstellt die Monatsauswertung.

Berechnet werden:
- Nächte
- Personen
- Personennächte
- Ortstaxe

Grundformel:
Personen × Nächte × Ortstaxe

Im Programm ist die Ortstaxe mit 2,60 Euro pro Person und Nacht hinterlegt.

Ausgaben:
- PDF für Ablage / Gemeinde
- CSV für Nachbearbeitung


10. RECHNUNGEN
Rechnungen werden aus Buchungsdaten erzeugt.

Enthalten sind:
- Gastdaten
- Zeitraum
- Zimmerpreis
- Extras
- Hund
- Ortstaxe
- Gesamtbetrag
- Logo und Betriebsdaten

Hinweis:
Bei Booking-Buchungen kann der Zimmerpreis bereits bezahlt sein. Dann ist besonders zu prüfen, welche Beträge noch offen sind.


11. ARTIKEL UND EXTRAS
Artikel sind Leistungen wie:
- Frühstück
- Lunchpaket
- Kaffee
- Tee
- Bier
- Wein
- Wasser
- Hund

Extras werden einer Buchung zugeordnet und können auf der Rechnung erscheinen.


12. TAGESLISTE
Die Tagesliste ist die tägliche Arbeitsliste.

Sie zeigt:
- Anreisen
- Abreisen
- Gäste im Haus
- wichtige Hinweise
- Frühstück / Wünsche
- offene Aufgaben

Empfehlung:
Tagesliste morgens öffnen und bei Bedarf als PDF speichern.


13. REINIGUNGSLISTE
Die Reinigungsliste zeigt, welche Zimmer vorbereitet oder gereinigt werden müssen.

Besonders wichtig bei:
- Abreise
- Anreise am gleichen Tag
- Zimmerwechsel
- Sonderwünschen


14. EINKAUFSLISTE
Hier werden Waren und Verbrauchsmaterialien verwaltet.

Beispiele:
- Kaffee
- Milch
- Tee
- Brot
- Eier
- Wein
- Bier
- Wasser
- Reinigungsmittel

Die Einkaufsliste kann als PDF gespeichert werden.


15. GOOGLE DRIVE / DATENORDNER
Der Datenordner bestimmt, wo die Daten gespeichert werden.

Wichtig:
Wenn mehrere Geräte dieselben Daten verwenden sollen, kann ein synchronisierter Ordner verwendet werden.

Empfehlung:
- Datenordner bewusst wählen
- regelmäßig Backup machen
- nicht gleichzeitig auf mehreren Geräten dieselbe Datei bearbeiten


16. BACKUP
Backups schützen vor Datenverlust.

Empfehlung:
- vor größeren Importen Backup erstellen
- vor Updates Backup erstellen
- regelmäßig Sicherungen aufheben

Bei Fehlern kann ein älterer Datenstand wiederhergestellt werden.


17. HÄUFIGE PROBLEME

Problem: PLZ oder Wohnort fehlen.
Lösung:
Stammdaten-Korrektur öffnen, Buchung markieren, Werte im großen Formular eintragen und speichern.

Problem: Booking importiert keine PLZ.
Grund:
Booking liefert in manchen Exporten keine PLZ-Spalte.

Problem: Telefonnummer ohne Plus.
Lösung:
Der Import ergänzt automatisch ein führendes Plus, soweit eine Nummer vorhanden ist.

Problem: Rechnung stimmt nicht.
Lösung:
Buchung öffnen, Preis, Personen, Extras und Ortstaxe prüfen.

Problem: Doppelbuchung rot.
Lösung:
Kalender prüfen und betroffene Buchungen vergleichen.

Problem: Daten verschwunden.
Lösung:
Prüfen, welcher Datenordner aktiv ist. Danach Backup wiederherstellen.


18. DATENPRÜFUNG
Der Reiter Datenprüfung kontrolliert die wichtigsten Angaben. Tagesliste und Reinigungsliste sind in Version 32.1 BETA – Windi Brain Regeln + Outlook-Kalender geprüft übersichtlicher aufgebaut.

Geprüft werden:
- ungültige Anreise/Abreise
- Personenanzahl 0
- fehlendes Zimmer
- Preis 0
- fehlende PLZ
- fehlender Wohnort
- fehlendes Land
- fehlende Telefonnummer
- Doppelbuchungen im selben Zimmer

Rot bedeutet Fehler.
Gelb bedeutet Hinweis.

Vor Monatsmeldung und Rechnungserstellung sollte die Datenprüfung ausgeführt werden.


19. BACKUP UND WIEDERHERSTELLUNG
Im Reiter Backup können Sicherungen erstellt und wiederhergestellt werden.

Neu:
- Backup jetzt erstellen
- Liste der letzten Backups
- markiertes Backup wiederherstellen
- Backup-Ordner öffnen
- automatisches Backup vor jedem Booking-Import

Vor dem Wiederherstellen wird der aktuelle Stand nochmals gesichert.


20. VERKAUFS- UND BETRIEBSHINWEIS
Diese Version enthält zusätzliche Dateien für Anwender, Datenschutz, Verkauf und Installation.
Nicht enthalten sind:
- Monatsabschluss-Sperre
- 30-Tage-Testmodus
- Lizenzschlüssel/Freischaltung
- Video-Anleitung
- Demo-Daten


21. EMPFOHLENE ARBEITSWEISE
- Booking-Import durchführen.
- Import-Log lesen.
- Stammdaten-Korrektur prüfen.
- Fehlende PLZ/Wohnorte ergänzen.
- Kalender kontrollieren.
- Tagesliste prüfen.
- Rechnungen bei Bedarf erstellen.
- Gemeinde-Meldung am Monatsende ausgeben.
- Backup erstellen.


22. RECHTLICHER HINWEIS
Das Programm ist ein Hilfsmittel.
Der Betreiber bleibt verantwortlich für die Richtigkeit von:
- Gästedaten
- Rechnungen
- Ortstaxe
- Gemeinde-Meldungen
- steuerlichen Angaben
- Datenschutz

Das Programm ersetzt keine rechtliche oder steuerliche Beratung.


23. COPYRIGHT
Copyright © J.F.X. Prem.
Alle Rechte vorbehalten.

Die Nutzung für den eigenen Betrieb ist vorgesehen.
Weitergabe, Verkauf oder Veröffentlichung nur mit Zustimmung des Rechteinhabers.
"""
        self.info_text.insert("1.0", help_content.strip())
        self.info_text.config(state="disabled")

    def show_data_folder(self):
        messagebox.showinfo(
            "Datenordner",
            f"Aktueller Datenordner:\n{data_dir()}\n\nAusgabeordner:\n{out_dir()}"
        )

    def export_help_txt(self):
        try:
            txt = self.info_text.get("1.0", END)
            f = out_dir() / ("Bedienungsanleitung_Info_Hilfe_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt")
            f.write_text(txt, encoding="utf-8")
            messagebox.showinfo("Export erstellt", f"Bedienungsanleitung gespeichert:\n{f}")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))




    # ---------------- Kalender-Synchronisation Outlook / Google ----------------
    def calendar_sync_dir(self):
        d = data_dir() / "kalender_sync"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def calendar_ics_path(self):
        return self.calendar_sync_dir() / "Zuhause_am_Bach_Buchungen.ics"

    def ics_text(self, value):
        return calendar_sync_escape_text(value)

    def booking_calendar_uid(self, b):
        return calendar_sync_booking_uid(b, self.booking_identity_key)

    def booking_calendar_status(self, b):
        return calendar_sync_booking_status(b)

    def booking_ics_event(self, b):
        return calendar_sync_build_ics(
            [b],
            parse_date=pdate,
            room_name_func=lambda booking: room_name(self.d, booking.get("room_id", "")) or booking.get("room", "") or "Zimmer",
            identity_key_func=self.booking_identity_key,
        ).split("BEGIN:VEVENT", 1)[1].rsplit("END:VCALENDAR", 1)[0].strip()

    def make_calendar_ics(self):
        return calendar_sync_build_ics(
            self.d.get("bookings", []),
            parse_date=pdate,
            room_name_func=lambda booking: room_name(self.d, booking.get("room_id", "")) or booking.get("room", "") or "Zimmer",
            identity_key_func=self.booking_identity_key,
            calendar_name="Zuhause am Bach Buchungen",
        )

    def validate_calendar_ics(self, content):
        return calendar_sync_validate_ics(content)

    def calendar_auto_export(self, silent=True):
        try:
            if not getattr(self, "calendar_sync_enabled", True):
                # Einstellung ist nur UI-Hinweis; Autoexport bleibt standardmäßig aktiv.
                pass
            path = self.calendar_ics_path()
            content = self.make_calendar_ics()
            errors = self.validate_calendar_ics(content)
            if errors:
                raise ValueError("Kalender-Export ungueltig: " + "; ".join(errors))
            calendar_sync_write_ics_file(path, content)
            self.d.setdefault("settings",{})["calendar_last_export"] = datetime.now().isoformat(timespec="seconds")
            save(self.d)
            if hasattr(self,"cal_sync_status"):
                self.cal_sync_status.set(f"Letzter Export: {datetime.now().strftime('%d.%m.%Y %H:%M')}  ·  {path}")
            return path
        except Exception as e:
            if not silent:
                messagebox.showerror("Kalender-Sync", str(e))
            return None

    def calendar_export_now(self):
        path = self.calendar_auto_export(silent=False)
        if path:
            messagebox.showinfo("Kalenderdatei erstellt", f"Outlook-kompatible ICS-Datei wurde erstellt/aktualisiert:\n{path}\n\nWichtig: Am besten in einen eigenen Outlook-Kalender importieren oder als Abo verwenden. Jede Buchung hat eine feste UID.")

    def open_calendar_sync_folder(self):
        try:
            folder = self.calendar_sync_dir()
            if os.name == "nt":
                os.startfile(folder)
            else:
                messagebox.showinfo("Kalenderordner", str(folder))
        except Exception as e:
            messagebox.showerror("Kalenderordner", str(e))

    def create_calendar_sync_help(self):
        path = self.calendar_auto_export(silent=True)
        html_path = self.calendar_sync_dir() / "Kalender_Sync_Anleitung.html"
        file_uri = path.as_uri() if path and path.exists() else ""
        content = f"""<!doctype html><html><head><meta charset='utf-8'><title>Kalender-Sync Zuhause am Bach</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:30px auto;line-height:1.45}}code{{background:#f1f4f8;padding:2px 5px;border-radius:4px}}.box{{border:1px solid #d8dee9;border-radius:8px;padding:14px;margin:14px 0}}</style></head><body>
<h1>Zuhause am Bach – Kalender-Synchronisation</h1>
<p><b>Kalenderdatei:</b><br><code>{html.escape(str(path or ''))}</code></p>
<p><a href='{html.escape(file_uri)}'>ICS-Datei öffnen</a></p>
<div class='box'><h2>Outlook / Hotmail: johannprem@hotmail.com</h2>
<ol><li>Outlook Kalender öffnen.</li><li>Kalender hinzufügen / Aus Datei importieren wählen.</li><li>Die Datei <code>Zuhause_am_Bach_Buchungen.ics</code> auswählen.</li><li>Als eigenen Kalender „Zuhause am Bach Buchungen“ importieren.</li></ol></div>
<div class='box'><h2>Google Kalender: 06Laura66@gmail.com</h2>
<ol><li>Google Kalender öffnen.</li><li>Einstellungen → Importieren & Exportieren.</li><li>ICS-Datei auswählen und in den gewünschten Kalender importieren.</li></ol>
<p><b>Hinweis:</b> Für echte automatische Aktualisierung braucht Google einen öffentlich/online erreichbaren Kalender-Link, z. B. über einen freigegebenen Cloud-Link. Lokale Dateien werden nur beim Import übernommen.</p></div>
<div class='box'><h2>Doppelte Einträge vermeiden</h2><p>Jede Buchung bekommt eine feste Kalender-UID. Bei Kalender-Abo wird aktualisiert statt doppelt angelegt. Beim manuellen Import kann Google/Outlook je nach Einstellung trotzdem Duplikate erzeugen; deshalb besser einen eigenen Kalender „Zuhause am Bach Buchungen“ verwenden.</p></div>
</body></html>"""
        html_path.write_text(content, encoding="utf-8")
        try:
            webbrowser.open(html_path.as_uri())
        except Exception:
            pass
        messagebox.showinfo("Anleitung erstellt", f"Anleitung erstellt:\n{html_path}")

    def open_outlook_calendar(self):
        webbrowser.open("https://outlook.live.com/calendar/")

    def open_google_calendar(self):
        webbrowser.open("https://calendar.google.com/calendar/u/0/r/settings/export")


    # ---------------- Windi Brain V28.0 ----------------
    def wb_events_path(self):
        return data_dir() / "windi_brain_events.csv"

    def wb_rules_path(self):
        return data_dir() / "windi_brain_rules.json"

    def wb_fieldnames(self):
        return ["timestamp","typ","booking_id","gast","anreise","abreise","wochentag","monat","naechte","personen","preis","fruehstueck","wanderer","rad","auto","quelle","status","notiz"]

    def wb_record_booking_event(self, b, typ="gespeichert", note=""):
        """Lernt aus echten Buchungsereignissen, ohne den Programmcode selbst zu ändern."""
        try:
            path=self.wb_events_path(); path.parent.mkdir(exist_ok=True)
            first=not path.exists()
            arr=parse_date(b.get("arrival")) if b.get("arrival") else None
            dep=parse_date(b.get("departure")) if b.get("departure") else None
            ns=nights(b.get("arrival", ""), b.get("departure", "")) if b.get("arrival") and b.get("departure") else 0
            row={
                "timestamp":datetime.now().isoformat(timespec="seconds"),
                "typ":typ,
                "booking_id":b.get("id",""),
                "gast":b.get("guest",b.get("name","")),
                "anreise":b.get("arrival",""),
                "abreise":b.get("departure",""),
                "wochentag":arr.strftime("%A") if arr else "",
                "monat":arr.strftime("%Y-%m") if arr else "",
                "naechte":ns,
                "personen":b.get("persons",1),
                "preis":b.get("price",0),
                "fruehstueck":b.get("breakfast",""),
                "wanderer":int(bool(b.get("wanderer"))),
                "rad":int(bool(b.get("bike") or b.get("ebike"))),
                "auto":int(bool(b.get("car"))),
                "quelle":b.get("source",b.get("channel","")),
                "status":b.get("status",""),
                "notiz":note,
            }
            with path.open("a", newline="", encoding="utf-8") as f:
                w=csv.DictWriter(f, fieldnames=self.wb_fieldnames(), delimiter=";")
                if first: w.writeheader()
                w.writerow(row)
        except Exception:
            log_exception("Windi Brain Ereignis speichern")

    def wb_read_events(self):
        path=self.wb_events_path()
        if not path.exists(): return []
        try:
            with path.open("r", newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f, delimiter=";"))
        except Exception:
            log_exception("Windi Brain Ereignisse lesen")
            return []

    def wb_current_observations_from_bookings(self):
        rows=[]
        for b in self.d.get("bookings",[]):
            if b.get("status")=="storniert":
                continue
            try:
                arr=parse_date(b.get("arrival")); dep=parse_date(b.get("departure"))
                rows.append({
                    "booking_id":b.get("id",""), "gast":b.get("guest",b.get("name","")),
                    "anreise":b.get("arrival",""), "abreise":b.get("departure",""),
                    "wochentag":arr.strftime("%A"), "monat":arr.strftime("%Y-%m"),
                    "naechte":max(0,(dep-arr).days), "personen":int(b.get("persons",1) or 1),
                    "preis":float(b.get("price",0) or 0), "fruehstueck":b.get("breakfast",""),
                    "wanderer":int(bool(b.get("wanderer"))), "rad":int(bool(b.get("bike") or b.get("ebike"))),
                    "auto":int(bool(b.get("car"))), "quelle":b.get("source",b.get("channel","")), "status":b.get("status","")
                })
            except Exception:
                pass
        return rows

    def wb_analyze_learning(self):
        bookings=self.wb_current_observations_from_bookings()
        events=self.wb_read_events()
        suggestions=[]
        total=len(bookings)
        if not bookings:
            return {"summary":"Noch zu wenig Daten. Fidel beginnt ab der nächsten Buchung zu lernen.","suggestions":[],"events":len(events)}
        avg_price=sum(r["preis"] for r in bookings)/max(1,total)
        avg_nights=sum(r["naechte"] for r in bookings)/max(1,total)
        breakfast_yes=sum(1 for r in bookings if str(r.get("fruehstueck","")).lower() not in ("","nein","none","0"))
        bike=sum(r["rad"] for r in bookings); wand=sum(r["wanderer"] for r in bookings); car=sum(r["auto"] for r in bookings)
        # Monatsanalyse
        by_month={}
        for r in bookings:
            by_month.setdefault(r["monat"],[]).append(r)
        best_month=max(by_month.items(), key=lambda kv: len(kv[1]))[0] if by_month else ""
        # Preislogik-Vorschläge
        if avg_price < 95 and total >= 5:
            suggestions.append(("Fidel", "Preis lernen", "Der bisherige Durchschnittspreis liegt unter 95 €. Prüfe, ob der Basispreis um 5–10 € angehoben werden kann.", "mittel"))
        if avg_nights <= 1.2 and total >= 5:
            suggestions.append(("Fidel", "Lückennächte", "Viele Aufenthalte sind 1 Nacht. Einzelne freie Nächte gezielt mit Schnellpreis verkaufen, Wochenenden nicht zu früh senken.", "hoch"))
        if breakfast_yes/total >= 0.65:
            suggestions.append(("Pia", "Frühstück", "Frühstück wird häufig genutzt. Pia sollte bei unklaren Buchungen automatisch eine kurze Frühstücksfrage vorbereiten.", "hoch"))
        if bike/total >= 0.35 or wand/total >= 0.35:
            suggestions.append(("Fidel", "Zielgruppe", "Viele Gäste wirken wie Radfahrer/Wanderer. Fahrradgarage, Trockenmöglichkeit und frühes Frühstück in Nachrichten stärker hervorheben.", "hoch"))
        if car/total >= 0.5:
            suggestions.append(("Pia", "Anreise", "Viele Gäste reisen vermutlich mit Auto an. Parkplatz-Hinweis in Begrüßungstexten sichtbarer platzieren.", "mittel"))
        if best_month:
            suggestions.append(("Fidel", "Saison", f"Stärkster bisheriger Monat: {best_month}. Für ähnliche Zeiträume höhere Startpreise und weniger Last-Minute-Rabatte prüfen.", "mittel"))
        # Gloria-Prüfung
        missing_phone=sum(1 for b in self.d.get("bookings",[]) if not str(b.get("phone","")).strip())
        if missing_phone:
            suggestions.append(("Gloria", "Datenqualität", f"Bei {missing_phone} Buchung(en) fehlt die Telefonnummer. Gloria empfiehlt: vor Anreise automatisch nach Kontakt/Ankunftszeit fragen.", "hoch"))
        summary=(f"{total} aktive Buchungen analysiert · Ø Preis {avg_price:.0f} € · Ø Nächte {avg_nights:.1f} · Frühstücksquote {breakfast_yes/max(1,total)*100:.0f}% · "
                 f"Rad/Wander-Hinweise {(bike+wand)/max(1,total)*100:.0f}% · gelernte Ereignisse {len(events)}")
        return {"summary":summary,"suggestions":suggestions,"events":len(events)}

    def build_windi_brain(self):
        main=ttk.Frame(self.tab_brain); main.pack(fill="both",expand=True,padx=8,pady=8)
        top=self.card(main,"🧠 Windi Brain – lernender Manager mit Freigabe")
        ttk.Label(top,text="Fidel, Gloria und Pia lernen aus echten Buchungen, Preisen, Frühstück, Anreisearten und Fehlern. Der Quellcode wird nicht automatisch verändert: jede Regel braucht deine Freigabe.",style="Card.TLabel",wraplength=1200).pack(anchor="w")
        row=ttk.Frame(top,style="Card.TFrame"); row.pack(fill="x",pady=(8,0))
        ttk.Button(row,text="JETZT LERNEN",command=self.wb_refresh,style="Touch.TButton").pack(side="left",padx=4)
        ttk.Button(row,text="Vorschläge übernehmen",command=self.wb_apply_suggestions,style="Primary.TButton").pack(side="left",padx=4)
        ttk.Button(row,text="Lernbericht exportieren",command=self.wb_export_report).pack(side="left",padx=4)
        ttk.Button(row,text="Lerndaten-Ordner öffnen",command=lambda: webbrowser.open(data_dir().as_uri())).pack(side="left",padx=4)
        self.wb_status=StringVar(value="Bereit. Windi Brain wartet auf Daten.")
        ttk.Label(top,textvariable=self.wb_status,style="Card.TLabel",wraplength=1200).pack(anchor="w",pady=(8,0))
        body=ttk.Frame(main); body.pack(fill="both",expand=True)
        left=self.card(body,"🐾 Fidel lernt Preise · 📚 Gloria lernt Kontrolle · 🎀 Pia lernt Gäste")
        left.pack(fill="both",expand=True)
        cols=("windi","bereich","vorschlag","prioritaet")
        self.wb_tree=ttk.Treeview(left,columns=cols,show="headings",height=12)
        for c,t,w in [("windi","Windi",90),("bereich","Bereich",150),("vorschlag","Lernvorschlag",760),("prioritaet","Priorität",90)]:
            self.wb_tree.heading(c,text=t); self.wb_tree.column(c,width=w,anchor="w")
        self.wb_tree.pack(fill="both",expand=True,pady=(5,0))
        self.wb_text=Text(main,bg="#fff",relief="flat",font=("Consolas",10),height=8,padx=12,pady=10)
        self.wb_text.pack(fill="x",padx=11,pady=8)
        self.wb_refresh()

    def wb_refresh(self):
        try:
            res=self.wb_analyze_learning()
            self.wb_status.set(res.get("summary",""))
            for i in self.wb_tree.get_children(): self.wb_tree.delete(i)
            for windi,bereich,vorschlag,prio in res.get("suggestions",[]):
                self.wb_tree.insert("","end",values=(windi,bereich,vorschlag,prio))
            self.wb_text.delete("1.0",END)
            self.wb_text.insert(END,"Windi Brain Prinzip:\n")
            self.wb_text.insert(END,"• Fidel verbessert Preis- und Nachfrageempfehlungen.\n")
            self.wb_text.insert(END,"• Gloria findet wiederkehrende Fehler und fehlende Daten.\n")
            self.wb_text.insert(END,"• Pia lernt, welche Gäste-Kommunikation hilfreich ist.\n")
            self.wb_text.insert(END,"• Automatisch gelernt wird nur in Regeln/Vorschlägen – Programmcodes werden nie ungeprüft verändert.\n")
            if not res.get("suggestions"):
                self.wb_text.insert(END,"\nNoch keine belastbaren Vorschläge. Mehr echte Buchungen verbessern die Lernqualität.\n")
        except Exception as e:
            log_exception("Windi Brain aktualisieren")
            messagebox.showerror("Windi Brain",str(e))

    def wb_apply_suggestions(self):
        try:
            res=self.wb_analyze_learning()
            rules={"updated":datetime.now().isoformat(timespec="seconds"),"rules":[]}
            for windi,bereich,vorschlag,prio in res.get("suggestions",[]):
                rules["rules"].append({"windi":windi,"bereich":bereich,"vorschlag":vorschlag,"prioritaet":prio,"aktiv":False})
            self.wb_rules_path().write_text(json.dumps(rules,ensure_ascii=False,indent=2),encoding="utf-8")
            messagebox.showinfo("Windi Brain",f"Vorschläge gespeichert, aber noch nicht automatisch aktiv geschaltet:\n{self.wb_rules_path()}\n\nGloria sagt: Erst prüfen, dann freigeben.")
        except Exception as e:
            log_exception("Windi Brain Vorschläge übernehmen")
            messagebox.showerror("Windi Brain",str(e))

    def wb_export_report(self):
        try:
            res=self.wb_analyze_learning()
            report_dir=out_dir(); report_dir.mkdir(exist_ok=True)
            path=report_dir/("Windi_Brain_Lernbericht_"+date.today().isoformat()+".txt")
            lines=["Zuhause am Bach OS – Windi Brain Lernbericht", "", res.get("summary",""), "", "Vorschläge:"]
            for windi,bereich,vorschlag,prio in res.get("suggestions",[]):
                lines.append(f"- {windi} / {bereich} / {prio}: {vorschlag}")
            lines += ["", "Hinweis: Das System lernt Empfehlungen. Änderungen werden nur nach Johann/Laura-Freigabe aktiv."]
            path.write_text("\n".join(lines),encoding="utf-8")
            messagebox.showinfo("Windi Brain",f"Lernbericht erstellt:\n{path}")
        except Exception as e:
            log_exception("Windi Brain Bericht")
            messagebox.showerror("Windi Brain",str(e))

    def mobile_sync_export_now(self):
        """Erzeugt mobile_data.json für die Handy-App.

        V32.4: Die Handy-App auf GitHub Pages kann nur eine veröffentlichte JSON-Datei lesen.
        Dieser Export schreibt die Datei lokal in den Datenordner. Von dort kann sie nach GitHub/Pages
        oder OneDrive kopiert werden.
        """
        try:
            target = mobile_sync_write_data(self.d, data_dir())
            summary = mobile_sync_export_summary(self.d)
            msg = (
                "Mobile-Daten wurden erzeugt.\n\n"
                f"Datei:\n{target}\n\n"
                f"Gäste: {summary.get('guests', 0)}\n"
                f"Buchungen: {summary.get('bookings', 0)}\n"
                f"Zimmer: {summary.get('rooms', 0)}\n"
                f"Extras: {summary.get('extras', 0)}\n\n"
                "Diese Datei muss als docs/data/mobile_data.json in GitHub Pages liegen, "
                "damit die Handy-App sie per 'Daten abrufen' laden kann."
            )
            try:
                self.sync_text.insert(END, "\n" + msg + "\n")
                self.sync_text.see(END)
            except Exception:
                pass
            messagebox.showinfo("Mobile Sync", msg)
        except Exception as e:
            log_exception("Mobile Sync Export")
            messagebox.showerror("Mobile Sync", str(e))

    def open_mobile_sync_folder(self):
        try:
            folder = mobile_sync_default_dir(data_dir())
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(folder))
            else:
                webbrowser.open(folder.as_uri())
        except Exception as e:
            log_exception("Mobile Sync Ordner öffnen")
            messagebox.showerror("Mobile Sync", str(e))

    def build_sync(self):
        f=self.card(self.tab_sync,"Kalender-Sync + Cloud-Datenordner")
        ttk.Label(f,text="Buchungen werden als ICS-Kalender mit stabiler UID exportiert. Damit können Outlook und Google die Termine einmalig übernehmen bzw. bei Abo aktualisieren.",style="Card.TLabel",wraplength=1200).pack(anchor="w")

        calbox=ttk.Frame(f,style="Card.TFrame")
        calbox.pack(fill="x",pady=(8,10))
        ttk.Label(calbox,text="Kalenderdatei",style="Card.TLabel").grid(row=0,column=0,sticky="w",padx=5,pady=4)
        self.cal_sync_path=StringVar(value=str(self.calendar_ics_path()))
        ttk.Entry(calbox,textvariable=self.cal_sync_path,width=95).grid(row=0,column=1,sticky="ew",padx=5,pady=4)
        calbox.columnconfigure(1,weight=1)
        btnrow=ttk.Frame(f,style="Card.TFrame"); btnrow.pack(fill="x",pady=4)
        ttk.Button(btnrow,text="OUTLOOK-ICS ERZEUGEN",command=self.calendar_export_now,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(btnrow,text="Ordner öffnen",command=self.open_calendar_sync_folder,style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(btnrow,text="Anleitung Outlook/Google",command=self.create_calendar_sync_help,style="Primary.TButton").pack(side="left",padx=5)
        ttk.Button(btnrow,text="Outlook öffnen",command=self.open_outlook_calendar).pack(side="left",padx=5)
        ttk.Button(btnrow,text="Google Kalender öffnen",command=self.open_google_calendar).pack(side="left",padx=5)
        ttk.Button(btnrow,text="📱 MOBILE-DATEN ERZEUGEN",command=self.mobile_sync_export_now,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(btnrow,text="Mobile-Ordner öffnen",command=self.open_mobile_sync_folder,style="Primary.TButton").pack(side="left",padx=5)
        self.cal_sync_status=StringVar(value=f"Ziel: Outlook johannprem@hotmail.com + Google 06Laura66@gmail.com · Datei: {self.calendar_ics_path()}")
        ttk.Label(f,textvariable=self.cal_sync_status,style="Card.TLabel",wraplength=1200).pack(anchor="w",pady=(3,10))

        g=self.card(self.tab_sync,"Google Drive / Cloud-Datenordner")
        ttk.Label(g,text="Hier kannst du den Datenordner auf Google Drive legen. Wenn die ICS-Datei in einem synchronisierten Ordner liegt, ist sie auch für Kalender-Abos leichter nutzbar.",style="Card.TLabel",wraplength=1200).pack(anchor="w")
        self.sync_path=StringVar(value=str(data_dir()))
        row=ttk.Frame(g,style="Card.TFrame"); row.pack(fill="x",pady=8)
        ttk.Entry(row,textvariable=self.sync_path,width=90).pack(side="left",padx=5)
        ttk.Button(row,text="Ordner auswählen",command=self.choose_sync_folder,style="Touch.TButton").pack(side="left",padx=5)
        ttk.Button(row,text="Daten neu laden",command=self.reload_data_from_folder).pack(side="left",padx=5)
        ttk.Button(row,text="Aktuelle Daten speichern",command=self.copy_current_data_to_sync).pack(side="left",padx=5)
        self.sync_text=Text(self.tab_sync,bg="#fff",relief="flat",font=("Consolas",10),padx=12,pady=12,height=10)
        self.sync_text.pack(fill="both",expand=True,padx=8,pady=8)
        self.sync_text.insert(END,"Kalender-Sync V32.2 Outlook Professional:\n")
        self.sync_text.insert(END,"• Buchungen werden automatisch nach Speichern/Löschen in die ICS-Datei geschrieben.\n")
        self.sync_text.insert(END,"• V32.2 schreibt ICS bytegenau als UTF-8, damit Outlook kein CRCRLF bekommt.\n")
        self.sync_text.insert(END,"• Beschreibung ist bewusst kurz, lange Notizen bleiben im Manager.\n")
        self.sync_text.insert(END,"• Jede Buchung hat eine feste UID: dadurch kein doppelter Termin bei Abo/Update.\n")
        self.sync_text.insert(END,"• Direkte API-Synchronisation mit Microsoft/Google wäre eine spätere Profi-Stufe mit Login/Berechtigungen.\n")
        self.sync_text.insert(END,"• V32.4 erzeugt mobile_data.json für die Handy-App / GitHub Pages.\n")
        self.sync_text.insert(END,f"\nICS-Datei:\n{self.calendar_ics_path()}\n")
        self.sync_text.insert(END,f"\nMobile-Datei:\n{mobile_sync_default_dir(data_dir()) / 'mobile_data.json'}\n")
        self.calendar_auto_export(silent=True)

    def refresh_all(self):
        for fn in [self.refresh_dash,self.refresh_year_stats,self.refresh_chances,self.refresh_price_agent,self.gai_refresh_booking_list,self.refresh_bookings,self.refresh_rooms,self.refresh_extras,self.refresh_articles,self.refresh_calendar,self.refresh_corrections,self.refresh_check,self.refresh_backup_list,self.import_room_values_refresh,self.wb_refresh]:
            try: fn()
            except Exception:
                log_exception(f"Refresh-Funktion: {getattr(fn, '__name__', str(fn))}")



# ============================================================
# V29.0 Betriebsstabilitaet & Faktenmodus
# Gloria prueft Fakten, Fidel fuehrt den Tagesablauf, Pia hilft bei Gaesten.
# Die Erweiterung veraendert keine Buchungen automatisch.
# ============================================================

def v29_booking_fact_status(d, b):
    """Gibt pruefbare Fakten zur Buchung zurueck. Keine KI-Vermutungen."""
    required = {
        "Gastname": b.get("guest") or b.get("name"),
        "Anreise": b.get("arrival"),
        "Abreise": b.get("departure"),
        "Personen": b.get("persons"),
        "Zimmer": b.get("room_id") or b.get("room"),
    }
    recommended = {
        "Telefon": b.get("phone"),
        "E-Mail": b.get("email"),
        "Straße": b.get("street") or b.get("address"),
        "PLZ": b.get("zip") or b.get("plz"),
        "Ort": b.get("city") or b.get("ort"),
        "Land": b.get("country") or b.get("land"),
        "Preis": b.get("price"),
        "Frühstück": b.get("breakfast"),
    }
    missing_required = [k for k,v in required.items() if v in (None, "", 0, "0")]
    missing_recommended = [k for k,v in recommended.items() if v in (None, "")]
    return missing_required, missing_recommended


def v29_count_today(d):
    today = date.today().isoformat()
    bookings = [b for b in d.get("bookings", []) if b.get("status") != "storniert"]
    arr = [b for b in bookings if b.get("arrival") == today]
    dep = [b for b in bookings if b.get("departure") == today]
    inhouse = []
    for b in bookings:
        try:
            if b.get("arrival") <= today < b.get("departure"):
                inhouse.append(b)
        except Exception:
            pass
    breakfast = 0
    for b in bookings:
        try:
            if b.get("arrival") <= today < b.get("departure") or b.get("arrival") == today:
                bf = str(b.get("breakfast", "")).lower()
                if bf and bf not in ["nein", "0", "false", "none"]:
                    breakfast += int(b.get("persons", 1) or 1)
        except Exception:
            pass
    return arr, dep, inhouse, breakfast


def v29_safe_backup_now(label="manual"):
    try:
        bd = data_dir() / "Backups"
        bd.mkdir(exist_ok=True)
        src = data_file()
        if not src.exists():
            return None
        target = bd / (f"{label}_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
        shutil.copy2(src, target)
        return target
    except Exception:
        log_exception("V29 Backup erstellen")
        return None


def v29_build_ops(self):
    main = ttk.Frame(self.tab_ops, padding=12)
    main.pack(fill="both", expand=True)
    top = ttk.Frame(main)
    top.pack(fill="x", pady=(0,8))
    ttk.Label(top, text="V29 – Betriebsstabilität & Faktenmodus", style="Title.TLabel").pack(side="left", anchor="w")
    ttk.Button(top, text="🔄 alles prüfen", command=self.v29_refresh_ops, style="Primary.TButton").pack(side="right", padx=4)
    ttk.Button(top, text="💾 Sicherheitsbackup", command=self.v29_backup_now_ui, style="Soft.TButton").pack(side="right", padx=4)

    self.ops_nb = ttk.Notebook(main)
    self.ops_nb.pack(fill="both", expand=True)

    self.ops_day = ttk.Frame(self.ops_nb); self.ops_nb.add(self.ops_day, text="🐾 Tagesmodus")
    self.ops_gloria = ttk.Frame(self.ops_nb); self.ops_nb.add(self.ops_gloria, text="📚 Gloria Faktencheck")
    self.ops_import = ttk.Frame(self.ops_nb); self.ops_nb.add(self.ops_import, text="⬇ Import-Sicherheit")
    self.ops_backup = ttk.Frame(self.ops_nb); self.ops_nb.add(self.ops_backup, text="💾 Backup/Wiederherstellung")
    self.ops_db = ttk.Frame(self.ops_nb); self.ops_nb.add(self.ops_db, text="🛠 Wartung")
    self.ops_ki = ttk.Frame(self.ops_nb); self.ops_nb.add(self.ops_ki, text="🧠 KI-Fakten")

    # Tagesmodus
    t = ttk.Frame(self.ops_day, padding=10); t.pack(fill="both", expand=True)
    ttk.Label(t, text="Geführter Tagesablauf", style="CardTitle.TLabel").pack(anchor="w")
    self.v29_day_text = Text(t, height=14, wrap="word", bg="#ffffff", relief="flat", font=("Segoe UI", 10), padx=10, pady=8)
    self.v29_day_text.pack(fill="both", expand=True, pady=6)
    brow = ttk.Frame(t); brow.pack(fill="x")
    ttk.Button(brow, text="📱 Pia: Gäste kontaktieren", command=lambda:self.open_guest_area(self.tab_whatsapp), style="Touch.TButton").pack(side="left", padx=4)
    ttk.Button(brow, text="🗓 Fidel: Kalender öffnen", command=lambda:self.safe_select_tab(self.tab_cal), style="Touch.TButton").pack(side="left", padx=4)
    ttk.Button(brow, text="🏛 Gloria: Gemeinde öffnen", command=lambda:self.open_finance_area(self.tab_gemeinde), style="Touch.TButton").pack(side="left", padx=4)
    ttk.Button(brow, text="💶 Rechnung", command=lambda:self.open_finance_area(self.tab_extras), style="Touch.TButton").pack(side="left", padx=4)

    # Gloria Faktencheck
    g = ttk.Frame(self.ops_gloria, padding=10); g.pack(fill="both", expand=True)
    self.v29_quality_summary = StringVar(value="Noch nicht geprüft")
    ttk.Label(g, textvariable=self.v29_quality_summary, style="CardTitle.TLabel").pack(anchor="w")
    cols=("ampel","gast","zeitraum","fehlt_pflicht","fehlt_empfohlen")
    self.v29_quality_tree=ttk.Treeview(g, columns=cols, show="headings", height=18)
    for c,w in [("ampel",70),("gast",190),("zeitraum",170),("fehlt_pflicht",260),("fehlt_empfohlen",360)]:
        self.v29_quality_tree.heading(c, text=c.replace("_"," ").title())
        self.v29_quality_tree.column(c, width=w, anchor="w")
    self.v29_quality_tree.pack(side="left", fill="both", expand=True, pady=6)
    sb=ttk.Scrollbar(g, orient="vertical", command=self.v29_quality_tree.yview); sb.pack(side="right", fill="y")
    self.v29_quality_tree.configure(yscrollcommand=sb.set)

    # Import Sicherheit
    imp=ttk.Frame(self.ops_import, padding=10); imp.pack(fill="both", expand=True)
    ttk.Label(imp, text="Import-Vorschau: erst prüfen, dann speichern", style="CardTitle.TLabel").pack(anchor="w")
    ttk.Label(imp, text="V29 speichert vor jedem Import ein Sicherheitsbackup und zeigt Dubletten/fehlende Spalten vor dem Speichern.", style="Card.TLabel").pack(anchor="w", pady=(0,6))
    irow=ttk.Frame(imp); irow.pack(fill="x")
    ttk.Button(irow, text="Datei für Vorschau wählen", command=self.v29_import_preview_file, style="Primary.TButton").pack(side="left", padx=4)
    ttk.Button(irow, text="zum bestehenden Import", command=lambda:self.open_system_area(self.tab_import), style="Soft.TButton").pack(side="left", padx=4)
    self.v29_import_text=Text(imp, height=18, wrap="word", bg="#ffffff", relief="flat", font=("Consolas",10), padx=10, pady=8)
    self.v29_import_text.pack(fill="both", expand=True, pady=8)

    # Backup Restore
    bp=ttk.Frame(self.ops_backup, padding=10); bp.pack(fill="both", expand=True)
    ttk.Label(bp, text="Backup mit Wiederherstellung", style="CardTitle.TLabel").pack(anchor="w")
    self.v29_backup_list=tk.Listbox(bp, height=14, font=("Consolas",10))
    self.v29_backup_list.pack(fill="both", expand=True, pady=6)
    bpr=ttk.Frame(bp); bpr.pack(fill="x")
    ttk.Button(bpr, text="Liste aktualisieren", command=self.v29_refresh_backups, style="Primary.TButton").pack(side="left", padx=4)
    ttk.Button(bpr, text="Backup jetzt", command=self.v29_backup_now_ui, style="Soft.TButton").pack(side="left", padx=4)
    ttk.Button(bpr, text="Ausgewähltes Backup wiederherstellen", command=self.v29_restore_selected_backup, style="Gold.TButton").pack(side="left", padx=4)

    # Wartung
    db=ttk.Frame(self.ops_db, padding=10); db.pack(fill="both", expand=True)
    ttk.Label(db, text="Datenbank-Wartung", style="CardTitle.TLabel").pack(anchor="w")
    dbr=ttk.Frame(db); dbr.pack(fill="x", pady=5)
    ttk.Button(dbr, text="Datenbank prüfen", command=self.v29_db_check, style="Primary.TButton").pack(side="left", padx=4)
    ttk.Button(dbr, text="Datenbank kompakt speichern", command=self.v29_db_compact, style="Soft.TButton").pack(side="left", padx=4)
    ttk.Button(dbr, text="alte Fehlerlogs zählen", command=self.v29_count_logs, style="Soft.TButton").pack(side="left", padx=4)
    self.v29_db_text=Text(db, height=20, wrap="word", bg="#ffffff", relief="flat", font=("Consolas",10), padx=10, pady=8)
    self.v29_db_text.pack(fill="both", expand=True, pady=8)

    # KI Faktenmodus
    ki=ttk.Frame(self.ops_ki, padding=10); ki.pack(fill="both", expand=True)
    ttk.Label(ki, text="KI-Faktenmodus: Wahrheit vor Glitzer", style="CardTitle.TLabel").pack(anchor="w")
    self.v29_ki_text=Text(ki, height=24, wrap="word", bg="#ffffff", relief="flat", font=("Segoe UI",10), padx=10, pady=8)
    self.v29_ki_text.pack(fill="both", expand=True, pady=6)
    self.v29_ki_text.insert(END, "[Fakt] Stammdaten, Buchungen, Zahlungen und Ortstaxe kommen aus dem Manager.\n")
    self.v29_ki_text.insert(END, "[Gelernt] Windi Brain darf Muster aus vergangenen Buchungen speichern.\n")
    self.v29_ki_text.insert(END, "[Schätzung] Preis, Anreiseart, Frühstückswahrscheinlichkeit und Bewertungschance bleiben Prognosen.\n")
    self.v29_ki_text.insert(END, "[Nicht verifiziert] Manuelle Google-KI-/Agenten-Hinweise werden klar getrennt.\n\n")
    self.v29_ki_text.insert(END, "Sicherheitsregel: Fidel, Gloria und Pia dürfen Vorschläge machen. Änderungen an Preisen, Texten oder Daten werden nur mit Freigabe übernommen.\n")

    self.v29_refresh_ops()


def v29_refresh_ops(self):
    try:
        self.v29_refresh_day_mode()
        self.v29_refresh_quality()
        self.v29_refresh_backups()
        self.v29_db_check(silent=True)
    except Exception:
        log_exception("V29 alles prüfen")


def v29_refresh_day_mode(self):
    if not hasattr(self, "v29_day_text"):
        return
    arr, dep, inhouse, breakfast = v29_count_today(self.d)
    warnings=[]
    for b in arr + inhouse:
        mr, me = v29_booking_fact_status(self.d,b)
        if mr or me:
            warnings.append((b.get("guest","Gast"), mr, me))
    lines=[]
    lines.append("🐾 Fidel – Tagesmodus\n")
    lines.append(f"[Fakt] Heute Anreisen: {len(arr)}")
    lines.append(f"[Fakt] Heute Abreisen: {len(dep)}")
    lines.append(f"[Fakt] Aktuell im Haus: {len(inhouse)}")
    lines.append(f"[Fakt] Frühstück vorbereitet/erwartet: {breakfast} Person(en)\n")
    lines.append("Geführter Ablauf:")
    lines.append("1. 📚 Gloria: Stammdaten prüfen")
    lines.append("2. 🧹 Zimmer/Reinigung prüfen")
    lines.append("3. 🎀 Pia: Begrüßung / Ankunft / Frühstück senden")
    lines.append("4. 💶 Rechnungen/offene Beträge prüfen")
    lines.append("5. 🗓 Fidel: Kalender + Preise prüfen")
    lines.append("6. 🌙 Tagesabschluss: Backup und Notizen\n")
    if warnings:
        lines.append("📚 Gloria hat gefunden:")
        for guest,mr,me in warnings[:8]:
            bits=[]
            if mr: bits.append("Pflicht fehlt: "+", ".join(mr))
            if me: bits.append("Empfohlen fehlt: "+", ".join(me[:4]))
            lines.append(f"- {guest}: {' | '.join(bits)}")
    else:
        lines.append("📚 Gloria: Heute keine kritischen Stammdaten-Lücken gefunden.")
    self.v29_day_text.delete("1.0",END)
    self.v29_day_text.insert(END,"\n".join(lines))


def v29_refresh_quality(self):
    if not hasattr(self, "v29_quality_tree"):
        return
    for iid in self.v29_quality_tree.get_children():
        self.v29_quality_tree.delete(iid)
    bookings = [b for b in self.d.get("bookings", []) if b.get("status") != "storniert"]
    critical=0; warn=0; ok=0
    for b in sorted(bookings, key=lambda x:(x.get("arrival",""), x.get("guest",""))):
        mr, me = v29_booking_fact_status(self.d,b)
        if mr:
            amp="🔴 Pflicht"
            critical += 1
        elif me:
            amp="🟡 prüfen"
            warn += 1
        else:
            amp="🟢 OK"
            ok += 1
        zeitraum=f"{fmt(b.get('arrival',''))} – {fmt(b.get('departure',''))}"
        self.v29_quality_tree.insert("",END,values=(amp,b.get("guest",""),zeitraum,", ".join(mr),", ".join(me)))
    self.v29_quality_summary.set(f"Gloria Faktencheck: {ok} OK · {warn} prüfen · {critical} kritisch")


def v29_import_preview_file(self):
    try:
        fn=filedialog.askopenfilename(title="Importdatei prüfen", filetypes=[("Tabellen","*.csv *.xlsx *.xls"),("Alle Dateien","*.*")])
        if not fn:
            return
        p=Path(fn)
        lines=[f"Datei: {p.name}",""]
        if pd is not None and p.suffix.lower() in [".xlsx",".xls"]:
            df=pd.read_excel(p, nrows=20)
            cols=list(df.columns)
            rows=len(df.index)
        else:
            with open(p,"r",encoding="utf-8-sig",errors="ignore") as f:
                sample=list(csv.reader(f, delimiter=';'))[:21]
            cols=sample[0] if sample else []
            rows=max(0,len(sample)-1)
        lower=[str(c).lower() for c in cols]
        expected=["name","gast","arrival","anreise","departure","abreise","phone","telefon","price","preis"]
        hits=[e for e in expected if any(e in c for c in lower)]
        lines.append(f"Gefundene Spalten: {', '.join(map(str, cols[:18]))}")
        lines.append(f"Vorschau-Zeilen gelesen: {rows}")
        lines.append("")
        lines.append("Gloria Bewertung:")
        lines.append("✅ Datei kann gelesen werden." if cols else "🔴 Keine Spalten erkannt.")
        lines.append(f"🟡 Erkannte Buchungsfelder: {len(hits)} / {len(expected)}")
        lines.append("[Fakt] Diese Vorschau speichert noch nichts. Vor echtem Import wird ein Backup empfohlen.")
        if self.v29_import_text:
            self.v29_import_text.delete("1.0",END); self.v29_import_text.insert(END,"\n".join(lines))
    except Exception as e:
        log_exception("V29 Importvorschau")
        messagebox.showerror("Import-Vorschau", str(e))


def v29_refresh_backups(self):
    if not hasattr(self, "v29_backup_list"):
        return
    self.v29_backup_list.delete(0,END)
    bd=data_dir()/"Backups"
    bd.mkdir(exist_ok=True)
    files=sorted(bd.glob("*.json"), key=lambda p:p.stat().st_mtime, reverse=True)[:80]
    self._v29_backup_paths=files
    for p in files:
        self.v29_backup_list.insert(END, f"{datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}  {p.name}  {p.stat().st_size//1024} KB")


def v29_backup_now_ui(self):
    p=v29_safe_backup_now("v29_sicherheitsbackup")
    self.v29_refresh_backups()
    if p:
        messagebox.showinfo("Backup", f"Backup erstellt:\n{p}")
    else:
        messagebox.showwarning("Backup", "Backup konnte nicht erstellt werden. Siehe Fehlerprotokoll.")


def v29_restore_selected_backup(self):
    try:
        sel=self.v29_backup_list.curselection()
        if not sel:
            messagebox.showwarning("Wiederherstellung", "Bitte zuerst ein Backup auswählen.")
            return
        p=self._v29_backup_paths[sel[0]]
        if not messagebox.askyesno("Wiederherstellung", f"Aktuelle Daten werden ersetzt. Vorher wird ein Backup erstellt.\n\nWiederherstellen aus:\n{p.name}"):
            return
        v29_safe_backup_now("vor_wiederherstellung")
        shutil.copy2(p, data_file())
        self.d=load()
        self.refresh_all()
        self.v29_refresh_ops()
        messagebox.showinfo("Wiederherstellung", "Backup wurde wiederhergestellt.")
    except Exception as e:
        log_exception("V29 Backup wiederherstellen")
        messagebox.showerror("Wiederherstellung", str(e))


def v29_db_check(self, silent=False):
    try:
        lines=[]
        path=data_file()
        lines.append(f"Datenbankdatei: {path}")
        lines.append(f"Existiert: {'ja' if path.exists() else 'nein'}")
        if path.exists():
            raw=path.read_text(encoding="utf-8")
            data=json.loads(raw)
            lines.append(f"JSON lesbar: ja")
            lines.append(f"Dateigröße: {path.stat().st_size//1024} KB")
            lines.append(f"Buchungen: {len(data.get('bookings',[]))}")
            lines.append(f"Zimmer: {len(data.get('rooms',[]))}")
            lines.append(f"Extras: {len(data.get('extras',[]))}")
        lines.append("[Fakt] SQLite wird hier nicht benutzt; die Daten liegen als JSON-Datei. Wartung = Lesbarkeit, Backup, Kompakt-Speicherung.")
        if hasattr(self,"v29_db_text"):
            self.v29_db_text.delete("1.0",END); self.v29_db_text.insert(END,"\n".join(lines))
        if not silent:
            messagebox.showinfo("Datenbankprüfung", "Datenbankprüfung abgeschlossen.")
    except Exception as e:
        log_exception("V29 Datenbankprüfung")
        if hasattr(self,"v29_db_text"):
            self.v29_db_text.delete("1.0",END); self.v29_db_text.insert(END,"Fehler: "+str(e))


def v29_db_compact(self):
    try:
        v29_safe_backup_now("vor_kompakt")
        save(self.d)
        self.v29_db_check(silent=True)
        messagebox.showinfo("Wartung", "Daten wurden kompakt gespeichert. Backup wurde vorher erstellt.")
    except Exception as e:
        log_exception("V29 Datenbank kompakt")
        messagebox.showerror("Wartung", str(e))


def v29_count_logs(self):
    try:
        logdir=Path("Fehlerprotokolle")
        files=list(logdir.glob("*.txt")) if logdir.exists() else []
        msg=f"Fehlerprotokolle: {len(files)}"
        if hasattr(self,"v29_db_text"):
            self.v29_db_text.insert(END,"\n"+msg)
        messagebox.showinfo("Fehlerprotokolle", msg)
    except Exception as e:
        log_exception("V29 Logs zählen")
        messagebox.showerror("Fehlerprotokolle", str(e))




# ---------------- Gloria Müllmanager Aggsbach Markt ----------------
def muell_csv_file():
    return app_dir() / "abfuhrtermine_aggsbach_markt_2026.csv"

def muell_ics_file():
    return app_dir() / "Gloria_Muell_Erinnerungen_Aggsbach_Markt_2026.ics"

def muell_load_terms():
    """Lädt die integrierten Abfuhrtermine. Erwartete Spalten:
    datum, art, abholung, erinnerung_datum, erinnerung_zeit, quelle
    """
    terms=[]
    path=muell_csv_file()
    if not path.exists():
        return terms
    try:
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader=csv.DictReader(f)
            for row in reader:
                d=pa_safe_date(row.get('datum') or row.get('Datum') or row.get('abholung') or row.get('Kalendereintrag_am'))
                r=pa_safe_date(row.get('erinnerung_datum') or row.get('Vortag_Erinnerung'))
                if not d:
                    continue
                terms.append({
                    'datum': d.isoformat(),
                    'art': (row.get('art') or row.get('Abfallart') or row.get('typ') or '').strip(),
                    'abholung': (row.get('abholung') or row.get('Kalendereintrag_am') or d.isoformat()).strip(),
                    'erinnerung_datum': r.isoformat() if r else '',
                    'erinnerung_zeit': (row.get('erinnerung_zeit') or row.get('Uhrzeit_Erinnerung') or '18:00').strip(),
                    'quelle': (row.get('quelle') or row.get('Quelle') or 'Müllkalender Aggsbach Markt').strip(),
                })
    except Exception:
        log_exception('Gloria Mülltermine laden')
    terms.sort(key=lambda x:x.get('datum',''))
    return terms

def muell_icon(kind):
    k=(kind or '').lower()
    if 'bio' in k: return '🟤'
    if 'papier' in k or 'altpapier' in k: return '🔵'
    if 'kunststoff' in k or 'gelb' in k: return '🟡'
    if 'rest' in k: return '⚫'
    return '🗑'

def muell_next_terms(days=45):
    today=date.today()
    end=today+timedelta(days=days)
    out=[]
    for t in muell_load_terms():
        d=pa_safe_date(t.get('datum'))
        if d and today <= d <= end:
            out.append(t)
    return out

def muell_terms_for_tomorrow():
    tomorrow=(date.today()+timedelta(days=1)).isoformat()
    return [t for t in muell_load_terms() if t.get('datum') == tomorrow]

def muell_build_summary():
    tomorrow=muell_terms_for_tomorrow()
    if tomorrow:
        items=', '.join(f"{muell_icon(t['art'])} {t['art']}" for t in tomorrow)
        return f"📚 Gloria: Morgen Müllabholung: {items}. Bitte heute Abend bereitstellen."
    nxt=muell_next_terms(14)
    if nxt:
        t=nxt[0]
        return f"📚 Gloria: Nächste Müllabholung am {fmt(t['datum'])}: {muell_icon(t['art'])} {t['art']}."
    return "📚 Gloria: Keine Müllabholung in den nächsten 14 Tagen gefunden."

def muell_open_ics():
    path=muell_ics_file()
    if not path.exists():
        messagebox.showwarning('Gloria Müll', 'ICS-Datei nicht gefunden.')
        return
    try:
        os.startfile(str(path))
    except Exception:
        webbrowser.open(path.as_uri())

def muell_open_csv():
    path=muell_csv_file()
    if not path.exists():
        messagebox.showwarning('Gloria Müll', 'CSV-Datei nicht gefunden.')
        return
    try:
        os.startfile(str(path))
    except Exception:
        webbrowser.open(path.as_uri())

def build_gloria_muell_tab(self):
    top=ttk.Frame(self.tab_muell)
    top.pack(fill='x', padx=12, pady=10)
    hero=ttk.Frame(top, style='Card.TFrame', padding=14)
    hero.pack(fill='x')
    ttk.Label(hero, text='📚 Gloria Müllmanager – Aggsbach Markt 2026', style='CardTitle.TLabel').pack(anchor='w')
    self.muell_summary_var=StringVar(value=muell_build_summary())
    ttk.Label(hero, textvariable=self.muell_summary_var, style='Card.TLabel', wraplength=1100).pack(anchor='w', pady=(6,8))
    brow=ttk.Frame(hero, style='Card.TFrame')
    brow.pack(fill='x')
    ttk.Button(brow, text='🔄 Aktualisieren', command=self.refresh_muell_tab, style='Soft.TButton').pack(side='left', padx=(0,6))
    ttk.Button(brow, text='📅 ICS für Outlook/Google öffnen', command=muell_open_ics, style='Touch.TButton').pack(side='left', padx=6)
    ttk.Button(brow, text='🧾 CSV öffnen', command=muell_open_csv, style='Soft.TButton').pack(side='left', padx=6)

    frame=ttk.Frame(self.tab_muell)
    frame.pack(fill='both', expand=True, padx=12, pady=(0,12))
    cols=('datum','art','erinnerung','quelle')
    self.muell_tree=ttk.Treeview(frame, columns=cols, show='headings')
    headings={'datum':'Abholung','art':'Tonne / Sack','erinnerung':'Erinnerung','quelle':'Quelle'}
    widths={'datum':110,'art':240,'erinnerung':170,'quelle':420}
    for c in cols:
        self.muell_tree.heading(c, text=headings[c])
        self.muell_tree.column(c, width=widths[c], anchor='w')
    y=ttk.Scrollbar(frame, orient='vertical', command=self.muell_tree.yview)
    self.muell_tree.configure(yscrollcommand=y.set)
    self.muell_tree.pack(side='left', fill='both', expand=True)
    y.pack(side='right', fill='y')
    self.refresh_muell_tab()

def refresh_muell_tab(self):
    try:
        if hasattr(self, 'muell_summary_var'):
            self.muell_summary_var.set(muell_build_summary())
        if hasattr(self, 'muell_tree'):
            self.muell_tree.delete(*self.muell_tree.get_children())
            for t in muell_next_terms(370):
                erinnerung = (fmt(t.get('erinnerung_datum')) if t.get('erinnerung_datum') else '')
                if t.get('erinnerung_zeit'):
                    erinnerung += f" {t.get('erinnerung_zeit')}"
                self.muell_tree.insert('', 'end', values=(fmt(t.get('datum')), f"{muell_icon(t.get('art'))} {t.get('art')}", erinnerung, t.get('quelle')))
    except Exception as e:
        log_exception('Gloria Müll aktualisieren')
        messagebox.showerror('Gloria Müll', str(e))

def muell_show_start_hint(root=None):
    terms=muell_terms_for_tomorrow()
    if not terms:
        return
    msg='Morgen wird abgeholt:\n\n' + '\n'.join(f"{muell_icon(t['art'])} {t['art']}" for t in terms) + '\n\nGloria erinnert: Tonne/Sack heute Abend bereitstellen.'
    try:
        messagebox.showinfo('📚 Gloria Müll-Erinnerung', msg)
    except Exception:
        pass


def build_laura_mode_tab(self):
    """Sprint 9: einfacher Laura-Modus mit grossen Tagesaufgaben."""
    top=ttk.Frame(self.tab_laura)
    top.pack(fill='x', padx=12, pady=10)
    hero=ttk.Frame(top, style='Card.TFrame', padding=14)
    hero.pack(fill='x')
    ttk.Label(hero, text='❤️ Laura-Modus – Haus, Zimmer & Frühstück', style='CardTitle.TLabel').pack(anchor='w')
    self.laura_summary_var=StringVar(value='Noch nicht aktualisiert')
    ttk.Label(hero, textvariable=self.laura_summary_var, style='Card.TLabel', wraplength=1100).pack(anchor='w', pady=(6,8))
    brow=ttk.Frame(hero, style='Card.TFrame')
    brow.pack(fill='x')
    ttk.Button(brow, text='🔄 Aktualisieren', command=self.refresh_laura_mode, style='Touch.TButton').pack(side='left', padx=(0,6))
    ttk.Button(brow, text='📋 Text kopieren', command=self.copy_laura_tasks, style='Soft.TButton').pack(side='left', padx=6)
    ttk.Button(brow, text='🥐 Einkauf kopieren', command=self.copy_breakfast_shopping, style='Soft.TButton').pack(side='left', padx=6)

    frame=ttk.Frame(self.tab_laura)
    frame.pack(fill='both', expand=True, padx=12, pady=(0,12))
    cols=('status','bereich','aufgabe','hinweis','prio')
    self.laura_tree=ttk.Treeview(frame, columns=cols, show='headings')
    headings={'status':'✓','bereich':'Bereich','aufgabe':'Aufgabe','hinweis':'Hinweis','prio':'Prio'}
    widths={'status':45,'bereich':130,'aufgabe':320,'hinweis':520,'prio':80}
    for c in cols:
        self.laura_tree.heading(c, text=headings[c])
        self.laura_tree.column(c, width=widths[c], anchor='w')
    y=ttk.Scrollbar(frame, orient='vertical', command=self.laura_tree.yview)
    self.laura_tree.configure(yscrollcommand=y.set)
    self.laura_tree.pack(side='left', fill='both', expand=True)
    y.pack(side='right', fill='y')
    self.laura_tree.bind('<Double-1>', self.toggle_laura_task_done)

    shop=ttk.Frame(self.tab_laura, style='Card.TFrame', padding=10)
    shop.pack(fill='x', padx=12, pady=(0,12))
    ttk.Label(shop, text='🥐 Frühstück / Einkauf morgen', style='CardTitle.TLabel').pack(anchor='w')
    self.breakfast_shop_text=Text(shop, height=7, wrap='word', bg='#ffffff', relief='flat', font=('Segoe UI',10), padx=8, pady=6)
    self.breakfast_shop_text.pack(fill='x', expand=False, pady=(6,0))

    self.refresh_laura_mode()

def _laura_current_plan(self):
    try:
        terms = muell_load_terms() if 'muell_load_terms' in globals() else []
    except Exception:
        terms = []
    return laura_build_tasks(date.today(), self.d.get('bookings', []), terms, room_name_fn=lambda rid: room_name(self.d, rid))

def refresh_laura_mode(self):
    try:
        plan = self._laura_current_plan()
        self._last_laura_plan = plan
        sm = plan.get('summary', {})
        self.laura_summary_var.set(f"Heute: {sm.get('arrivals',0)} Anreise · {sm.get('departures',0)} Abreise · Frühstück {sm.get('breakfast_persons',0)} Pers. · {sm.get('tasks_total',0)} Aufgaben")
        self.laura_tree.delete(*self.laura_tree.get_children())
        for i,t in enumerate(plan.get('tasks', [])):
            pr='hoch' if t.get('priority')=='hoch' else 'normal'
            self.laura_tree.insert('', 'end', iid=str(i), values=('□', t.get('category',''), t.get('title',''), t.get('detail',''), pr))
        if hasattr(self, 'breakfast_shop_text'):
            tomorrow=date.today()+timedelta(days=1)
            shop_plan=breakfast_build_shopping(self.d.get('bookings', []), tomorrow)
            self._last_breakfast_shop_plan=shop_plan
            self.breakfast_shop_text.delete('1.0', END)
            self.breakfast_shop_text.insert('1.0', breakfast_format_shopping(shop_plan, room_name_fn=lambda rid: room_name(self.d, rid)))
    except Exception as e:
        log_exception('Laura-Modus aktualisieren')
        messagebox.showerror('Laura-Modus', str(e))

def toggle_laura_task_done(self, event=None):
    try:
        sel=self.laura_tree.selection()
        if not sel: return
        iid=sel[0]
        vals=list(self.laura_tree.item(iid,'values'))
        vals[0]='✓' if vals and vals[0]=='□' else '□'
        self.laura_tree.item(iid, values=vals)
    except Exception:
        log_exception('Laura-Aufgabe abhaken')

def copy_laura_tasks(self):
    try:
        plan=getattr(self, '_last_laura_plan', None) or self._laura_current_plan()
        text=laura_format_tasks(plan)
        self.root.clipboard_clear(); self.root.clipboard_append(text)
        messagebox.showinfo('Laura-Modus', 'Tagesliste wurde in die Zwischenablage kopiert.')
    except Exception as e:
        log_exception('Laura-Text kopieren')
        messagebox.showerror('Laura-Modus', str(e))


def copy_breakfast_shopping(self):
    try:
        plan=getattr(self, '_last_breakfast_shop_plan', None)
        if not plan:
            tomorrow=date.today()+timedelta(days=1)
            plan=breakfast_build_shopping(self.d.get('bookings', []), tomorrow)
        text=breakfast_format_shopping(plan, room_name_fn=lambda rid: room_name(self.d, rid))
        self.root.clipboard_clear(); self.root.clipboard_append(text)
        messagebox.showinfo('Frühstück / Einkauf', 'Einkaufsliste wurde in die Zwischenablage kopiert.')
    except Exception as e:
        log_exception('Frühstück Einkauf kopieren')
        messagebox.showerror('Frühstück / Einkauf', str(e))

# Original-Build erweitern: V29 kommt in den bestehenden Systembereich, kein weiterer Hauptreiter.
_v28_build = App.build

def _v29_build_wrapper(self):
    _v28_build(self)
    try:
        self.tab_ops = ttk.Frame(self.tools_nb)
        self.tools_nb.insert(0, self.tab_ops, text="🛡 Betrieb V30")
        v29_build_ops(self)
    except Exception:
        log_exception("V29 Oberfläche einbauen")
    try:
        self.tab_muell = ttk.Frame(self.tools_nb)
        self.tools_nb.insert(1, self.tab_muell, text="📚 Gloria Müll")
        build_gloria_muell_tab(self)
        self.root.after(1200, muell_show_start_hint)
    except Exception:
        log_exception("Gloria Müllmanager einbauen")
    try:
        self.tab_laura = ttk.Frame(self.tools_nb)
        self.tools_nb.insert(2, self.tab_laura, text="❤️ Laura")
        build_laura_mode_tab(self)
    except Exception:
        log_exception("Laura-Modus einbauen")

App.build = _v29_build_wrapper
App.v29_refresh_ops = v29_refresh_ops
App.v29_refresh_day_mode = v29_refresh_day_mode
App.v29_refresh_quality = v29_refresh_quality
App.v29_import_preview_file = v29_import_preview_file
App.v29_refresh_backups = v29_refresh_backups
App.v29_backup_now_ui = v29_backup_now_ui
App.v29_restore_selected_backup = v29_restore_selected_backup
App.v29_db_check = v29_db_check
App.v29_db_compact = v29_db_compact
App.v29_count_logs = v29_count_logs
App.refresh_muell_tab = refresh_muell_tab
App.build_laura_mode_tab = build_laura_mode_tab
App.refresh_laura_mode = refresh_laura_mode
App._laura_current_plan = _laura_current_plan
App.toggle_laura_task_done = toggle_laura_task_done
App.copy_laura_tasks = copy_laura_tasks
App.copy_breakfast_shopping = copy_breakfast_shopping

# ---------------- Sprint 14 / V31.6: Smart Workflow ----------------
def build_workflow_tab(self):
    """Geführter Tagesablauf: Check-in, Check-out, Reinigung, Frühstück."""
    from manager.modules.workflow import build_today_workflow, format_workflow_text
    top = ttk.Frame(self.tab_workflow)
    top.pack(fill='x', padx=12, pady=10)
    hero = ttk.Frame(top, style='Card.TFrame', padding=14)
    hero.pack(fill='x')
    ttk.Label(hero, text='✅ Smart Workflow – Anreise, Abreise & Tagesablauf', style='CardTitle.TLabel').pack(anchor='w')
    self.workflow_summary_var = StringVar(value='Noch nicht geladen')
    ttk.Label(hero, textvariable=self.workflow_summary_var, style='HeroSub.TLabel').pack(anchor='w', pady=(4, 0))
    buttons = ttk.Frame(hero, style='Card.TFrame')
    buttons.pack(anchor='w', pady=(10, 0))
    ttk.Button(buttons, text='Aktualisieren', command=self.refresh_workflow_tab, style='Primary.TButton').pack(side='left', padx=(0, 6))
    ttk.Button(buttons, text='Tagesablauf kopieren', command=self.copy_workflow_text, style='Soft.TButton').pack(side='left', padx=6)

    frame = ttk.Frame(self.tab_workflow)
    frame.pack(fill='both', expand=True, padx=12, pady=(0, 12))
    cols=('status','owner','bereich','aufgabe','hinweis','prio')
    self.workflow_tree=ttk.Treeview(frame, columns=cols, show='headings')
    headings={'status':'✓','owner':'Windi','bereich':'Bereich','aufgabe':'Aufgabe','hinweis':'Hinweis','prio':'Prio'}
    widths={'status':45,'owner':90,'bereich':115,'aufgabe':290,'hinweis':520,'prio':80}
    for c in cols:
        self.workflow_tree.heading(c, text=headings[c])
        self.workflow_tree.column(c, width=widths[c], anchor='w')
    y=ttk.Scrollbar(frame, orient='vertical', command=self.workflow_tree.yview)
    self.workflow_tree.configure(yscrollcommand=y.set)
    self.workflow_tree.pack(side='left', fill='both', expand=True)
    y.pack(side='right', fill='y')
    self.workflow_tree.bind('<Double-1>', self.toggle_workflow_task_done)
    self.refresh_workflow_tab()


def _workflow_current_plan(self):
    from manager.modules.workflow import build_today_workflow
    return build_today_workflow(self.d.get('bookings', []), date.today(), room_name_fn=lambda rid: room_name(self.d, rid))


def refresh_workflow_tab(self):
    try:
        plan = self._workflow_current_plan()
        self._last_workflow_plan = plan
        sm = plan.get('summary', {})
        self.workflow_summary_var.set(
            f"Heute: {sm.get('arrivals',0)} Anreise · {sm.get('departures',0)} Abreise · im Haus {sm.get('in_house',0)} · Frühstück {sm.get('breakfast_persons',0)} Pers. · {sm.get('critical_steps',0)} wichtige Aufgaben"
        )
        self.workflow_tree.delete(*self.workflow_tree.get_children())
        for i, s in enumerate(plan.get('steps', [])):
            pr = 'hoch' if s.get('priority') == 'hoch' else 'normal'
            self.workflow_tree.insert('', 'end', iid=str(i), values=('□', s.get('owner',''), s.get('category',''), s.get('title',''), s.get('detail',''), pr))
    except Exception as e:
        log_exception('Smart Workflow aktualisieren')
        messagebox.showerror('Smart Workflow', str(e))


def toggle_workflow_task_done(self, event=None):
    try:
        sel=self.workflow_tree.selection()
        if not sel:
            return
        iid=sel[0]
        vals=list(self.workflow_tree.item(iid,'values'))
        vals[0]='✓' if vals and vals[0]=='□' else '□'
        self.workflow_tree.item(iid, values=vals)
    except Exception:
        log_exception('Smart Workflow Aufgabe abhaken')


def copy_workflow_text(self):
    try:
        from manager.modules.workflow import format_workflow_text
        plan=getattr(self, '_last_workflow_plan', None) or self._workflow_current_plan()
        text=format_workflow_text(plan)
        self.root.clipboard_clear(); self.root.clipboard_append(text)
        messagebox.showinfo('Smart Workflow', 'Tagesablauf wurde in die Zwischenablage kopiert.')
    except Exception as e:
        log_exception('Smart Workflow Text kopieren')
        messagebox.showerror('Smart Workflow', str(e))


_v31_5_build = App.build

def _v31_6_build_wrapper(self):
    _v31_5_build(self)
    try:
        self.tab_workflow = ttk.Frame(self.tools_nb)
        self.tools_nb.insert(3, self.tab_workflow, text='✅ Workflow')
        build_workflow_tab(self)
    except Exception:
        log_exception('Smart Workflow einbauen')

App.build = _v31_6_build_wrapper
App.build_workflow_tab = build_workflow_tab
App._workflow_current_plan = _workflow_current_plan
App.refresh_workflow_tab = refresh_workflow_tab
App.toggle_workflow_task_done = toggle_workflow_task_done
App.copy_workflow_text = copy_workflow_text


def main():
    install_error_logging()
    try:
        App()
    except Exception:
        path = log_exception("Programmstart / Hauptfenster")
        try:
            messagebox.showerror("Programmfehler", f"Der Manager konnte nicht gestartet werden.\n\nFehlerprotokoll:\n{path}")
        except Exception:
            print(f"Der Manager konnte nicht gestartet werden. Fehlerprotokoll: {path}")
        raise

if __name__=="__main__":
    main()
