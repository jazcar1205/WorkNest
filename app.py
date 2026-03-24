from flask import Flask, render_template, request, redirect, url_for, jsonify
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId
import calendar as cal_module
app = Flask(__name__)

client = MongoClient("mongodb+srv://jazcarlos4_db_user:kSfIBaCBdX0ay29n@type-db.u1wzklp.mongodb.net/?appName=type-db")
db = client["type-db"]
ap_collection = db["appointments"]
task_collection = db["tasks"]
req_collection = db["requests"]
tick_collection = db["tickets"]


@app.route("/openTasks")
def open_tasks():
    tasks = list(task_collection.find())
    return render_template("items.html", items=tasks, title="Tasks")

@app.route("/openTickets")
def open_tickets():
    tickets = list(tick_collection.find())
    return render_template("items.html", items=tickets, title="Tickets")

@app.route("/openRequests")
def open_requests():
    requests_data = list(req_collection.find())
    return render_template("items.html", items=requests_data, title="Requests")

@app.route("/create")
def creation():
    return render_template("creation.html")

@app.route("/create_item", methods=["POST"])
def create_item():
    item_type = request.form.get("type")

    item_data = {
        "assigned": request.form.get("assigned"),
        "status": request.form.get("status"),
        "description": request.form.get("description"),
        "created": request.form.get("created"),
        "due": request.form.get("due")
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
def appointments():
    now = datetime.today()
    today_str = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")

    upcoming = list(ap_collection.find({
        "date": {"$gte": today_str}
    }).sort("date", 1))

    month_appts = list(ap_collection.find({"date": {"$regex": f"^{month_str}"}}))

    # Build {day: [title, ...]} for calendar labels
    appt_by_day = {}
    for a in month_appts:
        if a.get("date"):
            try:
                day = int(a["date"].split("-")[2])
                label = a.get("title") or a.get("description") or "Appointment"
                appt_by_day.setdefault(day, []).append(label)
            except Exception:
                pass

    # Convert ObjectId to string so templates can use them as data attributes
    for a in upcoming:
        a["_id"] = str(a["_id"])

    cal = cal_module.Calendar(firstweekday=6)  # Sunday first
    cal_weeks = cal.monthdayscalendar(now.year, now.month)

    return render_template("appointments.html",
        appointments=upcoming,
        cal_weeks=cal_weeks,
        month_name=now.strftime("%B %Y"),
        today_day=now.day,
        appt_by_day=appt_by_day
    )

@app.route("/create_appointment", methods=["POST"])
def create_appointment():
    data = {
        "title":      request.form.get("title"),
        "date":       request.form.get("date"),
        "start_time": request.form.get("start_time"),
        "end_time":   request.form.get("end_time"),
        "invite":     request.form.get("invite"),
        "description": request.form.get("description")
    }
    ap_collection.insert_one(data)
    return redirect(url_for("appointments"))

@app.route("/update_appointment", methods=["POST"])
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
def delete_appointment():
    data = request.get_json()
    ap_collection.delete_one({"_id": ObjectId(data.get("id"))})
    return jsonify({"success": True})

@app.route("/delete_item", methods=["POST"])
def delete_item():
    data = request.json
    item_id = data.get("id")

    for collection in [task_collection, tick_collection, req_collection]:
        result = collection.delete_one({"_id": ObjectId(item_id)})
        if result.deleted_count > 0:
            break

    return jsonify({"success": True})

@app.route("/update_item", methods=["POST"])
def update_item():
    data = request.get_json()

    item_id = data.get("id")

    if not item_id:
        return jsonify({"error": "Missing ID"}), 400

    updated_data = {
        "description": data.get("description"),
        "status": data.get("status"),
        "assigned": data.get("assigned"),
        "created": data.get("created"),
        "due": data.get("due")
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
def assigned_tasks():

    tasks = list(task_collection.find())
    tickets = list(tick_collection.find())
    requests_data = list(req_collection.find())

    # Optional: convert ObjectId → string
    for item in tasks:
        item["_id"] = str(item["_id"])
    for item in tickets:
        item["_id"] = str(item["_id"])
    for item in requests_data:
        item["_id"] = str(item["_id"])

    return render_template(
        "assigned.html",
        tasks=tasks,
        tickets=tickets,
        requests=requests_data
    )

@app.route("/Dashboard")
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
@app.route("/")
def start_index():
    return render_template("login.html")

app.run(host="0.0.0.0", port=5055)