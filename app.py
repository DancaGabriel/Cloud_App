from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import os
import requests
import mysql.connector
from datetime import datetime, date, timezone, timedelta

load_dotenv()

app = Flask(__name__)

EXCHANGE_RATE_API_KEY = os.getenv('EXCHANGE_RATE_API_KEY')
if not EXCHANGE_RATE_API_KEY:
    print("Eroare: Variabila de mediu EXCHANGE_RATE_API_KEY nu este setată!")

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
    print("Eroare: Una sau mai multe variabile de mediu pentru baza de date nu sunt setate (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)!")

# Definim constante pentru numele surselor API
SOURCE_EXCHANGERATE_API = "ExchangeRateAPI.com"
SOURCE_FRANKFURTER_APP = "Frankfurter.app"


def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Eroare la conectarea la MySQL: {err}")
        return None

def parse_api_datetime_to_db_format(api_datetime_str):
    try:
        dt_object_aware = datetime.strptime(api_datetime_str, '%a, %d %b %Y %H:%M:%S %z')
        dt_object_utc_naive = dt_object_aware.astimezone(timezone.utc).replace(tzinfo=None)
        return dt_object_utc_naive
    except ValueError as e:
        # Acest fallback este mai puțin probabil să fie necesar dacă construim corect string-ul pentru Frankfurter
        print(f"Eroare la parsarea datei API '{api_datetime_str}': {e}")
        try:
            dt_object_utc_naive = datetime.strptime(api_datetime_str[:-6], '%a, %d %b %Y %H:%M:%S')
            return dt_object_utc_naive
        except ValueError:
            return None

# Funcția get_rates_from_db rămâne neschimbată în logica sa internă,
# dar va fi apelată cu source_api diferit
def get_rates_from_db(query_date_obj, base_curr, source_api):
    conn = get_db_connection()
    if not conn:
        return None
    
    cursor = conn.cursor(dictionary=True)
    rates_data_from_db = None
    
    try:
        query = """
            SELECT base_currency_code, target_currency_code, rate_value, source_last_updated_utc
            FROM daily_exchange_rates
            WHERE rate_date = %s AND base_currency_code = %s AND source_api_name = %s
        """
        cursor.execute(query, (query_date_obj, base_curr, source_api))
        rows = cursor.fetchall()
        
        if rows:
            rates = {row['target_currency_code']: float(row['rate_value']) for row in rows}
            source_dt_obj_utc_naive = rows[0]['source_last_updated_utc']
            last_update_str = "N/A"
            if source_dt_obj_utc_naive:
                source_dt_obj_utc_aware = source_dt_obj_utc_naive.replace(tzinfo=timezone.utc)
                base_time_str = source_dt_obj_utc_aware.strftime('%a, %d %b %Y %H:%M:%S')
                offset_seconds = source_dt_obj_utc_aware.utcoffset().total_seconds()
                offset_sign = "+" if offset_seconds >= 0 else "-"
                offset_hours = int(abs(offset_seconds / 3600))
                offset_minutes = int(abs(offset_seconds / 60)) % 60
                formatted_offset_str = f"{offset_sign}{offset_hours:02d}:{offset_minutes:02d}"
                last_update_str = f"{base_time_str} {formatted_offset_str}"

            rates_data_from_db = {
                "base_code": rows[0]['base_currency_code'],
                "rates": rates,
                "last_update": last_update_str
            }
    except mysql.connector.Error as err:
        print(f"Eroare la citirea din BD ({source_api}): {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            
    return rates_data_from_db

# Funcția insert_rates_into_db rămâne neschimbată în logica sa internă,
# dar va fi apelată cu source_api diferit
def insert_rates_into_db(base_code, rates_dict, effective_date_obj, source_last_update_utc_str, source_api):
    conn = get_db_connection()
    if not conn:
        return False

    cursor = conn.cursor()
    success = False
    
    source_datetime_db_format = parse_api_datetime_to_db_format(source_last_update_utc_str)
    if not source_datetime_db_format:
        print(f"Nu s-a putut parsa source_last_update_utc_str: {source_last_update_utc_str} pentru inserare (sursa: {source_api}).")
        if conn and conn.is_connected(): conn.close()
        return False
        
    insert_query = """
        INSERT IGNORE INTO daily_exchange_rates 
        (rate_date, base_currency_code, target_currency_code, rate_value, source_api_name, source_last_updated_utc)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    try:
        conn.start_transaction()
        for target_code, rate_value in rates_dict.items():
            cursor.execute(insert_query, (
                effective_date_obj,
                base_code,
                target_code,
                float(rate_value),
                source_api,
                source_datetime_db_format
            ))
        conn.commit()
        print(f"Ratele pentru {base_code} din {effective_date_obj} (sursa: {source_api}) inserate/ignorate cu succes.")
        success = True
    except mysql.connector.Error as err:
        print(f"Eroare la inserarea în BD ({source_api}): {err}")
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    return success

@app.route('/')
def hello_world():
     current_year = datetime.now().year
     return render_template('index.html', year=current_year)

@app.route('/get-exchange-rates')
def get_exchange_rates_route():
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        return jsonify({"error": "Configurația bazei de date este incompletă pe server."}), 500

    today_utc_date = datetime.now(timezone.utc).date()
    base_currency_to_fetch = "USD" # Moneda de bază implicită pentru API-ul curent
    
    print(f"Se caută rate în BD pentru data: {today_utc_date}, moneda de bază: {base_currency_to_fetch}, sursa: {SOURCE_EXCHANGERATE_API}")
    rates_from_db = get_rates_from_db(today_utc_date, base_currency_to_fetch, SOURCE_EXCHANGERATE_API)
    data_to_return = {}

    if rates_from_db:
        print(f"Rate ({SOURCE_EXCHANGERATE_API}) găsite în BD. Se returnează din BD.")
        data_to_return = rates_from_db
        data_to_return['data_source'] = "baza de date (cache local)"
        return jsonify(data_to_return)
    else:
        print(f"Ratele pentru {today_utc_date} ({SOURCE_EXCHANGERATE_API}) nu sunt în BD. Se apelează API-ul extern.")
        if not EXCHANGE_RATE_API_KEY:
            return jsonify({"error": f"API Key pentru {SOURCE_EXCHANGERATE_API} nu este configurat.", "data_source": "config_error"}), 500

        api_url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/latest/{base_currency_to_fetch}"
        print(f"Se apelează: {api_url}")
        
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            api_data = response.json()
            
            if api_data.get("result") == "success":
                print(f"Date primite cu succes de la {SOURCE_EXCHANGERATE_API}.")
                base_c = api_data.get("base_code")
                conversion_r = api_data.get("conversion_rates")
                time_last_update_utc_str = api_data.get("time_last_update_utc")

                api_dt_obj = parse_api_datetime_to_db_format(time_last_update_utc_str)
                if api_dt_obj and api_dt_obj.date() == today_utc_date:
                    insert_rates_into_db(base_c, conversion_r, today_utc_date, time_last_update_utc_str, SOURCE_EXCHANGERATE_API)
                else:
                    api_date_for_print = api_dt_obj.date() if api_dt_obj else 'N/A'
                    print(f"Data din API ({SOURCE_EXCHANGERATE_API}: {api_date_for_print}) nu corespunde cu ziua curentă UTC ({today_utc_date}). Ratele nu vor fi stocate.")
                
                data_to_return = {
                    "base_code": base_c,
                    "rates": conversion_r,
                    "last_update": time_last_update_utc_str,
                    "data_source": f"{SOURCE_EXCHANGERATE_API} (extern)"
                }
                return jsonify(data_to_return)
            else:
                error_type = api_data.get("error-type", f"Eroare necunoscută API ({SOURCE_EXCHANGERATE_API})")
                print(f"Eroare de la API-ul extern ({SOURCE_EXCHANGERATE_API}): {error_type}")
                return jsonify({"error": f"Eroare API extern ({SOURCE_EXCHANGERATE_API}): {error_type}", "details": api_data, "data_source": "api_error"}), 500
        except requests.exceptions.HTTPError as http_err:
            print(f"Eroare HTTP ({SOURCE_EXCHANGERATE_API}): {http_err}")
            return jsonify({"error": f"Eroare HTTP ({SOURCE_EXCHANGERATE_API}): {http_err}", "url_called": api_url, "data_source": "request_error"}), 500
        except requests.exceptions.RequestException as req_err:
            print(f"Eroare Request ({SOURCE_EXCHANGERATE_API}): {req_err}")
            return jsonify({"error": f"Eroare la request către API-ul extern ({SOURCE_EXCHANGERATE_API}): {req_err}", "url_called": api_url, "data_source": "request_error"}), 500
        except ValueError as json_err:
            print(f"Eroare decodare JSON ({SOURCE_EXCHANGERATE_API}): {json_err}")
            return jsonify({"error": f"Eroare la decodarea răspunsului JSON de la API-ul extern ({SOURCE_EXCHANGERATE_API}): {json_err}", "data_source": "request_error"}), 500

@app.route('/get-frankfurter-historical-rates')
def get_frankfurter_historical_rates_route():
    selected_date_str = request.args.get('date')
    base_currency_frankfurter = request.args.get('base', 'USD').upper() # Monedă de bază pentru Frankfurter

    if not selected_date_str:
        return jsonify({"error": "Parametrul 'date' (YYYY-MM-DD) este necesar.", "data_source": "user_error"}), 400
    
    try:
        frank_date_obj = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        min_date = date(1999, 1, 4)
        max_date = datetime.now(timezone.utc).date() - timedelta(days=1) 

        if not (min_date <= frank_date_obj <= max_date):
            return jsonify({"error": f"Data trebuie să fie între {min_date.strftime('%Y-%m-%d')} și {max_date.strftime('%Y-%m-%d')}.", "data_source": "user_error"}), 400
    except ValueError:
        return jsonify({"error": "Format dată invalid. Folosește YYYY-MM-DD.", "data_source": "user_error"}), 400

    # --- ADAUGAT: Verifică întâi în BD pentru datele Frankfurter ---
    print(f"Se caută rate în BD pentru data: {frank_date_obj}, moneda de bază: {base_currency_frankfurter}, sursa: {SOURCE_FRANKFURTER_APP}")
    rates_from_db = get_rates_from_db(frank_date_obj, base_currency_frankfurter, SOURCE_FRANKFURTER_APP)
    
    if rates_from_db:
        print(f"Rate ({SOURCE_FRANKFURTER_APP}) găsite în BD pentru {frank_date_obj}. Se returnează din BD.")
        data_to_return = rates_from_db
        data_to_return['data_source'] = f"baza de date (cache local - {SOURCE_FRANKFURTER_APP})"
        return jsonify(data_to_return)
    # --- SFÂRȘIT BLOC VERIFICARE BD ---

    print(f"Ratele pentru {frank_date_obj} ({SOURCE_FRANKFURTER_APP}) nu sunt în BD. Se apelează API-ul extern.")
    api_url = f"https://api.frankfurter.app/{selected_date_str}?base={base_currency_frankfurter}"
    print(f"Se apelează Frankfurter API: {api_url}")

    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        frank_data = response.json()

        # Construim un câmp "last_update" și un string pentru source_last_update_utc pentru BD
        hist_dt_aware = datetime(frank_date_obj.year, frank_date_obj.month, frank_date_obj.day, 0, 0, 0, tzinfo=timezone.utc)
        base_time_str = hist_dt_aware.strftime('%a, %d %b %Y %H:%M:%S')
        formatted_offset_str = "+00:00" 
        last_update_for_frontend_and_db = f"{base_time_str} {formatted_offset_str}"
        
        # Extragem datele necesare pentru inserare și răspuns
        base_c = frank_data.get("base")
        conversion_r = frank_data.get("rates")

        # --- ADAUGAT: Inserează datele Frankfurter în BD ---
        if base_c and conversion_r: # Verificăm dacă avem date valide de la API
            insert_rates_into_db(base_c, conversion_r, frank_date_obj, last_update_for_frontend_and_db, SOURCE_FRANKFURTER_APP)
        else:
            print(f"Răspuns incomplet de la Frankfurter API pentru {selected_date_str}. Nu se inserează în BD.")
        # --- SFÂRȘIT BLOC INSERARE BD ---
        
        data_to_return = {
            "base_code": base_c,
            "rates": conversion_r,
            "last_update": last_update_for_frontend_and_db,
            "data_source": f"{SOURCE_FRANKFURTER_APP} ({frank_data.get('date')}, extern)"
        }
        return jsonify(data_to_return)

    except requests.exceptions.HTTPError as http_err:
        print(f"Eroare HTTP (Frankfurter): {http_err}")
        error_details = None
        try:
            error_details = response.json()
        except ValueError:
            pass 
        return jsonify({"error": f"Eroare HTTP de la Frankfurter: {http_err.response.status_code if http_err.response else 'N/A'}", "details": error_details, "url_called": api_url, "data_source": "frankfurter_api_error"}), 500
    except requests.exceptions.RequestException as req_err:
        print(f"Eroare Request (Frankfurter): {req_err}")
        return jsonify({"error": f"Eroare la request către Frankfurter: {req_err}", "url_called": api_url, "data_source": "frankfurter_request_error"}), 500
    except ValueError as json_err: 
        print(f"Eroare decodare JSON (Frankfurter): {json_err}")
        return jsonify({"error": f"Eroare la decodarea răspunsului JSON de la Frankfurter: {json_err}", "data_source": "frankfurter_request_error"}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)