from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from functools import wraps
from pymongo import MongoClient
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import calendar as cal_module
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

SECURITY_QUESTIONS = [
    "What is your mother's maiden name?",
    "What was the name of your first pet?",
    "What city were you born in?",
]
app.secret_key = os.getenv("SECRET_KEY")

client = MongoClient(os.getenv("MONGO_URI"))
db = client["type-db"]
ap_collection = db["appointments"]
task_collection = db["tasks"]
req_collection = db["requests"]
tick_collection = db["tickets"]
users_collection = db["users"]
feedback_collection = db["feedback"]
demo_logs = db["demo_logs"]


# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


def demo_readonly(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("is_demo"):
            if request.is_json:
                return jsonify({"error": "Demo mode — changes are disabled."}), 403
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


def get_labels():
    mode = session.get("mode", "work")
    if mode == "school":
        req_plural = session.get("request_label", "Projects")
        req_single = {"Projects": "Project", "Labs": "Lab"}.get(req_plural, "Project")
        return {
            "mode":             "school",
            "tasks":            "Homework",
            "requests":         req_plural,
            "tickets":          "Exams",
            "appointments":     "Schedule",
            "my_work":          "Timeline",
            "task_singular":    "Homework",
            "request_singular": req_single,
            "ticket_singular":  "Exam",
            "create_title":     "Add New",
            "create_sub":       f"Add homework, a {req_single.lower()}, or an exam",
        }
    return {
        "mode":             "work",
        "tasks":            "Tasks",
        "requests":         "Requests",
        "tickets":          "Tickets",
        "appointments":     "Appointments",
        "my_work":          "My Work",
        "task_singular":    "Task",
        "request_singular": "Request",
        "ticket_singular":  "Ticket",
        "create_title":     "Create Item",
        "create_sub":       "Add a new task, request, or ticket",
    }


@app.context_processor
def inject_user():
    return {
        "current_username": session.get("username", ""),
        "current_role": session.get("role", ""),
        "is_demo": session.get("is_demo", False),
        "user_mode": session.get("mode", "work"),
        "labels": get_labels(),
    }


@app.template_filter('fmtdate')
def fmt_date(value):
    if not value:
        return '—'
    try:
        y, m, d = str(value).strip().split('-')
        return f"{m}/{d}/{y}"
    except Exception:
        return value or '—'


def get_assignable_usernames():
    role = session.get("role")
    username = session.get("username")
    user_id_str = session.get("user_id")

    if not role or not username:
        return [username] if username else []

    if session.get("is_demo"):
        if role == "admin":
            return [u["username"] for u in users_collection.find({}, {"username": 1})]
        return [username]

    if role == "admin":
        user_id = ObjectId(user_id_str)
        team = users_collection.find({"manager_id": user_id}, {"username": 1})
        names = [username] + [u["username"] for u in team]
        return names

    elif role == "user":
        manager_id_str = session.get("manager_id")
        if manager_id_str:
            manager_id = ObjectId(manager_id_str)
            peers = users_collection.find(
                {"manager_id": manager_id, "role": {"$in": ["user", "low"]}},
                {"username": 1}
            )
            names = [username] + [u["username"] for u in peers if u["username"] != username]
        else:
            names = [username]
        return names

    else:  # low
        return [username]


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/")
def start_index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = users_collection.find_one({"username": username})
        if not user:
            error = "Invalid username or password."
        elif "password" not in user or not user["password"]:
            # First-time setup — no password set yet
            session["setup_user_id"] = str(user["_id"])
            return redirect(url_for("set_password"))
        elif not check_password_hash(user["password"], password):
            error = "Invalid username or password."
        else:
            session["username"] = user["username"]
            session["role"] = user.get("role", "user")
            session["user_id"] = str(user["_id"])
            session["mode"] = user.get("mode", "work")
            session["request_label"] = user.get("request_label", "Requests")
            manager_id = user.get("manager_id")
            session["manager_id"] = str(manager_id) if manager_id else None
            return redirect(url_for("dashboard"))

    return render_template("login.html", error=error)


@app.route("/set-password", methods=["GET", "POST"])
def set_password():
    setup_user_id = session.get("setup_user_id")
    if not setup_user_id:
        return redirect(url_for("login"))

    user = users_collection.find_one({"_id": ObjectId(setup_user_id)})
    if not user:
        session.pop("setup_user_id", None)
        return redirect(url_for("login"))

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            hashed = generate_password_hash(password)
            users_collection.update_one(
                {"_id": ObjectId(setup_user_id)},
                {"$set": {"password": hashed}}
            )
            session.pop("setup_user_id", None)
            session["username"] = user["username"]
            session["role"] = user.get("role", "user")
            session["user_id"] = str(user["_id"])
            session["mode"] = user.get("mode", "work")
            session["request_label"] = user.get("request_label", "Requests")
            manager_id = user.get("manager_id")
            session["manager_id"] = str(manager_id) if manager_id else None
            return redirect(url_for("dashboard"))

    return render_template("set_password.html", username=user["username"], error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        username  = request.form.get("username", "").strip()
        password  = request.form.get("password", "")
        confirm   = request.form.get("confirm_password", "")
        sec_q     = request.form.get("security_question", "").strip()
        sec_a     = request.form.get("security_answer", "").strip()

        mode          = request.form.get("mode", "work")
        request_label = request.form.get("request_label", "Projects") if mode == "school" else "Requests"

        if not username:
            error = "Username is required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif sec_q not in SECURITY_QUESTIONS:
            error = "Please select a security question."
        elif not sec_a:
            error = "Please provide an answer to your security question."
        elif mode not in ("work", "school"):
            error = "Invalid mode selected."
        elif users_collection.find_one({"username": username}):
            error = "That username is already taken."
        else:
            users_collection.insert_one({
                "username":        username,
                "password":        generate_password_hash(password),
                "role":            "user",
                "security_question": sec_q,
                "security_answer":   generate_password_hash(sec_a.lower()),
                "mode":            mode,
                "request_label":   request_label,
            })
            return redirect(url_for("login"))

    return render_template("register.html", error=error, security_questions=SECURITY_QUESTIONS)


@app.route("/demo/<role>")
def demo_access(role):
    if role not in ("user", "admin"):
        return redirect(url_for("login"))
    demo_logs.insert_one({
        "role": role,
        "accessed_at": datetime.utcnow().isoformat(),
        "ip": request.remote_addr
    })
    session.clear()
    session["username"] = "Demo " + role.capitalize()
    session["role"] = role
    session["user_id"] = "demo"
    session["manager_id"] = None
    session["is_demo"] = True
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _token_serializer():
    return URLSafeTimedSerializer(app.secret_key)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        user = users_collection.find_one({"username": username})
        if user and user.get("security_question"):
            session["reset_username"] = username
            return redirect(url_for("verify_security"))
        elif user:
            # No security question — ask them to set one first
            session["reset_username"] = username
            session["reset_needs_setup"] = True
            return redirect(url_for("verify_security"))
        else:
            error = "No account found with that username."
    return render_template("forgot_password.html", reset_link=None, error=error)


@app.route("/verify-security", methods=["GET", "POST"])
def verify_security():
    username = session.get("reset_username")
    if not username:
        return redirect(url_for("forgot_password"))

    user = users_collection.find_one({"username": username})
    if not user:
        session.pop("reset_username", None)
        session.pop("reset_needs_setup", None)
        return redirect(url_for("forgot_password"))

    # ── Setup mode: user has no security question yet ──────────────────────────
    if session.get("reset_needs_setup"):
        error = None
        if request.method == "POST":
            sec_q = request.form.get("security_question", "").strip()
            sec_a = request.form.get("security_answer", "").strip()
            if sec_q not in SECURITY_QUESTIONS:
                error = "Please select a valid security question."
            elif not sec_a:
                error = "Please provide an answer."
            else:
                users_collection.update_one({"username": username}, {"$set": {
                    "security_question": sec_q,
                    "security_answer":   generate_password_hash(sec_a.lower()),
                }})
                session.pop("reset_needs_setup", None)
                session.pop("reset_username", None)
                token = _token_serializer().dumps(str(user["_id"]), salt="pw-reset")
                reset_link = url_for("reset_password", token=token, _external=True)
                return render_template("verify_security.html",
                    setup_mode=False, reset_link=reset_link, locked=False)
        return render_template("verify_security.html",
            setup_mode=True,
            security_questions=SECURITY_QUESTIONS,
            error=error,
            locked=False)

    # ── Verify mode: user already has a security question ─────────────────────
    locked_until = user.get("security_locked_until")
    if locked_until and datetime.utcnow() < locked_until:
        mins = max(1, int((locked_until - datetime.utcnow()).total_seconds() / 60) + 1)
        return render_template("verify_security.html",
            setup_mode=False,
            question=user["security_question"],
            error=f"Account locked. Try again in {mins} minute(s).",
            locked=True)
    elif locked_until:
        users_collection.update_one({"username": username},
            {"$unset": {"security_locked_until": "", "security_attempts": ""}})

    error = None
    if request.method == "POST":
        answer = request.form.get("answer", "").strip().lower()
        if check_password_hash(user.get("security_answer", ""), answer):
            session.pop("reset_username", None)
            users_collection.update_one({"username": username},
                {"$unset": {"security_attempts": ""}})
            token = _token_serializer().dumps(str(user["_id"]), salt="pw-reset")
            reset_link = url_for("reset_password", token=token, _external=True)
            return render_template("verify_security.html",
                setup_mode=False,
                question=user["security_question"],
                reset_link=reset_link,
                locked=False)
        else:
            attempts = user.get("security_attempts", 0) + 1
            if attempts >= 3:
                lock_until = datetime.utcnow() + timedelta(minutes=15)
                users_collection.update_one({"username": username}, {"$set": {
                    "security_locked_until": lock_until,
                    "security_attempts": attempts
                }})
                session.pop("reset_username", None)
                return render_template("verify_security.html",
                    setup_mode=False,
                    question=user["security_question"],
                    error="Too many incorrect attempts. Account locked for 15 minutes.",
                    locked=True)
            else:
                users_collection.update_one({"username": username},
                    {"$set": {"security_attempts": attempts}})
                remaining = 3 - attempts
                error = f"Incorrect answer. {remaining} attempt(s) remaining."

    return render_template("verify_security.html",
        setup_mode=False,
        question=user["security_question"],
        error=error,
        locked=False)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        user_id_str = _token_serializer().loads(token, salt="pw-reset", max_age=3600)
    except (SignatureExpired, BadSignature):
        return render_template("forgot_password.html", error="This reset link has expired or is invalid. Please request a new one.")

    user = users_collection.find_one({"_id": ObjectId(user_id_str)})
    if not user:
        return redirect(url_for("forgot_password"))

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"password": generate_password_hash(password)}}
            )
            return redirect(url_for("login"))

    return render_template("reset_password.html", token=token, username=user["username"], error=error)


# ── Existing routes (all protected) ──────────────────────────────────────────

@app.route("/openTasks")
@login_required
def open_tasks():
    role = session.get("role")
    username = session.get("username")
    assignable_users = get_assignable_usernames()

    if role == "low":
        tasks = list(task_collection.find({"assigned": username}))
    else:
        tasks = list(task_collection.find())

    for t in tasks:
        t["_id"] = str(t["_id"])

    lbl = get_labels()
    return render_template("items.html", items=tasks, title=lbl["tasks"], item_type="Task", assignable_users=assignable_users)


@app.route("/openTickets")
@login_required
def open_tickets():
    role = session.get("role")
    username = session.get("username")
    assignable_users = get_assignable_usernames()

    if role == "low":
        tickets = list(tick_collection.find({"assigned": username}))
    else:
        tickets = list(tick_collection.find())

    for t in tickets:
        t["_id"] = str(t["_id"])

    lbl = get_labels()
    return render_template("items.html", items=tickets, title=lbl["tickets"], item_type="Ticket", assignable_users=assignable_users)


@app.route("/openRequests")
@login_required
def open_requests():
    role = session.get("role")
    username = session.get("username")
    assignable_users = get_assignable_usernames()

    if role == "low":
        requests_data = list(req_collection.find({"assigned": username}))
    else:
        requests_data = list(req_collection.find())

    for r in requests_data:
        r["_id"] = str(r["_id"])

    lbl = get_labels()
    return render_template("items.html", items=requests_data, title=lbl["requests"], item_type="Request", assignable_users=assignable_users)


@app.route("/create")
@login_required
def creation():
    assignable_users = get_assignable_usernames()
    current_username = session.get("username")
    default_type = request.args.get("type", "Task")
    if default_type not in ("Task", "Request", "Ticket"):
        default_type = "Task"
    return render_template("creation.html", assignable_users=assignable_users, current_username=current_username, default_type=default_type)


@app.route("/create_item", methods=["POST"])
@login_required
@demo_readonly
def create_item():
    item_type = request.form.get("type")

    item_data = {
        "assigned": request.form.get("assigned"),
        "status": request.form.get("status"),
        "priority": request.form.get("priority", "Medium"),
        "description": request.form.get("description"),
        "created": request.form.get("created"),
        "due": request.form.get("due"),
        "created_by": session.get("username")
    }

    if item_type == "Task":
        task_collection.insert_one(item_data)
        return redirect(url_for("open_tasks"))

    elif item_type == "Request":
        req_collection.insert_one(item_data)
        return redirect(url_for("open_requests"))

    elif item_type == "Ticket":
        tick_collection.insert_one(item_data)
        return redirect(url_for("open_tickets"))

    return redirect(url_for("creation"))


@app.route("/appointments")
@login_required
def appointments():
    username = session.get("username")
    assignable_users = get_assignable_usernames()
    now = datetime.today()
    today_str = now.strftime("%Y-%m-%d")

    # Parse requested month from query params, clamp to ±2 months from today
    try:
        view_year  = int(request.args.get("year",  now.year))
        view_month = int(request.args.get("month", now.month))
        view_date  = datetime(view_year, view_month, 1)
    except (ValueError, TypeError):
        view_date = datetime(now.year, now.month, 1)

    min_date = datetime(now.year, now.month, 1)
    # shift by -2 months
    m = min_date.month - 2
    y = min_date.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    min_date = datetime(y, m, 1)

    max_date = datetime(now.year, now.month, 1)
    # shift by +2 months
    m = max_date.month + 2
    y = max_date.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    max_date = datetime(y, m, 1)

    if view_date < min_date:
        view_date = min_date
    if view_date > max_date:
        view_date = max_date

    view_year  = view_date.year
    view_month = view_date.month
    month_str  = view_date.strftime("%Y-%m")

    # Prev / next month links
    def shift_month(year, month, delta):
        m = month + delta
        y = year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        return y, m

    prev_year, prev_month = shift_month(view_year, view_month, -1)
    next_year, next_month = shift_month(view_year, view_month, +1)

    prev_date = datetime(prev_year, prev_month, 1)
    next_date = datetime(next_year, next_month, 1)

    has_prev = prev_date >= min_date
    has_next = next_date <= max_date

    # Upcoming: always from today forward, filtered by user
    upcoming_all = list(ap_collection.find({"date": {"$gte": today_str}}).sort("date", 1))
    upcoming = [
        a for a in upcoming_all
        if "created_by" not in a
        or a.get("created_by") == username
        or a.get("invite") == username
    ]
    for a in upcoming:
        a["_id"] = str(a["_id"])

    # Calendar appointments for the viewed month
    month_appts_all = list(ap_collection.find({"date": {"$regex": f"^{month_str}"}}))
    month_appts = [
        a for a in month_appts_all
        if "created_by" not in a
        or a.get("created_by") == username
        or a.get("invite") == username
    ]

    appt_by_day = {}
    for a in month_appts:
        if a.get("date"):
            try:
                day = int(a["date"].split("-")[2])
                label = a.get("title") or a.get("description") or "Appointment"
                appt_by_day.setdefault(day, []).append(label)
            except Exception:
                pass

    cal = cal_module.Calendar(firstweekday=6)
    cal_weeks = cal.monthdayscalendar(view_year, view_month)

    # today_day only highlights if we're viewing the current month
    today_day = now.day if (view_year == now.year and view_month == now.month) else -1

    all_users = [u["username"] for u in users_collection.find({}, {"username": 1})]

    return render_template("appointments.html",
        appointments=upcoming,
        cal_weeks=cal_weeks,
        month_name=view_date.strftime("%B %Y"),
        today_day=today_day,
        appt_by_day=appt_by_day,
        assignable_users=assignable_users,
        all_users=all_users,
        has_prev=has_prev,
        has_next=has_next,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
    )


@app.route("/create_appointment", methods=["POST"])
@login_required
@demo_readonly
def create_appointment():
    data = {
        "title":       request.form.get("title"),
        "date":        request.form.get("date"),
        "start_time":  request.form.get("start_time"),
        "end_time":    request.form.get("end_time"),
        "invite":      request.form.get("invite"),
        "description": request.form.get("description"),
        "created_by":  session.get("username")
    }
    ap_collection.insert_one(data)
    return redirect(url_for("appointments"))


@app.route("/update_appointment", methods=["POST"])
@login_required
@demo_readonly
def update_appointment():
    data = request.get_json()
    appt_id = data.get("id")
    if not appt_id:
        return jsonify({"error": "Missing ID"}), 400
    ap_collection.update_one(
        {"_id": ObjectId(appt_id)},
        {"$set": {
            "title":       data.get("title"),
            "date":        data.get("date"),
            "start_time":  data.get("start_time"),
            "end_time":    data.get("end_time"),
            "invite":      data.get("invite"),
            "description": data.get("description")
        }}
    )
    return jsonify({"success": True})


@app.route("/delete_appointment", methods=["POST"])
@login_required
@demo_readonly
def delete_appointment():
    data = request.get_json()
    ap_collection.delete_one({"_id": ObjectId(data.get("id"))})
    return jsonify({"success": True})


@app.route("/delete_item", methods=["POST"])
@login_required
@demo_readonly
def delete_item():
    data = request.json
    item_id = data.get("id")

    for collection in [task_collection, tick_collection, req_collection]:
        result = collection.delete_one({"_id": ObjectId(item_id)})
        if result.deleted_count > 0:
            break

    return jsonify({"success": True})


@app.route("/update_item", methods=["POST"])
@login_required
@demo_readonly
def update_item():
    data = request.get_json()
    item_id = data.get("id")

    if not item_id:
        return jsonify({"error": "Missing ID"}), 400

    updated_data = {
        "description": data.get("description"),
        "status":      data.get("status"),
        "priority":    data.get("priority"),
        "assigned":    data.get("assigned"),
        "created":     data.get("created"),
        "due":         data.get("due")
    }

    for collection in [task_collection, tick_collection, req_collection]:
        result = collection.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": updated_data}
        )
        if result.modified_count > 0:
            return jsonify({"success": True})

    return jsonify({"error": "Item not found"}), 404


@app.route("/assigned")
@login_required
def assigned_tasks():
    username = session.get("username")
    assignable_users = get_assignable_usernames()

    tasks = list(task_collection.find({"assigned": username}))
    tickets = list(tick_collection.find({"assigned": username}))
    requests_data = list(req_collection.find({"assigned": username}))

    for item in tasks + tickets + requests_data:
        item["_id"] = str(item["_id"])

    return render_template(
        "assigned.html",
        tasks=tasks,
        tickets=tickets,
        requests=requests_data,
        assignable_users=assignable_users
    )


@app.route("/Dashboard")
@login_required
def dashboard():
    open_tasks = task_collection.count_documents({"status": "Open"})
    open_requests = req_collection.count_documents({"status": "Open"})
    open_tickets = tick_collection.count_documents({"status": "Open"})

    in_progress = (
        task_collection.count_documents({"status": "In Progress"}) +
        req_collection.count_documents({"status": "In Progress"}) +
        tick_collection.count_documents({"status": "In Progress"})
    )

    completed = (
        task_collection.count_documents({"status": "Completed"}) +
        req_collection.count_documents({"status": "Completed"}) +
        tick_collection.count_documents({"status": "Completed"})
    )

    total_all = open_tasks + open_requests + open_tickets + in_progress + completed

    recent_items = []
    for coll, type_label in [(task_collection, "Task"), (req_collection, "Request"), (tick_collection, "Ticket")]:
        for item in coll.find().sort("_id", -1).limit(3):
            item["_id"] = str(item["_id"])
            item["type_label"] = type_label
            recent_items.append(item)
    recent_items.sort(key=lambda x: x["_id"], reverse=True)
    recent_items = recent_items[:6]

    return render_template(
        "dashboard.html",
        open_tasks=open_tasks,
        open_requests=open_requests,
        open_tickets=open_tickets,
        in_progress=in_progress,
        completed=completed,
        total_all=total_all,
        recent_items=recent_items
    )


@app.route("/feedback")
@login_required
def feedback():
    return render_template("feedback.html")


@app.route("/submit_feedback", methods=["POST"])
@login_required
@demo_readonly
def submit_feedback():
    data = request.get_json(silent=True) or {}
    rating   = data.get("rating", "")
    fb_text  = data.get("feedback", "").strip()
    if not rating or not fb_text:
        return jsonify({"error": "Missing fields"}), 400
    feedback_collection.insert_one({
        "rating": int(rating),
        "feedback": fb_text,
        "submitted_by": session.get("username"),
        "submitted_at": datetime.utcnow().isoformat()
    })
    return jsonify({"success": True})


@app.route("/admin")
@admin_required
def admin_panel():
    users = list(users_collection.find({}, {"password": 0}))
    for u in users:
        u["_id"] = str(u["_id"])
        if u.get("manager_id"):
            u["manager_id"] = str(u["manager_id"])

    all_feedback = list(feedback_collection.find().sort("submitted_at", -1))
    for f in all_feedback:
        f["_id"] = str(f["_id"])

    return render_template("admin.html",
        users=users,
        all_feedback=all_feedback,
        total_users=len(users),
        total_tasks=task_collection.count_documents({}),
        total_requests=req_collection.count_documents({}),
        total_tickets=tick_collection.count_documents({}),
        current_user_id=session.get("user_id")
    )


@app.route("/admin/create_user", methods=["POST"])
@admin_required
@demo_readonly
def admin_create_user():
    data = request.get_json()
    username = data.get("username", "").strip()
    role = data.get("role", "user")
    if not username:
        return jsonify({"error": "Username is required."}), 400
    if role not in ("user", "low", "admin"):
        return jsonify({"error": "Invalid role."}), 400
    if users_collection.find_one({"username": username}):
        return jsonify({"error": "That username is already taken."}), 400
    users_collection.insert_one({"username": username, "role": role})
    return jsonify({"success": True})


@app.route("/admin/update_user", methods=["POST"])
@admin_required
@demo_readonly
def admin_update_user():
    data = request.get_json()
    user_id = data.get("id")
    new_role = data.get("role")
    manager_id_str = data.get("manager_id", "")
    if new_role not in ("user", "low", "admin"):
        return jsonify({"error": "Invalid role."}), 400
    update = {"role": new_role}
    if manager_id_str:
        update["manager_id"] = ObjectId(manager_id_str)
    else:
        update["manager_id"] = None
    users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": update})
    return jsonify({"success": True})


@app.route("/admin/delete_user", methods=["POST"])
@admin_required
@demo_readonly
def admin_delete_user():
    data = request.get_json()
    user_id = data.get("id")
    if user_id == session.get("user_id"):
        return jsonify({"error": "You cannot delete your own account."}), 400
    users_collection.delete_one({"_id": ObjectId(user_id)})
    return jsonify({"success": True})


@app.route("/switch-mode", methods=["POST"])
@login_required
@demo_readonly
def switch_mode():
    username = session.get("username")
    current_mode = session.get("mode", "work")
    requested_mode = "school" if current_mode == "work" else "work"
    feedback_collection.insert_one({
        "rating": 5,
        "feedback": f"Mode switch request: {username} wants to switch from {current_mode} to {requested_mode} mode.",
        "submitted_by": username,
        "submitted_at": datetime.utcnow().isoformat(),
        "type": "mode_switch_request"
    })
    return redirect(url_for("dashboard"))


app.run(host="0.0.0.0", port=5055, debug=True)
