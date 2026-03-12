from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mysecretkey123')

DATABASE = 'results.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                roll_no  TEXT UNIQUE NOT NULL,
                name     TEXT NOT NULL,
                email    TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                class    TEXT NOT NULL,
                created  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                subject    TEXT NOT NULL,
                marks      INTEGER NOT NULL,
                max_marks  INTEGER NOT NULL DEFAULT 100,
                exam_type  TEXT NOT NULL DEFAULT 'Mid Term',
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        ''')

        existing = conn.execute("SELECT * FROM admins WHERE username='admin'").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO admins (username, password) VALUES (?, ?)",
                ('admin', generate_password_hash('admin123'))
            )

        existing_student = conn.execute("SELECT * FROM students WHERE roll_no='STU001'").fetchone()
        if not existing_student:
            conn.execute(
                "INSERT INTO students (roll_no, name, email, password, class) VALUES (?, ?, ?, ?, ?)",
                ('STU001', 'Demo Student', 'demo@student.com',
                 generate_password_hash('student123'), '10th Grade')
            )
            student = conn.execute("SELECT id FROM students WHERE roll_no='STU001'").fetchone()
            subjects = [
                ('Mathematics', 85, 100),
                ('Science', 78, 100),
                ('English', 92, 100),
                ('Social Studies', 70, 100),
                ('Computer Science', 95, 100),
            ]
            for sub, marks, max_marks in subjects:
                conn.execute(
                    "INSERT INTO results (student_id, subject, marks, max_marks, exam_type) VALUES (?, ?, ?, ?, ?)",
                    (student['id'], sub, marks, max_marks, 'Final Exam')
                )
        conn.commit()


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required!', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'student':
            flash('Please login as student!', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/')
def index():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    if session.get('role') == 'student':
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role     = request.form['role']
        username = request.form['username'].strip()
        password = request.form['password']

        if role == 'admin':
            with get_db() as conn:
                admin = conn.execute(
                    "SELECT * FROM admins WHERE username=?", (username,)
                ).fetchone()
            if admin and check_password_hash(admin['password'], password):
                session['user_id']  = admin['id']
                session['username'] = admin['username']
                session['role']     = 'admin'
                flash('Welcome Admin!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin credentials!', 'danger')

        elif role == 'student':
            with get_db() as conn:
                student = conn.execute(
                    "SELECT * FROM students WHERE roll_no=?", (username,)
                ).fetchone()
            if student and check_password_hash(student['password'], password):
                session['user_id']  = student['id']
                session['username'] = student['name']
                session['roll_no']  = student['roll_no']
                session['role']     = 'student'
                flash(f'Welcome, {student["name"]}!', 'success')
                return redirect(url_for('student_dashboard'))
            else:
                flash('Invalid Roll No or Password!', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('login'))


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    with get_db() as conn:
        students       = conn.execute("SELECT * FROM students ORDER BY created DESC").fetchall()
        total_students = len(students)
        total_results  = conn.execute("SELECT COUNT(*) as c FROM results").fetchone()['c']
    return render_template('admin_dashboard.html',
                           students=students,
                           total_students=total_students,
                           total_results=total_results)


@app.route('/admin/add_student', methods=['GET', 'POST'])
@admin_required
def add_student():
    if request.method == 'POST':
        roll_no  = request.form['roll_no'].strip().upper()
        name     = request.form['name'].strip()
        email    = request.form['email'].strip().lower()
        password = request.form['password']
        cls      = request.form['class'].strip()

        if not all([roll_no, name, email, password, cls]):
            flash('All fields are required!', 'danger')
            return render_template('add_student.html')

        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO students (roll_no, name, email, password, class) VALUES (?,?,?,?,?)",
                    (roll_no, name, email, generate_password_hash(password), cls)
                )
                conn.commit()
            flash(f'Student {name} added successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except sqlite3.IntegrityError:
            flash('Roll No or Email already exists!', 'danger')

    return render_template('add_student.html')


@app.route('/admin/add_result/<int:student_id>', methods=['GET', 'POST'])
@admin_required
def add_result(student_id):
    with get_db() as conn:
        student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()

    if not student:
        flash('Student not found!', 'danger')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        subject   = request.form['subject'].strip()
        marks     = int(request.form['marks'])
        max_marks = int(request.form['max_marks'])
        exam_type = request.form['exam_type']

        if marks > max_marks:
            flash('Marks cannot exceed Max Marks!', 'danger')
            return render_template('add_result.html', student=student)

        with get_db() as conn:
            conn.execute(
                "INSERT INTO results (student_id, subject, marks, max_marks, exam_type) VALUES (?,?,?,?,?)",
                (student_id, subject, marks, max_marks, exam_type)
            )
            conn.commit()
        flash(f'Result added for {student["name"]}!', 'success')
        return redirect(url_for('view_student', student_id=student_id))

    return render_template('add_result.html', student=student)


@app.route('/admin/student/<int:student_id>')
@admin_required
def view_student(student_id):
    with get_db() as conn:
        student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
        results = conn.execute("SELECT * FROM results WHERE student_id=?", (student_id,)).fetchall()
    if not student:
        flash('Student not found!', 'danger')
        return redirect(url_for('admin_dashboard'))
    stats = calculate_stats(results)
    return render_template('view_result.html', student=student, results=results, stats=stats, role='admin')


@app.route('/admin/delete_student/<int:student_id>')
@admin_required
def delete_student(student_id):
    with get_db() as conn:
        conn.execute("DELETE FROM results WHERE student_id=?", (student_id,))
        conn.execute("DELETE FROM students WHERE id=?", (student_id,))
        conn.commit()
    flash('Student deleted!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/student/dashboard')
@student_required
def student_dashboard():
    with get_db() as conn:
        student = conn.execute("SELECT * FROM students WHERE id=?", (session['user_id'],)).fetchone()
        results = conn.execute("SELECT * FROM results WHERE student_id=?", (session['user_id'],)).fetchall()
    stats = calculate_stats(results)
    return render_template('student_dashboard.html', student=student, results=results, stats=stats)


@app.route('/student/result')
@student_required
def student_result():
    with get_db() as conn:
        student = conn.execute("SELECT * FROM students WHERE id=?", (session['user_id'],)).fetchone()
        results = conn.execute("SELECT * FROM results WHERE student_id=?", (session['user_id'],)).fetchall()
    stats = calculate_stats(results)
    return render_template('view_result.html', student=student, results=results, stats=stats, role='student')


def calculate_stats(results):
    if not results:
        return {'total': 0, 'max_total': 0, 'percentage': 0, 'grade': 'N/A', 'passed': False}
    total      = sum(r['marks'] for r in results)
    max_total  = sum(r['max_marks'] for r in results)
    percentage = round((total / max_total) * 100, 2) if max_total else 0
    if percentage >= 90:   grade = 'A+'
    elif percentage >= 80: grade = 'A'
    elif percentage >= 70: grade = 'B+'
    elif percentage >= 60: grade = 'B'
    elif percentage >= 50: grade = 'C'
    elif percentage >= 35: grade = 'D'
    else:                  grade = 'F'
    passed = percentage >= 35
    return {
        'total': total, 'max_total': max_total,
        'percentage': percentage, 'grade': grade, 'passed': passed
    }


if __name__ == '__main__':
    init_db()
    app.run(debug=True)