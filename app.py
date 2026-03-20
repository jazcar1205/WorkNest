from flask import Flask, render_template
#request, #jsonify
#import random
#from pymongo import MongoClient

#uri = "mongodb+srv://jazcarlos4_db_user:rO2ekaME0CtWH4te@rather-db.z8ogimc.mongodb.net/?appName=rather-db"

#client = MongoClient(uri)

#db = client["WouldRather"]
#collection = db["Choices"]
#votes_collection = db["votes"]
app = Flask(__name__)

@app.route("/openTasks")
def open_tasks():
    return render_template("items.html")
@app.route("/openTickets")
def open_tickets():
    return render_template("items.html")
@app.route("/openRequests")
def open_requests():
    return render_template("items.html")

@app.route("/assigned")
def assigned_tasks():
    return render_template("assigned.html")
@app.route("/appointments")
def appointments():
    return render_template("appointments.html")

@app.route("/create")
def creation():
    return render_template("creation.html")

@app.route("/Dashboard")
def dashboard():
    return render_template("dashboard.html")
@app.route("/")
def start_index():
    return render_template("index.html")

app.run(host = "0.0.0.0", port = 5055)