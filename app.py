from flask import Flask, render_template, jsonify
from dotenv import load_dotenv
import os
import requests 

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv('EXCHANGE_RATE_API_KEY')
if not API_KEY:
    print("Eroare: Variabila de mediu EXCHANGE_RATE_API_KEY nu este setată sau nu este accesibilă!")


@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/get-exchange-rates')
def get_exchange_rates():
    if not API_KEY:
        return jsonify({"error": "API Key for exchange rate service is not configured."}), 500

    base_currency = "USD"
    api_url = f"https://v6.exchangerate-api.com/v6/{API_KEY}/latest/{base_currency}"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status() 
        data = response.json()
        
        if data.get("result") == "success":
            return jsonify({
                "base_code": data.get("base_code"),
                "rates": data.get("conversion_rates"),
                "last_update": data.get("time_last_update_utc")
            })
        else:
            error_type = data.get("error-type", "Unknown API error")
            return jsonify({"error": f"API Error: {error_type}", "details": data}), 500

    except requests.exceptions.HTTPError as http_err:
        return jsonify({"error": f"HTTP error occurred: {http_err}", "url_called": api_url}), 500
    except requests.exceptions.ConnectionError as conn_err:
        return jsonify({"error": f"Error Connecting: {conn_err}", "url_called": api_url}), 500
    except requests.exceptions.Timeout as timeout_err:
        return jsonify({"error": f"Timeout Error: {timeout_err}", "url_called": api_url}), 500
    except requests.exceptions.RequestException as req_err:
        return jsonify({"error": f"Oops: Something Else went wrong with the request: {req_err}", "url_called": api_url}), 500
    except ValueError as json_err: # s
        return jsonify({"error": f"Error decoding JSON response: {json_err}"}), 500


if __name__ == '__main__':
    app.run(port=5000, debug=True) 