from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import hashlib
import os

app = Flask(__name__, static_folder='static')
CORS(app)

DB_PATH = 'skillswap.db'

# ── Database Setup ──────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL,
            email    TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            bio      TEXT DEFAULT '',
            joined   TEXT DEFAULT (date('now'))
        );

        CREATE TABLE IF NOT EXISTS skills (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            skill   TEXT NOT NULL,
            type    TEXT NOT NULL CHECK(type IN ('offer','want')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')
    # Seed demo users
    demo = [
        ('Anika Reyes',   'anika@example.com',  'pass123', 'Designer & illustrator passionate about visual storytelling.',
         ['Graphic Design','Illustration','Figma'], ['Python','Data Analysis','Music Production']),
        ('Tomás Ferreira','tomas@example.com',  'pass123', 'Full-stack developer who loves building things that matter.',
         ['Python','React','SQL'], ['Photography','Spanish Cooking','Guitar']),
        ('Priya Nair',    'priya@example.com',  'pass123', 'Marketing strategist with a love for creative writing.',
         ['Content Writing','SEO','Social Media'], ['Web Development','Video Editing','French']),
        ('Kwame Asante',  'kwame@example.com',  'pass123', 'Music producer and audio engineer exploring tech.',
         ['Music Production','Audio Mixing','Logic Pro'], ['Graphic Design','Marketing','Photography']),
    ]
    for name, email, pwd, bio, offers, wants in demo:
        hashed = hash_password(pwd)
        try:
            cur.execute('INSERT INTO users (name,email,password,bio) VALUES (?,?,?,?)', (name,email,hashed,bio))
            uid = cur.lastrowid
            for s in offers:
                cur.execute('INSERT INTO skills (user_id,skill,type) VALUES (?,?,?)', (uid,s,'offer'))
            for s in wants:
                cur.execute('INSERT INTO skills (user_id,skill,type) VALUES (?,?,?)', (uid,s,'want'))
        except sqlite3.IntegrityError:
            pass  # already seeded
    conn.commit()
    conn.close()

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def user_dict(row, skills):
    return {
        'id':      row['id'],
        'name':    row['name'],
        'email':   row['email'],
        'bio':     row['bio'] or '',
        'joined':  row['joined'],
        'offering': [s['skill'] for s in skills if s['type'] == 'offer'],
        'wanting':  [s['skill'] for s in skills if s['type'] == 'want'],
    }

# ── Static Pages ────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# ── Auth Routes ─────────────────────────────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    name     = data.get('name','').strip()
    email    = data.get('email','').strip().lower()
    password = data.get('password','')
    bio      = data.get('bio','').strip()
    offering = [s.strip() for s in data.get('offering',[]) if s.strip()]
    wanting  = [s.strip() for s in data.get('wanting',[])  if s.strip()]

    if not name or not email or not password:
        return jsonify({'error': 'Name, email and password are required.'}), 400

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('INSERT INTO users (name,email,password,bio) VALUES (?,?,?,?)',
                    (name, email, hash_password(password), bio))
        uid = cur.lastrowid
        for s in offering:
            cur.execute('INSERT INTO skills (user_id,skill,type) VALUES (?,?,?)', (uid,s,'offer'))
        for s in wanting:
            cur.execute('INSERT INTO skills (user_id,skill,type) VALUES (?,?,?)', (uid,s,'want'))
        conn.commit()
        row    = cur.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        skills = cur.execute('SELECT * FROM skills WHERE user_id=?', (uid,)).fetchall()
        return jsonify({'message': 'Registered successfully!', 'user': user_dict(row, skills)}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Email already registered.'}), 409
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data  = request.json
    email = data.get('email','').strip().lower()
    pwd   = data.get('password','')
    conn  = get_db()
    cur   = conn.cursor()
    row   = cur.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if not row or row['password'] != hash_password(pwd):
        conn.close()
        return jsonify({'error': 'Invalid email or password.'}), 401
    skills = cur.execute('SELECT * FROM skills WHERE user_id=?', (row['id'],)).fetchall()
    conn.close()
    return jsonify({'message': 'Login successful!', 'user': user_dict(row, skills)})

# ── User Routes ─────────────────────────────────────────────────
@app.route('/api/users', methods=['GET'])
def get_users():
    query = request.args.get('search','').strip().lower()
    conn  = get_db()
    cur   = conn.cursor()
    if query:
        rows = cur.execute('''
            SELECT DISTINCT u.* FROM users u
            LEFT JOIN skills s ON s.user_id = u.id
            WHERE LOWER(u.name) LIKE ? OR LOWER(u.bio) LIKE ? OR LOWER(s.skill) LIKE ?
        ''', (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
    else:
        rows = cur.execute('SELECT * FROM users').fetchall()
    result = []
    for row in rows:
        skills = cur.execute('SELECT * FROM skills WHERE user_id=?', (row['id'],)).fetchall()
        result.append(user_dict(row, skills))
    conn.close()
    return jsonify(result)

@app.route('/api/users/<int:uid>', methods=['GET'])
def get_user(uid):
    conn   = get_db()
    cur    = conn.cursor()
    row    = cur.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'User not found.'}), 404
    skills = cur.execute('SELECT * FROM skills WHERE user_id=?', (uid,)).fetchall()
    conn.close()
    return jsonify(user_dict(row, skills))

@app.route('/api/users/<int:uid>', methods=['PUT'])
def update_user(uid):
    data     = request.json
    name     = data.get('name','').strip()
    bio      = data.get('bio','').strip()
    offering = [s.strip() for s in data.get('offering',[]) if s.strip()]
    wanting  = [s.strip() for s in data.get('wanting',[])  if s.strip()]

    if not name:
        return jsonify({'error': 'Name is required.'}), 400

    conn = get_db()
    cur  = conn.cursor()
    cur.execute('UPDATE users SET name=?, bio=? WHERE id=?', (name, bio, uid))
    cur.execute('DELETE FROM skills WHERE user_id=?', (uid,))
    for s in offering:
        cur.execute('INSERT INTO skills (user_id,skill,type) VALUES (?,?,?)', (uid,s,'offer'))
    for s in wanting:
        cur.execute('INSERT INTO skills (user_id,skill,type) VALUES (?,?,?)', (uid,s,'want'))
    conn.commit()
    row    = cur.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    skills = cur.execute('SELECT * FROM skills WHERE user_id=?', (uid,)).fetchall()
    conn.close()
    return jsonify({'message': 'Profile updated!', 'user': user_dict(row, skills)})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
