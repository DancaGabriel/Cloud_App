from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from dotenv import load_dotenv
import os
import requests
import boto3
import pandas as pd
import yfinance as yf
import mysql.connector
from datetime import datetime, date, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

textract_client = boto3.client('textract', region_name='eu-central-1')

load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'o_cheie_secreta_foarte_puternica_si_unica_aici')

EXCHANGE_RATE_API_KEY = os.getenv('EXCHANGE_RATE_API_KEY')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

SOURCE_EXCHANGERATE_API = "ExchangeRateAPI.com"
SOURCE_FRANKFURTER_APP = "Frankfurter.app"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_route'
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"

class User(UserMixin):
    def __init__(self, id, username, email, password_hash=None):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash

    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        user_data_dict = None
        try:
            cursor.execute("SELECT id, username, email FROM users WHERE id = %s", (user_id,))
            user_data_dict = cursor.fetchone()
        except mysql.connector.Error as err:
            print(f"Error fetching user (id: {user_id}) from DB: {err}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
        if user_data_dict:
            return User(
                id=user_data_dict['id'],
                username=user_data_dict['username'],
                email=user_data_dict['email']
            )
        return None

    @staticmethod
    def find_by_username(username):
        conn = get_db_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        user_data_dict = None
        try:
            cursor.execute("SELECT id, username, email, password_hash FROM users WHERE username = %s", (username,))
            user_data_dict = cursor.fetchone()
        except mysql.connector.Error as err:
            print(f"Error searching for user {username} in DB: {err}")
        finally:
            if conn and conn.is_connected(): cursor.close(); conn.close()
        if user_data_dict:
            return User(id=user_data_dict['id'], username=user_data_dict['username'], email=user_data_dict['email'], password_hash=user_data_dict['password_hash'])
        return None

    @staticmethod
    def find_by_email(email_address):
        conn = get_db_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        user_data_dict = None
        try:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email_address,))
            user_data_dict = cursor.fetchone()
        except mysql.connector.Error as err:
            print(f"Error searching for email {email_address} in DB: {err}")
        finally:
            if conn and conn.is_connected(): cursor.close(); conn.close()
        return bool(user_data_dict)

@login_manager.user_loader
def load_user(user_id):
    return User.get(int(user_id))

# --- Formulare WTForms ---
class RegistrationForm(FlaskForm):
    username = StringField('Utilizator', validators=[DataRequired(), Length(min=4, max=25)])
    email = StringField('Email', validators=[DataRequired(), Email(message="Invalid email address.")])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, max=35)])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')]
    )
    submit = SubmitField('Register')

    def validate_username(self, username_field): # Parameter name changed for clarity
        if User.find_by_username(username_field.data):
            raise ValidationError('This username is already in use. Please choose another.')

    def validate_email(self, email_field): # Parameter name changed for clarity
        if User.find_by_email(email_field.data): # Uses the corrected find_by_email
            raise ValidationError('This email address is already in use. Please choose another.')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Log In')
# --- Funcțiile Helper pentru BD și API ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, connect_timeout=5
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Eroare CRITICĂ la conectarea la MySQL: {err}")
        return None

def create_user_stocks_table_if_not_exists():
    conn = get_db_connection()
    if not conn:
        print("❌ Database connection failed.")
        return
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_stocks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                buy_price DECIMAL(10, 2) NOT NULL,
                quantity INT NOT NULL,
                buy_date DATE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        conn.commit()
        print("✅ Table `user_stocks` created or already exists.")
    except mysql.connector.Error as err:
        print(f"❌ Error creating table `user_stocks`: {err}")
    finally:
        cursor.close()
        conn.close()

def parse_api_datetime_to_db_format(api_datetime_str):
    formats_to_try = ['%a, %d %b %Y %H:%M:%S %z']
    cleaned_api_datetime_str = api_datetime_str.replace(" UTC", " +0000").replace(" GMT", " +0000")
    if len(cleaned_api_datetime_str) > 5 and cleaned_api_datetime_str[-3] == ':':
        cleaned_api_datetime_str = cleaned_api_datetime_str[:-3] + cleaned_api_datetime_str[-2:]
    for fmt in formats_to_try:
        try:
            dt_object_aware = datetime.strptime(cleaned_api_datetime_str, fmt)
            return dt_object_aware.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError: pass
    try:
        datetime_part_only = " ".join(cleaned_api_datetime_str.split()[:5])
        dt_object_utc_naive = datetime.strptime(datetime_part_only, '%a, %d %b %Y %H:%M:%S')
        return dt_object_utc_naive
    except ValueError as e_final:
        print(f"CRITICAL: Failed to parse API date '{api_datetime_str}': {final_err}")
        return None

def get_rates_from_db(query_date_obj, base_curr, source_api):
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor(dictionary=True)
    rates_data_from_db = None
    try:
        query = "SELECT base_currency_code, target_currency_code, rate_value, source_last_updated_utc FROM daily_exchange_rates WHERE rate_date = %s AND base_currency_code = %s AND source_api_name = %s"
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
            rates_data_from_db = {"base_code": rows[0]['base_currency_code'], "rates": rates, "last_update": last_update_str}
    except mysql.connector.Error as err: print(f"Error reading from DB ({source_api}): {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    return rates_data_from_db

def insert_rates_into_db(base_code, rates_dict, effective_date_obj, source_last_update_utc_str, source_api):
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    success = False
    source_datetime_db_format = parse_api_datetime_to_db_format(source_last_update_utc_str)
    if not source_datetime_db_format:
        print(f"CRITICAL: Could not parse source_last_update_str: '{source_last_update_str}' (source: {source_api}). Rates will NOT be inserted.")
        if conn and conn.is_connected(): conn.close()
        return False
    insert_query = "INSERT IGNORE INTO daily_exchange_rates (rate_date, base_currency_code, target_currency_code, rate_value, source_api_name, source_last_updated_utc) VALUES (%s, %s, %s, %s, %s, %s)"
    try:
        conn.start_transaction()
        for target_code, rate_value in rates_dict.items():
            if rate_value is not None:
                 cursor.execute(insert_query, (effective_date_obj, base_code, target_code, float(rate_value), source_api, source_datetime_db_format))
        conn.commit()
        print(f"Ratele pentru {base_code} din {effective_date_obj} (sursa: {source_api}) inserate/ignorate cu succes.")
        success = True
    except mysql.connector.Error as err:
        print(f"Error inserting into DB ({source_api}): {err}")
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    return success


def get_current_stock_price(symbol):
    api_key = os.getenv('FINNHUB_API_KEY')
    if not api_key:
        print("❌ FINNHUB_API_KEY missing in .env")
        return None
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={api_key}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("c")  # current price
    except Exception as e:
        print(f"❌ Finnhub error for {symbol}: {e}")
        return None

# --- Rute Flask ---
@app.route('/')
def hello_world():
    current_year = datetime.now().year
    return render_template('index.html', year=current_year)

@app.route('/exchange-rates')
def exchange_rates_page():
    current_year = datetime.now().year
    return render_template('exchange_rates.html', year=current_year)

@app.route('/visualize')
@login_required # Am protejat această rută
def visualize_page():
    current_year = datetime.now().year
    return render_template('visualize.html', year=current_year)

# --- Rute pentru Autentificare ---
@app.route('/register', methods=['GET', 'POST'])
def register_route():
    if current_user.is_authenticated:
        return redirect(url_for('hello_world'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data) # Am eliminat .decode('utf-8')
        
        conn = get_db_connection()
        if not conn:
            flash('Database server error. Please try again later.', 'danger')
            return render_template('register.html', title='Register', form=form, year=datetime.now().year)

        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                           (form.username.data, form.email.data, hashed_password))
            conn.commit()
            flash(f'Account for {form.username.data} created! You can now log in.', 'success')
            return redirect(url_for('login_route'))
        except mysql.connector.Error as err:
            conn.rollback()
            print(f"User registration error: {err}")
            flash('Registration error (possibly existing user/email). Please try again.', 'danger')
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    current_year = datetime.now().year
    return render_template('register.html', title='Register', form=form, year=current_year)

@app.route('/login', methods=['GET', 'POST'])
def login_route():
    if current_user.is_authenticated:
        return redirect(url_for('hello_world'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.find_by_username(form.username.data)
        if user and check_password_hash(user.password_hash, form.password.data):  # Using user.password_hash
            login_user(user, remember=form.remember.data)
            flash('Login successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('hello_world'))
        else:
            flash('Login failed. Check username and password.', 'danger')
    current_year = datetime.now().year
    return render_template('login.html', title='Login', form=form, year=current_year)

@app.route('/logout')
@login_required
def logout_route():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login_route'))


# --- Rute API pentru rate ---
@app.route('/get-exchange-rates')
def get_exchange_rates_route():
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        return jsonify({"error": "Database configuration is incomplete on the server."}), 500
    today_utc_date = datetime.now(timezone.utc).date()
    base_currency_to_fetch = request.args.get('base', 'USD').upper()
    rates_from_db = get_rates_from_db(today_utc_date, base_currency_to_fetch, SOURCE_EXCHANGERATE_API)
    if rates_from_db:
        rates_from_db['data_source'] = "database (local cache)"
        return jsonify(rates_from_db)
    else:
        if not EXCHANGE_RATE_API_KEY:
            return jsonify({"error": f"API Key for {SOURCE_EXCHANGERATE_API} is not configured.", "data_source": "config_error"}), 500
        api_url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/latest/{base_currency_to_fetch}"
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            api_data = response.json()
            if api_data.get("result") == "success":
                base_c = api_data.get("base_code"); conversion_r = api_data.get("conversion_rates"); time_last_update_utc_str = api_data.get("time_last_update_utc")
                api_dt_obj_parsed = parse_api_datetime_to_db_format(time_last_update_utc_str)
                if api_dt_obj_parsed and api_dt_obj_parsed.date() == today_utc_date:
                    if base_c and conversion_r:
                        insert_rates_into_db(base_c, conversion_r, today_utc_date, time_last_update_utc_str, SOURCE_EXCHANGERATE_API)
                return jsonify({"base_code": base_c, "rates": conversion_r, "last_update": time_last_update_utc_str, "data_source": f"{SOURCE_EXCHANGERATE_API} (external)"})
            else:
                error_type = api_data.get("error-type", f"Unknown API error ({SOURCE_EXCHANGERATE_API})")
                return jsonify({"error": f"External API error ({SOURCE_EXCHANGERATE_API}): {error_type}", "details": api_data, "data_source": "api_error"}), 500
        except requests.exceptions.RequestException as e:
            print(f"Request error to {SOURCE_EXCHANGERATE_API}: {str(e)}")
            return jsonify({"error": f"Request error to external API ({SOURCE_EXCHANGERATE_API}): {str(e)}", "url_called": api_url, "data_source": "request_error"}), 500
        except ValueError as json_err:
            print(f"JSON decode error ({SOURCE_EXCHANGERATE_API}): {json_err}")
            return jsonify({"error": f"JSON decoding error from external API ({SOURCE_EXCHANGERATE_API}): {json_err}", "data_source": "request_error"}), 500

@app.route('/get-frankfurter-historical-rates')
def get_frankfurter_historical_rates_route():
    selected_date_str = request.args.get('date')
    base_currency_frankfurter = request.args.get('base', 'USD').upper()
    if not selected_date_str:
        return jsonify({"error": "Parameter 'date' (YYYY-MM-DD) is required.", "data_source": "user_error"}), 400
    try:
        frank_date_obj = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        min_date = date(1999, 1, 4)
        max_date = datetime.now(timezone.utc).date() - timedelta(days=1)
        if not (min_date <= frank_date_obj <= max_date):
            return jsonify({
                "error": f"Date must be between {min_date.strftime('%Y-%m-%d')} and {max_date.strftime('%Y-%m-%d')}.",
                "data_source": "user_error"
            }), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD.", "data_source": "user_error"}), 400

    rates_from_db = get_rates_from_db(frank_date_obj, base_currency_frankfurter, SOURCE_FRANKFURTER_APP)
    if rates_from_db:
        rates_from_db['data_source'] = f"database (local cache - {SOURCE_FRANKFURTER_APP})"
        return jsonify(rates_from_db)

    api_url = f"https://api.frankfurter.app/{selected_date_str}?base={base_currency_frankfurter}"
    print(f"Calling Frankfurter API: {api_url}")
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        frank_data = response.json()
        base_c = frank_data.get("base")
        conversion_r = frank_data.get("rates")
        frank_api_date_str = frank_data.get("date")
        hist_dt_for_timestamp = datetime(
            frank_date_obj.year, frank_date_obj.month, frank_date_obj.day,
            0, 0, 0, tzinfo=timezone.utc
        )
        db_timestamp_str = hist_dt_for_timestamp.strftime('%a, %d %b %Y %H:%M:%S %z')
        frontend_display_last_update = hist_dt_for_timestamp.strftime('%a, %d %b %Y %H:%M:%S') + " +00:00"
        if base_c and conversion_r and frank_api_date_str:
            print(f"Preparing insert for requested date {frank_date_obj} (Frankfurter API returned for {frank_api_date_str}).")
            insert_rates_into_db(base_c, conversion_r, frank_date_obj, db_timestamp_str, SOURCE_FRANKFURTER_APP)
        else:
            print(f"Incomplete response from Frankfurter API for {selected_date_str}. Not inserting into DB.")
            if not (base_c and conversion_r):
                return jsonify({"error": "Incomplete response from Frankfurter API.", "data_source": "frankfurter_api_error"}), 500
        return jsonify({
            "base_code": base_c,
            "rates": conversion_r,
            "last_update": frontend_display_last_update,
            "data_source": f"{SOURCE_FRANKFURTER_APP} (rates from {frank_api_date_str}, requested for {selected_date_str})"
        })
    except requests.exceptions.RequestException as e:
        error_details = None
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            try:
                error_details = e.response.json()
            except ValueError:
                pass
            print(f"HTTP Error (Frankfurter): {str(e)}")
            return jsonify({
                "error": f"HTTP error from Frankfurter: {e.response.status_code}",
                "details": error_details,
                "url_called": api_url,
                "data_source": "frankfurter_api_error"
            }), 500
        print(f"Request Error (Frankfurter): {str(e)}")
        return jsonify({
            "error": f"Request error to Frankfurter: {str(e)}",
            "url_called": api_url,
            "data_source": "frankfurter_request_error"
        }), 500
    except ValueError as json_err:
        print(f"JSON decode error (Frankfurter): {json_err}")
        return jsonify({"error": f"JSON decoding error from Frankfurter: {json_err}", "data_source": "frankfurter_request_error"}), 500

@app.route('/stocks', methods=['GET', 'POST'])
@login_required
def stocks_page():
    conn = get_db_connection()
    if request.method == 'POST':
        symbol = request.form['symbol'].upper()
        price = float(request.form['buy_price'])
        quantity = int(request.form['quantity'])
        buy_date = request.form['buy_date']
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_stocks (user_id, symbol, buy_price, quantity, buy_date)
                VALUES (%s, %s, %s, %s, %s)
            """, (current_user.id, symbol, price, quantity, buy_date))
            conn.commit()
            flash(f"Stock {symbol} added!", "success")
        except mysql.connector.Error as err:
            conn.rollback()
            print(f"DB error: {err}")
            flash("Error saving the stock.", "danger")
        finally:
            cursor.close()

    user_stocks = []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM user_stocks WHERE user_id = %s ORDER BY buy_date DESC",
            (current_user.id,)
        )
        rows = cursor.fetchall()
        for row in rows:
            current_price = get_current_stock_price(row['symbol'])
            buy_price = float(row['buy_price'])
            if current_price is not None:
                win_loss = ((current_price - buy_price) / buy_price) * 100
            else:
                current_price = "Error"
                win_loss = None
            user_stocks.append({
                "id": row['id'],
                "symbol": row['symbol'],
                "quantity": row['quantity'],
                "buy_price": buy_price,
                "buy_date": row['buy_date'],
                "current_price": current_price,
                "win_loss": win_loss
            })
    except mysql.connector.Error as err:
        print(f"Error fetching stocks: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('stocks.html', year=datetime.now().year, stocks=user_stocks)

@app.route('/delete-stock/<int:stock_id>', methods=['POST'])
@login_required
def delete_stock(stock_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_stocks WHERE id = %s AND user_id = %s",
            (stock_id, current_user.id)
        )
        conn.commit()
        flash("Stock deleted successfully.", "info")
    except mysql.connector.Error as err:
        print(f"Error deleting stock: {err}")
        flash("Error deleting stock.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('stocks_page'))

@app.route('/stock-history/<symbol>')
@login_required
def stock_history(symbol):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB connection failed"}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT MIN(buy_date) AS start_date FROM user_stocks
            WHERE user_id = %s AND symbol = %s
            """,
            (current_user.id, symbol)
        )
        row = cursor.fetchone()
        from_date = row['start_date'] if row and row['start_date'] else None
    except mysql.connector.Error as err:
        print(f"DB error: {err}")
        return jsonify({"error": "DB error"}), 500
    finally:
        cursor.close()
        conn.close()

    if not from_date:
        from_date = datetime.now() - timedelta(days=30)

    try:
        df = yf.download(
            symbol,
            start=from_date.strftime('%Y-%m-%d'),
            end=datetime.now().strftime('%Y-%m-%d')
        )
        if df.empty or 'Close' not in df.columns:
            return jsonify({"error": "Historical data unavailable or missing columns."}), 404

        dates = df.index.to_series().dt.strftime('%Y-%m-%d').tolist()

        close_data = df['Close']
        if isinstance(close_data, pd.DataFrame):
            close_series = close_data.iloc[:, 0]
        else:
            close_series = close_data

        prices = close_series.round(2).tolist()

        return jsonify({"dates": dates, "prices": prices})
    except Exception as e:
        print(f"yfinance error: {e}")
        return jsonify({"error": "Error fetching data from yfinance"}), 500


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

import boto3
from flask import request, jsonify
from datetime import datetime

textract_client = boto3.client('textract', region_name='eu-west-1')  # Nu uita să setezi regiunea!

@app.route('/verify-student', methods=['GET'])
@login_required
def verify_student_form():
    return render_template('verify_student.html', year=datetime.now().year)

@app.route('/verify-student', methods=['POST'])
@login_required
def verify_student():
    if 'image' not in request.files:
        return jsonify({'status': 'Error', 'message': 'No file was sent.'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'status': 'Error', 'message': 'Invalid or empty file.'}), 400

    try:
        image_bytes = file.read()
        response = textract_client.detect_document_text(Document={'Bytes': image_bytes})

        text_lines = [block['Text'] for block in response['Blocks'] if block['BlockType'] == 'LINE']
        text = " ".join(text_lines).lower()

        keywords = ["student", "matricol", "university", "faculty", "facultate", "universitate"]
        found_keywords = sum(1 for kw in keywords if kw in text)

        if found_keywords >= 2:
            return jsonify({'status': 'Success', 'message': 'Student status confirmed ✅'})
        else:
            return jsonify({'status': 'Fail', 'message': 'Not enough student-related elements detected ❌'})
    except Exception as e:
        return jsonify({'status': 'Error', 'message': f'Image processing error: {str(e)}'}), 500


if __name__ == '__main__':
    create_user_stocks_table_if_not_exists()
    app.run(port=5000, debug=True)
