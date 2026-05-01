import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "ultimate_warehouse_key_2026"

# --- DATABASE LOGIC ---
def get_db_connection():
    conn = sqlite3.connect('inventory.db', timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                min_limit INTEGER NOT NULL DEFAULT 5,
                buy_price REAL DEFAULT 0.0,
                sell_price REAL DEFAULT 0.0
            );
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT,
                action TEXT,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        conn.commit()

init_db()

def log_action(conn, action, details):
    user = session.get('user', 'System')
    conn.execute('INSERT INTO logs (user_name, action, details) VALUES (?, ?, ?)',
                 (user, action, details))

# --- AUTH ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        with get_db_connection() as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (u,)).fetchone()
            if user and check_password_hash(user['password'], p):
                session['user'] = u
                return redirect(url_for('index'))
        flash("Λάθος στοιχεία!")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, p = request.form['username'], generate_password_hash(request.form['password'])
        with get_db_connection() as conn:
            try:
                conn.execute('INSERT INTO users (username, password) VALUES (?,?)', (u, p))
                conn.commit()
                return redirect(url_for('login'))
            except: flash("Ο χρήστης υπάρχει ήδη!")
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- MAIN INVENTORY ROUTES ---
@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    with get_db_connection() as conn:
        items = conn.execute('SELECT * FROM items ORDER BY id DESC').fetchall()
        # Παίρνουμε όλα τα logs για να λειτουργήσει το scrollbar
        history = conn.execute('SELECT * FROM logs ORDER BY timestamp DESC').fetchall()
        total_val = conn.execute('SELECT SUM(qty * buy_price) FROM items').fetchone()[0] or 0
    return render_template('index.html', items=items, history=history, total_value=total_val)

@app.route('/update_stock', methods=['POST'])
def update_stock():
    if 'user' not in session: return redirect(url_for('login'))
    code, name = request.form['code'], request.form['item']
    qty = int(request.form.get('quantity') or 0)
    limit = int(request.form.get('min_limit') or 5)
    buy = float(request.form.get('buy_price') or 0)
    sell = float(request.form.get('sell_price') or 0)

    with get_db_connection() as conn:
        existing = conn.execute('SELECT * FROM items WHERE code = ?', (code,)).fetchone()
        if existing:
            conn.execute('UPDATE items SET name=?, qty=?, min_limit=?, buy_price=?, sell_price=? WHERE code=?',
                         (name, qty, limit, buy, sell, code))
            log_action(conn, "UPDATE", f"Προϊόν: {name}")
        else:
            conn.execute('INSERT INTO items (code, name, qty, min_limit, buy_price, sell_price) VALUES (?,?,?,?,?,?)',
                         (code, name, qty, limit, buy, sell))
            log_action(conn, "INSERT", f"Νέο Είδος: {name}")
        conn.commit()
    return redirect(url_for('index'))

@app.route('/quick_update/<int:id>/<action>')
def quick_update(id, action):
    if 'user' not in session: return redirect(url_for('login'))
    with get_db_connection() as conn:
        item = conn.execute('SELECT name FROM items WHERE id = ?', (id,)).fetchone()
        if action == 'add':
            conn.execute('UPDATE items SET qty = qty + 1 WHERE id = ?', (id,))
            log_action(conn, "STOCK +1", f"Προϊόν: {item['name'] if item else id}")
        elif action == 'sub':
            conn.execute('UPDATE items SET qty = MAX(0, qty - 1) WHERE id = ?', (id,))
            log_action(conn, "STOCK -1", f"Προϊόν: {item['name'] if item else id}")
        conn.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete_item(id):
    if 'user' not in session: return redirect(url_for('login'))
    with get_db_connection() as conn:
        conn.execute('DELETE FROM items WHERE id = ?', (id,))
        conn.commit()
    return redirect(url_for('index'))

@app.route('/get_item_details/<code>')
def get_item_details(code):
    with get_db_connection() as conn:
        item = conn.execute('SELECT * FROM items WHERE code = ?', (code,)).fetchone()
        if item:
            return jsonify({'exists': True, 'name': item['name'], 'qty': item['qty'], 
                            'min_limit': item['min_limit'], 'buy_price': item['buy_price'], 
                            'sell_price': item['sell_price']})
    return jsonify({'exists': False})

if __name__ == '__main__':
    app.run(debug=True)