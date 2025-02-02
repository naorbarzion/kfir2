from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime
import csv
from typing import Dict, List, Optional
import random
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO

print("Starting application...")

app = Flask(__name__)

# הגדרת משתנים גלובליים
client = None
sheet_routes = None
sheet_links = None

# הגדרת כותרות הגיליון
headers = [
    'route_name',           # שם הקו - A
    'start_time',          # שעת התחלה - B
    'end_time',            # שעת סיום - C
    'pickup_time',         # זמן איסוף - D
    'dropoff_time',        # זמן פיזור - E
    'map_url',             # קישור למפה - F
    'modal_title',         # כותרת המודל - G
    'modal_content',       # תוכן המודל - H
    'map_availability',    # זמן זמינות המפה - I
    'status'               # סטטוס הקו - J
]

# הגדרת הרשאות לגישה ל-Google Sheets
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# קבוע עבור תיקיית גוגל דרייב
DRIVE_FOLDER_ID = '15pwRsGUYz3FeERr4aftOHI6h2xJAT-L2'

def init_google_sheets():
    """אתחול חיבור ל-Google Sheets"""
    try:
        # בדיקה שכל המשתנים הנדרשים קיימים
        required_env_vars = [
            "GOOGLE_SHEETS_TYPE",
            "GOOGLE_SHEETS_PROJECT_ID",
            "GOOGLE_SHEETS_PRIVATE_KEY_ID",
            "GOOGLE_SHEETS_PRIVATE_KEY",
            "GOOGLE_SHEETS_CLIENT_EMAIL",
            "GOOGLE_SHEETS_CLIENT_ID",
            "GOOGLE_SHEETS_AUTH_URI",
            "GOOGLE_SHEETS_TOKEN_URI",
            "GOOGLE_SHEETS_AUTH_PROVIDER_X509_CERT_URL",
            "GOOGLE_SHEETS_CLIENT_X509_CERT_URL",
            "SPREADSHEET_ID"
        ]
        
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            print(f"Missing environment variables: {', '.join(missing_vars)}")
            return None

        service_account_info = {
            "type": os.getenv("GOOGLE_SHEETS_TYPE"),
            "project_id": os.getenv("GOOGLE_SHEETS_PROJECT_ID"),
            "private_key_id": os.getenv("GOOGLE_SHEETS_PRIVATE_KEY_ID"),
            "private_key": os.getenv("GOOGLE_SHEETS_PRIVATE_KEY").replace('\\n', '\n'),
            "client_email": os.getenv("GOOGLE_SHEETS_CLIENT_EMAIL"),
            "client_id": os.getenv("GOOGLE_SHEETS_CLIENT_ID"),
            "auth_uri": os.getenv("GOOGLE_SHEETS_AUTH_URI"),
            "token_uri": os.getenv("GOOGLE_SHEETS_TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("GOOGLE_SHEETS_AUTH_PROVIDER_X509_CERT_URL"),
            "client_x509_cert_url": os.getenv("GOOGLE_SHEETS_CLIENT_X509_CERT_URL")
        }

        print("Service account info:", json.dumps(service_account_info, indent=2))
        
        scope = ['https://www.googleapis.com/auth/spreadsheets']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Error with Google Sheets authorization: {e}")
        return None

def init_spreadsheet(client):
    """אתחול הגיליון"""
    try:
        if client is None:
            print("Client is None, cannot initialize spreadsheet")
            return None, None
            
        SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
        if not SPREADSHEET_ID:
            print("SPREADSHEET_ID environment variable is not set")
            return None, None
            
        print(f"Opening spreadsheet with ID: {SPREADSHEET_ID}")
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        print("Successfully opened spreadsheet")
        
        # פתיחת גיליון הקווים
        try:
            sheet_routes = spreadsheet.worksheet('routes')
            print("Found routes worksheet")
        except Exception as e:
            print(f"Error opening routes worksheet: {e}")
            return None, None
            
        # פתיחת גיליון הקישורים
        try:
            sheet_links = spreadsheet.worksheet('links')
            print("Found links worksheet")
        except Exception as e:
            print(f"Error opening links worksheet: {e}")
            return None, None
            
        return sheet_routes, sheet_links
    except Exception as e:
        print(f"Error initializing spreadsheet: {e}")
        return None, None

@app.before_first_request
def initialize():
    """אתחול המערכת לפני הבקשה הראשונה"""
    global client, sheet_routes, sheet_links
    try:
        client = init_google_sheets()
        if client:
            sheet_routes, sheet_links = init_spreadsheet(client)
    except Exception as e:
        print(f"Error during initialization: {e}")

def add_example_route():
    """הוספת קו לדוגמה"""
    try:
        # בדיקה אם יש כבר קווים בגיליון
        all_values = sheet_routes.get_all_values()
        if len(all_values) > 1:  # אם יש יותר משורה אחת (כותרות)
            print("Routes already exist, skipping example route")
            return
        
        # קבלת קישור פנוי מבנק הקישורים
        available_links = get_available_links()
        map_url = ''
        map_name = ''
        if available_links:
            for link in available_links:
                if link.get('is_used') != 'true':
                    map_url = link['map_url']
                    map_name = link['map_name']
                    break
        
        # הוספת קו לדוגמא
        example_route = [
            'קו בית חולים הגליל נהריה',  # שם הקו
            '21:50',                       # שעת התחלה
            '23:00',                       # שעת סיום
            '22:00',                       # זמן איסוף
            '23:15',                       # זמן פיזור
            map_url,                       # קישור למפה
            'אחים ואחיות יקרים',          # כותרת המודל
            'אנו שמחים לשרת אתכם ולהקל על הנסיעה שלכם לעבודה ובחזרה הביתה.',  # תוכן המודל
            'המפה תהיה זמינה בשעה 21:50 בדיוק',  # זמן זמינות המפה
            'פעיל'                         # סטטוס הקו
        ]
        sheet_routes.append_row(example_route)
        print("Added example route")
        
        # עדכון סטטוס הקישור
        if map_url:
            update_link_status(map_url, True)
            
    except Exception as e:
        print(f"Error adding example route: {e}")

def refresh_sheets():
    """רענון החיבור לגיליונות"""
    global client, sheet_routes, sheet_links
    client = init_google_sheets()
    sheet_routes, sheet_links = init_spreadsheet(client)

# אתחול הגיליונות
try:
    refresh_sheets()
    # הוספת קו לדוגמה
    add_example_route()
except Exception as e:
    print(f"Critical error during initialization: {e}")
    raise

def debug_sheet_structure():
    """פונקציה לבדיקת מבנה הגיליון והנתונים"""
    print("\n=== מבנה הגיליון ===")
    
    # קבלת כל הנתונים
    all_values = sheet_routes.get_all_values()
    if not all_values:
        print("הגיליון ריק")
        return
    
    # הדפסת הכותרות
    headers = all_values[0]
    print("\nכותרות:")
    for i, header in enumerate(headers, 1):
        print(f"עמודה {chr(64 + i)} ({i}): '{header}'")
    
    # הדפסת הנתונים
    print("\nנתונים:")
    for row_num, row in enumerate(all_values[1:], 2):
        print(f"\nשורה {row_num}:")
        for i, value in enumerate(row):
            print(f"  {chr(64 + i + 1)} ({i+1}): '{value}'")

def get_all_routes():
    """קבלת כל הקווים מהגיליון"""
    try:
        # קבלת כל השורות כולל הכותרות
        all_values = sheet_routes.get_all_values()
        if len(all_values) <= 1:  # אם יש רק כותרות או פחות
            return []
        
        # המרת השורות למילון
        headers = all_values[0]
        routes = []
        for row in all_values[1:]:  # דילוג על שורת הכותרות
            route = {}
            for i, value in enumerate(row):
                route[headers[i]] = value
            routes.append(route)
        
        return routes
            
    except Exception as e:
        print(f"Error getting routes: {e}")
        return None  # רק במקרה של שגיאה אמיתית

def init_google_drive():
    """אתחול שירות גוגל דרייב"""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('drive.json', scope)
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Error initializing Google Drive: {e}")
        raise

def create_html_file_in_drive(filename: str, content: str, drive_service) -> str:
    """יצירת קובץ HTML בגוגל דרייב"""
    try:
        file_metadata = {
            'name': filename,
            'parents': [DRIVE_FOLDER_ID],
            'mimeType': 'text/html'
        }
        
        # יצירת אובייקט מדיה מהתוכן
        fh = BytesIO(content.encode('utf-8'))
        media = MediaIoBaseUpload(fh, mimetype='text/html', resumable=True)
        
        # העלאת הקובץ לדרייב
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        print(f"Created file {filename} in Drive with ID: {file.get('id')}")
        return file.get('webViewLink')
        
    except Exception as e:
        print(f"Error creating file in Drive: {e}")
        raise

def update_html_file_in_drive(file_id: str, content: str, drive_service) -> None:
    """עדכון קובץ HTML קיים בגוגל דרייב"""
    try:
        # יצירת אובייקט מדיה מהתוכן החדש
        fh = BytesIO(content.encode('utf-8'))
        media = MediaIoBaseUpload(fh, mimetype='text/html', resumable=True)
        
        # עדכון הקובץ
        drive_service.files().update(
            fileId=file_id,
            media_body=media
        ).execute()
        
        print(f"Updated file {file_id} in Drive")
        
    except Exception as e:
        print(f"Error updating file in Drive: {e}")
        raise

def find_file_in_drive(filename: str, drive_service) -> dict:
    """חיפוש קובץ בגוגל דרייב לפי שם"""
    try:
        query = f"name = '{filename}' and '{DRIVE_FOLDER_ID}' in parents and trashed = false"
        results = drive_service.files().list(
            q=query,
            fields="files(id, webViewLink)"
        ).execute()
        files = results.get('files', [])
        
        return files[0] if files else None
        
    except Exception as e:
        print(f"Error finding file in Drive: {e}")
        raise

def generate_route_html(route_data):
    """יצירת קובץ HTML עבור קו ספציפי"""
    try:
        with open('templates/route_template.html', 'r', encoding='utf-8') as file:
            template = file.read()
        
        # החלפת הפלייסהולדרים בערכים האמיתיים
        replacements = {
            'ROUTE_NAME_PLACEHOLDER': route_data['route_name'],
            'START_TIME_PLACEHOLDER': route_data['start_time'],
            'END_TIME_PLACEHOLDER': route_data['end_time'],
            'PICKUP_TIME_PLACEHOLDER': route_data['pickup_time'],
            'DROPOFF_TIME_PLACEHOLDER': route_data['dropoff_time'],
            'MAP_URL_PLACEHOLDER': route_data.get('full_map_url', route_data['map_url']),
            'MODAL_TITLE_PLACEHOLDER': route_data['modal_title'],
            'MODAL_CONTENT_PLACEHOLDER': route_data['modal_content'],
            'MAP_AVAILABILITY_PLACEHOLDER': route_data['map_availability']
        }
        
        # החלפת כל הפלייסהולדרים בערכים האמיתיים
        content = template
        for placeholder, value in replacements.items():
            if value is None:
                value = ''
            content = content.replace(placeholder, str(value))
        
        # שם הקובץ
        filename = f"templates/routes/route_{route_data['route_name'].replace(' ', '_')}.html"
        
        # יצירת תיקיית routes אם לא קיימת
        os.makedirs('templates/routes', exist_ok=True)
        
        # שמירת הקובץ
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)
            
        return filename
            
    except Exception as e:
        print(f"Error generating route HTML: {e}")
        raise

def get_available_links():
    """קבלת כל הקישורים מהגיליון"""
    try:
        links = sheet_links.get_all_records()
        return links
    except Exception as e:
        print(f"Error getting links: {e}")
        return None

def update_link_status(map_url: str, is_used: bool):
    """עדכון סטטוס הקישור בגיליון"""
    try:
        # ניסיון לרענן את האישור אם פג תוקף
        try:
            cell = sheet_links.find(map_url)
        except gspread.exceptions.APIError:
            print("Refreshing credentials...")
            refresh_sheets()
            cell = sheet_links.find(map_url)
            
        if cell:
            sheet_links.update_cell(cell.row, 3, str(is_used).lower())
            print(f"Updated status for link {map_url} to {is_used}")
        else:
            print(f"Link {map_url} not found in spreadsheet")
    except Exception as e:
        print(f"Error updating link status: {e}")

def ensure_sheets_initialized():
    """וידוא שהחיבור לגיליונות מאותחל"""
    global client, sheet_routes, sheet_links
    if client is None or sheet_routes is None or sheet_links is None:
        try:
            refresh_sheets()
            return True
        except Exception as e:
            print(f"Error initializing sheets: {e}")
            return False

@app.route('/')
def index():
    """דף הבית הבסיסי"""
    return render_template('index.html')

@app.route('/admin')
def admin():
    """דף ניהול הקווים"""
    try:
        # בדיקה אם צריך לאתחל את החיבור
        global client, sheet_routes, sheet_links
        if client is None:
            client = init_google_sheets()
            if client is None:
                return render_template('admin.html', routes=[], error="שגיאה בהתחברות למסד הנתונים")
        
        return render_template('admin.html', routes=[])
    except Exception as e:
        print(f"Error in admin page: {e}")
        return render_template('admin.html', routes=[], error=str(e))

@app.route('/route/<route_name>')
def view_route(route_name):
    """צפייה בקו ספציפי"""
    try:
        routes = get_all_routes()
        if not routes:
            return "שגיאה בטעינת הקווים. אנא נסה שוב.", 500
            
        for route in routes:
            if route['route_name'] == route_name:
                try:
                    filename = generate_route_html(route)
                    return render_template(f"routes/route_{route_name.replace(' ', '_')}.html")
                except Exception as e:
                    print(f"Error generating route page: {e}")
                    return "שגיאה ביצירת דף הקו. אנא נסה שוב.", 500
        
        print(f"Route {route_name} not found")
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Error in view_route: {e}")
        return "שגיאה בטעינת הקו. אנא נסה שוב.", 500

@app.route('/create_route', methods=['POST'])
def create_route():
    """יצירת קו חדש"""
    try:
        print("Creating new route")
        # קבלת הנתונים מהטופס
        route_data = {
            'route_name': request.form.get('route_name'),
            'start_time': request.form.get('start_time'),
            'end_time': request.form.get('end_time'),
            'pickup_time': request.form.get('pickup_time'),
            'dropoff_time': request.form.get('dropoff_time'),
            'modal_title': request.form.get('modal_title'),
            'modal_content': request.form.get('modal_content'),
            'map_availability': request.form.get('map_availability'),
            'status': request.form.get('status', 'פעיל')  # ברירת מחדל: פעיל
        }
        
        # וידוא שכל השדות החובה קיימים
        required_fields = ['route_name', 'start_time', 'end_time', 'pickup_time', 'dropoff_time']
        for field in required_fields:
            if not route_data.get(field):
                return f"שדה {field} הוא שדה חובה.", 400
        
        print(f"Route data: {route_data}")
        
        # מציאת קישור פנוי מבנק הקישורים
        available_links = get_available_links()
        map_url = ''
        if available_links:
            # איסוף כל הקישורים הפנויים
            free_links = [link for link in available_links if link.get('is_used') != 'true']
            if free_links:
                # בחירה רנדומלית של קישור מתוך הקישורים הפנויים
                chosen_link = random.choice(free_links)
                map_url = chosen_link['map_url']
                print(f"Randomly selected map URL: {map_url}")
            
            if not map_url:
                return "לא נמצאו קישורים פנויים בבנק הקישורים. אנא פנה למנהל המערכת.", 400
        else:
            return "שגיאה בטעינת בנק הקישורים. אנא נסה שוב.", 500
        
        route_data['map_url'] = map_url
        
        # וידוא שהסטטוס הוא ערך תקין
        route_data['status'] = 'פעיל' if route_data['status'] == 'פעיל' else 'לא פעיל'
        
        # הוספת הקו לגיליון
        try:
            sheet_routes.append_row([
                route_data['route_name'],
                route_data['start_time'],
                route_data['end_time'],
                route_data['pickup_time'],
                route_data['dropoff_time'],
                route_data['map_url'],
                route_data['modal_title'] or '',
                route_data['modal_content'] or '',
                route_data['map_availability'] or '',
                route_data['status']
            ])
            print("Route added successfully")
            
            # עדכון סטטוס הקישור
            update_link_status(map_url, True)
                
        except Exception as e:
            print(f"Error adding route to spreadsheet: {e}")
            return "שגיאה בהוספת הקו לגיליון. אנא נסה שוב.", 500
        
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Error in create_route: {e}")
        return "שגיאה ביצירת הקו. אנא נסה שוב.", 500

@app.route('/get_route/<route_name>')
def get_route(route_name):
    try:
        # מקבל את כל הקווים
        routes = get_all_routes()
        if not routes:
            return jsonify({'error': 'לא נמצאו קווים'}), 404
            
        # מחפש את הקו הספציפי
        route = next((route for route in routes if route['route_name'] == route_name), None)
        if not route:
            return jsonify({'error': 'הקו לא נמצא'}), 404
            
        # מחזיר את פרטי הקו
        return jsonify({
            'route_name': route['route_name'],
            'pickup_time': route['pickup_time'],
            'dropoff_time': route['dropoff_time'],
            'start_time': route['start_time'],
            'end_time': route['end_time'],
            'map_availability': route.get('map_availability', ''),
            'modal_title': route.get('modal_title', ''),
            'modal_content': route.get('modal_content', ''),
            'status': route.get('status', 'פעיל')
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/edit_route/<route_name>', methods=['POST'])
def edit_route(route_name):
    """עדכון קו קיים"""
    try:
        print(f"Editing route: {route_name}")
        
        # קבלת הנתונים מהטופס
        route_data = {
            'route_name': request.form.get('route_name'),
            'start_time': request.form.get('start_time'),
            'end_time': request.form.get('end_time'),
            'pickup_time': request.form.get('pickup_time'),
            'dropoff_time': request.form.get('dropoff_time'),
            'modal_title': request.form.get('modal_title'),
            'modal_content': request.form.get('modal_content'),
            'map_availability': request.form.get('map_availability'),
            'status': request.form.get('status', 'פעיל')
        }
        
        print(f"Looking for route: {route_name}")
        
        try:
            # מציאת השורה של הקו לפי השם המקורי
            cell = sheet_routes.find(route_name)
            if not cell:
                print(f"Route not found: {route_name}")
                return "הקו לא נמצא.", 404
            
            row_index = cell.row
            print(f"Found route at row: {row_index}")
            
            # קבלת הקישור הקיים של הקו
            existing_map_url = sheet_routes.cell(row_index, 6).value
            print(f"Existing map URL: {existing_map_url}")
            
            # וידוא שכל השדות החובה קיימים
            required_fields = ['route_name', 'start_time', 'end_time', 'pickup_time', 'dropoff_time']
            for field in required_fields:
                if not route_data.get(field):
                    return f"שדה {field} הוא שדה חובה.", 400
            
            # עדכון שורת הקו
            update_data = [
                route_data['route_name'],
                route_data['start_time'],
                route_data['end_time'],
                route_data['pickup_time'],
                route_data['dropoff_time'],
                existing_map_url,  # שמירה על הקישור הקיים
                route_data['modal_title'] or '',
                route_data['modal_content'] or '',
                route_data['map_availability'] or '',
                route_data['status']
            ]
            
            print(f"Updating row {row_index} with data: {update_data}")
            sheet_routes.update(f'A{row_index}:J{row_index}', [update_data])
            print("Route updated successfully")
                
        except Exception as e:
            print(f"Error updating route in spreadsheet: {e}")
            return "שגיאה בעדכון הקו בגיליון. אנא נסה שוב.", 500
        
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Error in edit_route: {e}")
        return "שגיאה בעדכון הקו. אנא נסה שוב.", 500

@app.route('/delete_route/<route_name>', methods=['POST'])
def delete_route(route_name):
    """מחיקת קו קיים"""
    try:
        print(f"Deleting route: {route_name}")
        
        try:
            # מציאת השורה של הקו
            cell = sheet_routes.find(route_name)
            if not cell:
                print(f"Route not found: {route_name}")
                return "הקו לא נמצא.", 404
            
            row_index = cell.row
            print(f"Found route at row: {row_index}")
            
            # קבלת הקישור של הקו לפני המחיקה
            map_url = sheet_routes.cell(row_index, 6).value
            print(f"Map URL to be freed: {map_url}")
            
            # מחיקת השורה
            sheet_routes.delete_rows(row_index)
            print("Route deleted successfully")
            
            # שחרור הקישור בחזרה למאגר
            if map_url:
                update_link_status(map_url, False)
                print(f"Link {map_url} freed successfully")
                
        except Exception as e:
            print(f"Error deleting route from spreadsheet: {e}")
            return "שגיאה במחיקת הקו מהגיליון. אנא נסה שוב.", 500
        
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Error in delete_route: {e}")
        return "שגיאה במחיקת הקו. אנא נסה שוב.", 500

# במקום זה, נייצא את האפליקציה
app.debug = False  # חשוב! לכבות debug mode בפרודקשן
application = app 
