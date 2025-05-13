from flask import Flask, render_template, jsonify
from dotenv import load_dotenv
import os
import requests
import mysql.connector
from datetime import datetime, date, timezone

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

SOURCE_API_NAME = "ExchangeRateAPI.com"

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
        print(f"Eroare la parsarea datei API '{api_datetime_str}': {e}")
        try:
            dt_object_utc_naive = datetime.strptime(api_datetime_str[:-6], '%a, %d %b %Y %H:%M:%S')
            return dt_object_utc_naive
        except ValueError:
            return None

def get_rates_from_db(query_date_obj, base_curr, source_api=SOURCE_API_NAME):
    conn = get_db_connection()
    if not conn:
        return None
    
    cursor = conn.cursor(dictionary=True)
    rates_data = None
    
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
            
            if source_dt_obj_utc_naive:
                source_dt_obj_utc_aware = source_dt_obj_utc_naive.replace(tzinfo=timezone.utc)
                base_time_str = source_dt_obj_utc_aware.strftime('%a, %d %b %Y %H:%M:%S')
                offset_seconds = source_dt_obj_utc_aware.utcoffset().total_seconds()
                offset_sign = "+" if offset_seconds >= 0 else "-"
                offset_hours = int(abs(offset_seconds / 3600))
                offset_minutes = int(abs(offset_seconds / 60)) % 60
                formatted_offset_str = f"{offset_sign}{offset_hours:02d}:{offset_minutes:02d}"
                last_update_str = f"{base_time_str} {formatted_offset_str}"
            else:
                last_update_str = "N/A"

            rates_data = {
                "base_code": rows[0]['base_currency_code'],
                "rates": rates,
                "last_update": last_update_str
            }
    except mysql.connector.Error as err:
        print(f"Eroare la citirea din BD: {err}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            
    return rates_data

def insert_rates_into_db(base_code, rates_dict, api_last_update_str, source_api=SOURCE_API_NAME):
    conn = get_db_connection()
    if not conn:
        return False

    cursor = conn.cursor()
    success = False
    
    source_datetime_db_format = parse_api_datetime_to_db_format(api_last_update_str)
    if not source_datetime_db_format:
        print(f"Nu s-a putut parsa api_last_update_str: {api_last_update_str}")
        if conn.is_connected(): conn.close()
        return False
        
    rate_date_db_format = source_datetime_db_format.date()

    insert_query = """
        INSERT IGNORE INTO daily_exchange_rates 
        (rate_date, base_currency_code, target_currency_code, rate_value, source_api_name, source_last_updated_utc)
        VALUES (%s, %s, %s, %s, %s, %s)
    """

    try:
        conn.start_transaction()
        for target_code, rate_value in rates_dict.items():
            cursor.execute(insert_query, (
                rate_date_db_format,
                base_code,
                target_code,
                float(rate_value),
                source_api,
                source_datetime_db_format
            ))
        conn.commit()
        print(f"Ratele pentru {base_code} din {rate_date_db_format} inserate/ignorate cu succes.")
        success = True
    except mysql.connector.Error as err:
        print(f"Eroare la inserarea în BD: {err}")
        conn.rollback()
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
    return success

@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/get-exchange-rates')
def get_exchange_rates_route():
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        return jsonify({"error": "Configurația bazei de date este incompletă pe server."}), 500

    today_utc = datetime.now(timezone.utc).date()
    base_currency_to_fetch = "USD"

    print(f"Se caută rate în BD pentru data: {today_utc}, moneda de bază: {base_currency_to_fetch}")
    rates_from_db = get_rates_from_db(today_utc, base_currency_to_fetch)

    if rates_from_db:
        print("Rate găsite în BD. Se returnează din BD.")
        return jsonify(rates_from_db)
    else:
        print(f"Ratele pentru {today_utc} nu sunt în BD. Se apelează API-ul extern.")
        if not EXCHANGE_RATE_API_KEY:
            return jsonify({"error": "API Key pentru serviciul de rate de schimb nu este configurat pe server."}), 500

        api_url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/latest/{base_currency_to_fetch}"
        
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            api_data = response.json()
            
            if api_data.get("result") == "success":
                print("Date primite cu succes de la API-ul extern.")
                base_c = api_data.get("base_code")
                conversion_r = api_data.get("conversion_rates")
                time_last_update_utc_str = api_data.get("time_last_update_utc")

                api_dt_obj = parse_api_datetime_to_db_format(time_last_update_utc_str)
                if api_dt_obj and api_dt_obj.date() == today_utc:
                    insert_rates_into_db(base_c, conversion_r, time_last_update_utc_str)
                else:
                    api_date_for_print = api_dt_obj.date() if api_dt_obj else 'N/A'
                    print(f"Data din API ({api_date_for_print}) nu corespunde cu ziua curentă UTC ({today_utc}). Ratele nu vor fi stocate.")
                
                return jsonify({
                    "base_code": base_c,
                    "rates": conversion_r,
                    "last_update": time_last_update_utc_str
                })
            else:
                error_type = api_data.get("error-type", "Eroare necunoscută API extern")
                print(f"Eroare de la API-ul extern: {error_type}")
                return jsonify({"error": f"Eroare API extern: {error_type}", "details": api_data}), 500

        except requests.exceptions.HTTPError as http_err:
            print(f"Eroare HTTP: {http_err}")
            return jsonify({"error": f"Eroare HTTP: {http_err}", "url_called": api_url}), 500
        except requests.exceptions.RequestException as req_err:
            print(f"Eroare Request: {req_err}")
            return jsonify({"error": f"Eroare la request către API-ul extern: {req_err}", "url_called": api_url}), 500
        except ValueError as json_err:
            print(f"Eroare decodare JSON: {json_err}")
            return jsonify({"error": f"Eroare la decodarea răspunsului JSON de la API-ul extern: {json_err}"}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)