from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from functools import wraps
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import calendar as cal_module
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
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


@app.context_processor
def inject_user():
    return {
        "current_username": session.get("username", ""),
        "current_role": session.get("role", ""),
        "is_demo": session.get("is_demo", False)
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
            manager_id = user.get("manager_id")
            session["manager_id"] = str(manager_id) if manager_id else None
            return redirect(url_for("dashboard"))

    return render_template("set_password.html", username=user["username"], error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username:
            error = "Username is required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif users_collection.find_one({"username": username}):
            error = "That username is already taken."
        else:
            hashed = generate_password_hash(password)
            users_collection.insert_one({
                "username": username,
                "password": hashed,
                "role": "user"
            })
            return redirect(url_for("login"))

    return render_template("register.html", error=error)


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

    return render_template("items.html", items=tasks, title="Tasks", assignable_users=assignable_users)


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

    return render_template("items.html", items=tickets, title="Tickets", assignable_users=assignable_users)


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

    return render_template("items.html", items=requests_data, title="Requests", assignable_users=assignable_users)


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
        current_user_id=session.get("user_id"),
        demo_views_user=demo_logs.count_documents({"role": "user"}),
        demo_views_admin=demo_logs.count_documents({"role": "admin"})
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


app.run(host="0.0.0.0", port=5055, debug=True)
