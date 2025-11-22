# app.py
import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import uuid
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "rms.db")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("RMS_SECRET", "dev-secret-change-me")
CORS(app)

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=True)

class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    logo = db.Column(db.String(500), nullable=True)
    menu_items = db.relationship("MenuItem", backref="restaurant", lazy=True, cascade="all, delete-orphan")
    tables = db.relationship("Table", backref="restaurant", lazy=True, cascade="all, delete-orphan")
    orders = db.relationship("Order", backref="restaurant", lazy=True, cascade="all, delete-orphan")
    incomes = db.relationship("Income", backref="restaurant", lazy=True, cascade="all, delete-orphan")
    feedback = db.relationship("Feedback", backref="restaurant", lazy=True, cascade="all, delete-orphan")

    def to_list_item(self):
        return {
            "id": self.id,
            "name": self.name,
            "logo": self.logo or f"https://ui-avatars.com/api/?name={self.name.replace(' ','+')}&&background=101827&color=fff",
            "menuCount": len(self.menu_items),
            "tableCount": len(self.tables)
        }

    def to_full(self):
        bookings = []
        for t in self.tables:
            for b in t.bookings:
                bookings.append(b.to_dict())
        
        return {
            "id": self.id,
            "name": self.name,
            "logo": self.logo or f"https://ui-avatars.com/api/?name={self.name.replace(' ','+')}&&background=101827&color=fff",
            "menu": [m.to_dict() for m in self.menu_items],
            "tables": [t.to_dict() for t in self.tables],
            "orders": [o.to_dict() for o in self.orders],
            "incomes": [i.amount for i in self.incomes],
            "feedback": [f.to_dict() for f in self.feedback],
            "bookings": bookings
        }

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    img = db.Column(db.String(500), nullable=True)
    order_count = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "img": self.img or "https://via.placeholder.com/400x200?text=Dish",
            "orderCount": self.order_count
        }

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False)
    num = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), default="Available")
    bookings = db.relationship("Booking", backref="table", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "num": self.num, "status": self.status}

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey("table.id"), nullable=False)
    user_name = db.Column(db.String(150))
    start = db.Column(db.String(100))
    end = db.Column(db.String(100))

    def to_dict(self):
        return {
            "id": self.id,
            "tableNum": self.table.num if self.table else str(self.table_id),
            "userName": self.user_name,
            "start": self.start,
            "end": self.end
        }

class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    when = db.Column(db.DateTime, default=datetime.utcnow)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False)
    user_name = db.Column(db.String(150))
    when = db.Column(db.DateTime, default=datetime.utcnow)
    food_rating = db.Column(db.Integer, default=0)
    service_rating = db.Column(db.Integer, default=0)
    text = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": self.id,
            "userName": self.user_name,
            "when": self.when.isoformat(),
            "foodRating": self.food_rating,
            "serviceRating": self.service_rating,
            "text": self.text
        }

class Order(db.Model):
    id = db.Column(db.String(100), primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False)
    user_name = db.Column(db.String(150))
    items_json = db.Column(db.Text)
    total = db.Column(db.Float)
    method = db.Column(db.String(50))
    when = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        items = json.loads(self.items_json) if self.items_json else []
        return {
            "id": self.id,
            "userName": self.user_name,
            "items": items,
            "total": self.total,
            "method": self.method,
            "when": self.when.isoformat()
        }

# Routes
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    type_ = data.get("type")
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not all([type_, name, email, password]):
        return jsonify({"error": "Missing fields"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 400

    password_hash = generate_password_hash(password)
    user = User(name=name, email=email, password_hash=password_hash, type=type_)
    
    if type_ == "restaurant":
        r = Restaurant(name=name)
        db.session.add(r)
        db.session.flush()
        user.restaurant_id = r.id

    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Registration successful"}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        return jsonify({"error": "Missing credentials"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    resp = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "type": user.type
    }
    if user.type == "restaurant":
        resp["restaurantId"] = user.restaurant_id
    return jsonify(resp)

@app.route("/api/restaurants", methods=["GET"])
def list_restaurants():
    rs = Restaurant.query.all()
    return jsonify([r.to_list_item() for r in rs])

@app.route("/api/restaurants/<int:rid>", methods=["GET"])
def get_restaurant(rid):
    r = Restaurant.query.get_or_404(rid)
    return jsonify(r.to_full())

@app.route("/api/restaurants/<int:rid>/menu", methods=["POST"])
def add_menu_item(rid):
    r = Restaurant.query.get_or_404(rid)
    data = request.get_json() or {}
    name = data.get("name")
    price = data.get("price")
    img = data.get("img")
    
    if not name or price is None:
        return jsonify({"error": "Missing name or price"}), 400
    
    mi = MenuItem(restaurant_id=r.id, name=name, price=float(price), img=img)
    db.session.add(mi)
    db.session.commit()
    return jsonify({"message": "Menu item added", "item": mi.to_dict()}), 201

@app.route("/api/restaurants/<int:rid>/tables", methods=["POST"])
def add_table(rid):
    r = Restaurant.query.get_or_404(rid)
    data = request.get_json() or {}
    num = data.get("num")
    status = data.get("status", "Available")
    
    if not num:
        return jsonify({"error": "Missing table number"}), 400
    
    t = Table.query.filter_by(restaurant_id=r.id, num=num).first()
    if t:
        t.status = status
    else:
        t = Table(restaurant_id=r.id, num=num, status=status)
        db.session.add(t)
    
    db.session.commit()
    return jsonify({"message": "Table updated", "table": t.to_dict()}), 201

@app.route("/api/restaurants/<int:rid>/income", methods=["POST"])
def add_income(rid):
    r = Restaurant.query.get_or_404(rid)
    data = request.get_json() or {}
    amount = data.get("amount")
    
    try:
        amt = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount"}), 400
    
    inc = Income(restaurant_id=r.id, amount=amt)
    db.session.add(inc)
    db.session.commit()
    return jsonify({"message": "Income added"}), 201

@app.route("/api/restaurants/<int:rid>/feedback", methods=["POST"])
def add_feedback(rid):
    r = Restaurant.query.get_or_404(rid)
    data = request.get_json() or {}
    user_name = data.get("userName", "Anonymous")
    food_rating = int(data.get("foodRating", 0))
    service_rating = int(data.get("serviceRating", 0))
    text = data.get("text", "")
    
    fb = Feedback(
        restaurant_id=r.id,
        user_name=user_name,
        food_rating=food_rating,
        service_rating=service_rating,
        text=text
    )
    db.session.add(fb)
    db.session.commit()
    return jsonify({"message": "Feedback submitted"}), 201

@app.route("/api/restaurants/<int:rid>/orders", methods=["POST"])
def create_order(rid):
    r = Restaurant.query.get_or_404(rid)
    data = request.get_json() or {}
    user_name = data.get("userName", "Guest")
    items = data.get("items", [])
    method = data.get("method", "online")
    total = float(data.get("total", 0))
    order_id = str(uuid.uuid4())[:8]
    
    o = Order(
        id=order_id,
        restaurant_id=r.id,
        user_name=user_name,
        items_json=json.dumps(items),
        total=total,
        method=method
    )
    db.session.add(o)
    
    # Update order counts
    for it in items:
        mid = it.get("id")
        qty = int(it.get("qty", 1))
        if mid:
            mi = MenuItem.query.filter_by(id=mid, restaurant_id=r.id).first()
            if mi:
                mi.order_count = (mi.order_count or 0) + qty
    
    db.session.commit()
    return jsonify({"message": "Order placed", "orderId": order_id}), 201

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "database": "connected"})

def init_db():
    """Initialize database and seed demo data"""
    with app.app_context():
        db.create_all()
        
        # Check if demo data exists
        if not Restaurant.query.first():
            # Create demo restaurant
            demo_rest = Restaurant(
                name="Spice & Flavor",
                logo="https://ui-avatars.com/api/?name=Spice+Flavor&background=ff6b35&color=fff"
            )
            db.session.add(demo_rest)
            db.session.flush()
            
            # Add demo menu items
            menu_items = [
                MenuItem(restaurant_id=demo_rest.id, name="Masala Dosa", price=120, 
                        img="https://via.placeholder.com/400x200?text=Masala+Dosa", order_count=45),
                MenuItem(restaurant_id=demo_rest.id, name="Paneer Butter Masala", price=240,
                        img="https://via.placeholder.com/400x200?text=Paneer+Butter+Masala", order_count=32),
                MenuItem(restaurant_id=demo_rest.id, name="Biryani", price=280,
                        img="https://via.placeholder.com/400x200?text=Biryani", order_count=67)
            ]
            
            # Add demo tables
            tables = [
                Table(restaurant_id=demo_rest.id, num="1", status="Available"),
                Table(restaurant_id=demo_rest.id, num="2", status="Available"),
                Table(restaurant_id=demo_rest.id, num="3", status="Occupied")
            ]
            
            db.session.add_all(menu_items + tables)
            db.session.commit()
            print("✓ Database initialized with demo data")
        else:
            print("✓ Database already exists")

if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print("Restaurant Management System - Backend Started")
    print("=" * 50)
    print("🌐 Server: http://localhost:5000")
    print("📊 Database: SQLite (rms.db)")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)