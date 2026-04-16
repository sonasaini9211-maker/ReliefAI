import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import requests
from datetime import datetime
import contextlib

app = Flask(__name__)
app.secret_key = "super_secret_hackathon_key"


@contextlib.contextmanager
def get_db():
    conn = sqlite3.connect('database.db', timeout=10) # 10 seconds timeout
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user'
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                problem TEXT NOT NULL,
                description TEXT NOT NULL,
                priority TEXT NOT NULL,
                ai_insight TEXT,
                lat REAL,
                lng REAL,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0:
            admin_hash = generate_password_hash('admin123')
            c.execute("INSERT INTO users (username, password, role) VALUES ('admin', ?, 'admin')", (admin_hash,))

       
        c.execute("SELECT COUNT(*) FROM reports")
        if c.fetchone()[0] == 0:
            dummy_data = [
                ("Central Park area", "fire", "Small brush fire near the south gate", "HIGH", 
                 "AI Insight: Detected keyword 'fire'. High volatility expected. Immediate dispatch of multiple units required.", 
                 40.7648, -73.9734, "Pending"),
                 
                ("Downtown Main St", "accident", "Two-car collision, traffic blocked", "MEDIUM", 
                 "AI Insight: 'Accident' categorized as Medium risk. No hyper-critical keywords detected. Monitor for escalation.", 
                 40.7128, -74.0060, "In Progress")
            ]
            c.executemany("INSERT INTO reports (location, problem, description, priority, ai_insight, lat, lng, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", dummy_data)
        
        conn.commit()


if not os.path.exists("database.db"):
    init_db()
else:
    
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("ALTER TABLE reports ADD COLUMN created_at TEXT")
            c.execute("UPDATE reports SET created_at = datetime('now') WHERE created_at IS NULL")
            conn.commit()
    except sqlite3.OperationalError:
        pass 


def get_coordinates(city):
    try:
        query = city + ", India"
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
        headers = {"User-Agent": "ReliefAI"}
        res = requests.get(url, headers=headers).json()
        if res:
            return float(res[0]['lat']), float(res[0]['lon'])
    except:
        pass
    return 20.5937, 78.9629


def determine_priority(problem, description):
    desc = description.lower()
    
    if 'fire' in problem.lower():
        priority = "HIGH"
        insight = "AI Insight: Flame spread risk detected. Categorized as critical volatility."
    elif 'medical' in problem.lower():
        priority = "HIGH"
        insight = "AI Insight: Critical health incident flagged. Vital intervention required rapidly."
    elif 'accident' in problem.lower():
        priority = "MEDIUM"
        insight = "AI Insight: Vehicular or localized accident. Standard resource allocation advised."
    else:
        priority = "LOW"
        insight = "AI Insight: Standard incident pattern recognized. Monitor situation."
    
    # Overrides
    if any(word in desc for word in ["urgent", "severe", "immediately", "critical", "dying", "explosion"]):
        priority = "HIGH"
        insight = "AI Insight: Extreme severity keywords parsed from user context! Immediate response required."
    elif "minor" in desc and priority != "HIGH":
        priority = "LOW"
        insight = "AI Insight: Event naturally de-escalated via contextual keywords indicating low immediate threat."
        
    return priority, insight

# ROUTES
@app.route('/')
def home():
    return render_template('index.html')

#  AUTHENTICATION
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT id, username, password, role FROM users WHERE username = ?", (username,))
            user = c.fetchone()
            
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['user'] = user['username']  # Explicitly stringing username as per req
            
            flash(f"Successfully logged in as {session['role'].capitalize()}.", "success")
            
            if user['role'] == 'admin':
                return redirect(url_for('admin'))
            return redirect(url_for('home'))
        else:
            flash("Invalid credentials or unauthorized user.", "error")
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'user') 
        
        hashed_pw = generate_password_hash(password)

        with get_db() as conn:
            c = conn.cursor()
            try:
                c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, hashed_pw, role))
                conn.commit()
                flash("Registration successful! You may now login.", "success")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash("Username already exists.", "error")
            
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for('login'))

@app.route('/report', methods=['GET', 'POST'])
def report():
    # Only allow authenticated users OR admins to file reports
    if 'user_id' not in session:
        flash("Authorization Required: You must be signed in to submit an emergency report.", "error")
        return redirect(url_for('login'))

    if request.method == 'POST':
        location = request.form.get('location', '').strip()
        problem = request.form.get('problem', '').strip()
        description = request.form.get('description', '').strip()
        
        if not location or not problem or not description:
            flash("All fields are required!", "error")
            return redirect(url_for('report'))

        if problem == 'other':
            custom_problem = request.form.get('custom_problem', '').strip()
            if custom_problem:
                problem = custom_problem

        # Data Normalization to prevent chart duplications! (e.g. "flood", "FLOOD", "Flood / Natural" -> "flood")
        problem = problem.lower()
        if "natural" in problem or "flood" in problem:
            problem = "flood"
        elif "fire" in problem:
            problem = "fire"
        elif "medical" in problem:
            problem = "medical"
        elif "accident" in problem:
            problem = "accident"

        # Check for duplicate incidents to prevent spam
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM reports WHERE LOWER(location) = ? AND LOWER(description) = ?", (location.lower(), description.lower()))
            duplicate = c.fetchone()
            
            if duplicate:
                flash("Duplicate Incident Detected. This emergency has already been reported.", "error")
                return redirect(url_for('report'))

        lat = request.form.get('lat')
        lng = request.form.get('lng')

        if lat and lng and lat.strip() != "" and lng.strip() != "":
            try:
                lat = float(lat)
                lng = float(lng)
            except ValueError:
                lat, lng = get_coordinates(location)
        else:
            lat, lng = get_coordinates(location)

        priority, insight = determine_priority(problem, description)

        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO reports (location, problem, description, priority, ai_insight, lat, lng, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending')",
                (location, problem, description, priority, insight, lat, lng)
            )
            conn.commit()

        flash("Emergency report successfully verified and submitted to the network logs.", "success")

        # Format problem back to title for UI string display locally
        return render_template(
            'result.html',
            location=location,
            problem=problem.title(),
            description=description,
            priority=priority,
            insight=insight,
            lat=lat,
            lng=lng
        )

    return render_template('report.html')

@app.route('/dashboard')
def dashboard():
    # Strict Authorization Checking
    if 'user_id' not in session:
        return redirect(url_for('login'))

    filter_category = request.args.get('category', 'All').lower()
    filter_priority = request.args.get('priority', 'All').upper()

    with get_db() as conn:
        c = conn.cursor()
        
        query = "SELECT location, problem, description, priority, ai_insight, lat, lng, status, id, created_at FROM reports WHERE 1=1"
        params = []
        
        if filter_category != 'all':
            query += " AND LOWER(problem) = ?"
            params.append(filter_category)
            
        if filter_priority != 'ALL':
            query += " AND priority = ?"
            params.append(filter_priority)
            
        query += " ORDER BY id DESC"
        
        c.execute(query, params)
        data = c.fetchall()
        
        # Fix Charts Issue requested - Fetch dynamically using GROUP BY for optimal speed instead of looping whole table
        c.execute("SELECT LOWER(problem), COUNT(*) FROM reports GROUP BY LOWER(problem)")
        cat_counts = c.fetchall()
        
        c.execute("SELECT priority, COUNT(*) FROM reports GROUP BY priority")
        pri_counts = c.fetchall()
        
        c.execute("SELECT COUNT(*) FROM reports WHERE status IN ('Pending', 'In Progress')")
        active_cases = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM reports WHERE priority = 'HIGH'")
        high_priority_count = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM reports")
        total_cases = c.fetchone()[0] or 0
    
    reports = []
    for row in data:
        reports.append({
            "location": row['location'] or 'Unknown',
            "problem": (row['problem'] or 'Unknown').title(),
            "description": row['description'] or 'No description',
            "priority": row['priority'] or 'LOW',
            "ai_insight": row['ai_insight'],
            "lat": float(row['lat']) if row['lat'] else None,
            "lng": float(row['lng']) if row['lng'] else None,
            "status": row['status'] or 'Pending',
            "id": row['id'],
            "created_at": row['created_at'] or 'Legacy Data'
        })

    cat_labels = [row[0].title() for row in cat_counts]
    cat_data = [row[1] for row in cat_counts]
    
    pri_labels = [row[0] for row in pri_counts]
    pri_data = [row[1] for row in pri_counts]

    last_updated = datetime.now().strftime("%I:%M:%S %p")

    return render_template(
        'dashboard.html',
        reports=reports,
        total_cases=total_cases,
        active_cases=active_cases,
        high_priority_count=high_priority_count,
        cat_labels=cat_labels,
        cat_data=cat_data,
        pri_labels=pri_labels,
        pri_data=pri_data,
        last_updated=last_updated,
        curr_category=(filter_category or 'All').title(),
        curr_priority=filter_priority or 'All'
    )

@app.route('/admin')
def admin():
    if session.get('role') != 'admin':
        flash("Unauthorized Target. You must login with administrator credentials.", "error")
        return redirect(url_for('login'))
        
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, location, problem, description, priority, ai_insight, status, created_at FROM reports ORDER BY id DESC")
        reports = [{"id": r['id'], "location": r['location'] or 'Unknown', "problem": (r['problem'] or 'Unknown').title(), "description": r['description'] or '', "priority": r['priority'] or 'LOW', "ai_insight": r['ai_insight'], "status": r['status'] or 'Pending', "created_at": r['created_at'] or 'Legacy Data'} for r in c.fetchall()]
        
    return render_template('admin.html', reports=reports)

@app.route('/update_status/<int:report_id>', methods=['POST'])
def update_status(report_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    new_status = request.form.get('status')
    if new_status in ['Pending', 'In Progress', 'Resolved']:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("UPDATE reports SET status = ? WHERE id = ?", (new_status, report_id))
            conn.commit()
            flash(f"Status for Node #{report_id} logically updated to '{new_status}'.", "success")
            
    return redirect(url_for('admin'))

# REAL-TIME POLLING API
@app.route('/api/count')
def api_count():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM reports")
        total = c.fetchone()[0]
    return jsonify({"count": total})

if __name__ == '__main__':
    app.run(debug=True)