from flask import Flask, render_template, request, redirect, flash, session
import sqlite3
from datetime import datetime, timedelta
from flask import jsonify, request

app = Flask(__name__)
app.secret_key = "advanced_library_secret"

# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect("library.db")
    conn.row_factory = sqlite3.Row
    return conn
def create_tables():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO admin (id, username, password)
        VALUES (1, 'admin', 'admin123')
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            author TEXT,
            quantity INTEGER,
            status TEXT DEFAULT 'Available'
        )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS issued_books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER,
        student_name TEXT,
        student_class TEXT,
        roll_no TEXT,
        issue_date TEXT,
        return_date TEXT,
        returned INTEGER DEFAULT 0,
        FOREIGN KEY (book_id) REFERENCES books(id)
    )
""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no TEXT,
    student_class TEXT,
    full_name TEXT,
    contact TEXT,
    email TEXT
    )
    """)

    conn.commit()
    conn.close()
    
create_tables()


# ================= LOGIN =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM admin WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if user:
            session["admin"] = username
            return redirect("/dashboard")
        else:
            flash("Invalid Credentials!")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "admin" not in session:
        return redirect("/")

    conn = get_db()

    total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    
    issued_books = conn.execute(
        "SELECT COUNT(*) FROM issued_books WHERE returned=0"
        ).fetchone()[0]
    
    available_books = conn.execute(
        "SELECT SUM(quantity) FROM books"
        ).fetchone()[0]

    conn.close()

    return render_template("dashboard.html",
                           total=total_books,
                           issued=issued_books,
                           available=available_books)


@app.route('/books', methods=['GET','POST'])
def books():
    conn = get_db()

    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        quantity = request.form['quantity']

        conn.execute("""
            INSERT INTO books (title, author, quantity)
            VALUES (?, ?, ?)
        """, (title, author, quantity))

        conn.commit()
        conn.close()

        flash("Book Added Successfully!")
        return redirect('/books')

    books = conn.execute("SELECT * FROM books").fetchall()
    conn.close()

    return render_template('books.html', books=books)


# ================= ISSUE =================
@app.route("/issue/<int:id>", methods=["POST"])
def issue(id):
    conn = get_db()

    issue_date = datetime.now()
    return_date = issue_date + timedelta(minutes=1)

    conn.execute("""
        INSERT INTO issued_books (book_id, student_name, issue_date, return_date)
        VALUES (?, ?, ?, ?)
    """, (id, request.form["student"],
          issue_date.strftime("%Y-%m-%d %H:%M:%S"),
          return_date.strftime("%Y-%m-%d %H:%M:%S")))

    conn.execute("""
    UPDATE books
    SET quantity = quantity - 1
    WHERE id=?
    """, (id,))
    conn.commit()
    conn.close()

    flash("Book Issued Successfully!")
    return redirect("/books")

# ================= NOTIFICATIONS =================
@app.route("/notifications")
def notifications():
    if "admin" not in session:
        return redirect("/")

    conn = get_db()

    rows = conn.execute("""
        SELECT issued_books.id,
               books.title,
               issued_books.student_name,
               issued_books.return_date
        FROM issued_books
        JOIN books ON issued_books.book_id = books.id
        WHERE issued_books.returned = 0
    """).fetchall()

    notifications = []
    now = datetime.now()

    for row in rows:
        return_date = datetime.fromisoformat(row["return_date"])

        if now > return_date:
            overdue_minutes = int((now - return_date).total_seconds() // 60)
            fine = overdue_minutes * 2

            notifications.append({
                "title": row["title"],
                "student": row["student_name"],
                "minutes": overdue_minutes,
                "fine": fine
            })

    conn.close()
    return render_template("notifications.html", notifications=notifications)

# ================= ISSUE BOOK PAGE =================
@app.route("/issue-book", methods=["GET", "POST"])
def issue_book():
    if "admin" not in session:
        return redirect("/")

    conn = get_db()

    if request.method == "POST":

        book_id = request.form["book_id"]
        student_name = request.form["student_name"]
        student_class = request.form["student_class"]
        roll_no = request.form["roll_no"]

        issue_date = datetime.now()
        return_date = issue_date + timedelta(minutes=1)

        # Get book quantity
        book = conn.execute(
            "SELECT quantity FROM books WHERE id=?",
            (book_id,)
        ).fetchone()

        if book is None:
            flash("Book not found!")
            return redirect("/issue-book")

        if book["quantity"] <= 0:
            flash("No copies available!")
            return redirect("/issue-book")

        # Insert issued book
        conn.execute("""
            INSERT INTO issued_books
            (book_id, student_name, student_class, roll_no, issue_date, return_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            book_id,
            student_name,
            student_class,
            roll_no,
            issue_date.strftime("%Y-%m-%d %H:%M:%S"),
            return_date.strftime("%Y-%m-%d %H:%M:%S")
        ))

        # Reduce quantity
        conn.execute("""
            UPDATE books
            SET quantity = quantity - 1
            WHERE id=?
        """, (book_id,))

        conn.commit()
        conn.close()

        flash("Book Issued Successfully!")
        return redirect("/books")

    books = conn.execute(
        "SELECT * FROM books WHERE quantity > 0"
    ).fetchall()

    conn.close()

    return render_template("issue_book.html", books=books)

# ================= ISSUED BOOKS =================
@app.route("/issued-books")
def issued_books_list():
    if "admin" not in session:
        return redirect("/")

    conn = get_db()

    rows = conn.execute("""
        SELECT issued_books.id,
               books.title,
               issued_books.student_name,
               issued_books.student_class,
               issued_books.roll_no,
               issued_books.issue_date,
               issued_books.return_date
        FROM issued_books
        JOIN books ON issued_books.book_id = books.id
        WHERE issued_books.returned = 0
        ORDER BY issued_books.issue_date DESC
    """).fetchall()

    conn.close()

    return render_template("issued_books.html", books=rows)

#======================Student==================
@app.route('/students', methods=['GET', 'POST'])
def students():
    conn = sqlite3.connect('library.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'POST':
        roll_no = request.form['roll_no']
        student_class = request.form['student_class']
        full_name = request.form['full_name']
        contact = request.form['contact']
        email = request.form['email']

        cursor.execute("""
            INSERT INTO students 
            (roll_no, student_class, full_name, contact, email)
            VALUES (?, ?, ?, ?, ?)
        """, (roll_no, student_class, full_name, contact, email))

        conn.commit()
        flash("Student Added Successfully!")
        return redirect('/students')

    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()
    conn.close()

    return render_template('students.html', students=students)

@app.route('/get-student')
def get_student():
    roll_no = request.args.get('roll_no', '').strip()
    student_class = request.args.get('student_class', '').strip()

    conn = get_db()

    student = conn.execute("""
        SELECT * FROM students
        WHERE roll_no = ?
        AND LOWER(student_class) = LOWER(?)
    """, (roll_no, student_class)).fetchone()

    conn.close()

    if student:
        return jsonify({
            "full_name": student["full_name"],
            "contact": student["contact"],
            "email": student["email"]
        })
    else:
        return jsonify({})
    
#===============Return button================#
@app.route("/return_book/<int:id>")
def return_book_action(id):

    if "admin" not in session:
        return redirect("/")

    conn = get_db()

    book = conn.execute(
        "SELECT book_id FROM issued_books WHERE id=?",
        (id,)
    ).fetchone()

    conn.execute(
        "UPDATE issued_books SET returned=1 WHERE id=?",
        (id,)
    )

    conn.execute(
        "UPDATE books SET quantity = quantity + 1 WHERE id=?",
        (book["book_id"],)
    )

    conn.commit()
    conn.close()

    return redirect("/issued-books")
    
if __name__ == "__main__":
    app.run(debug=True)