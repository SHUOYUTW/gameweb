from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'musmus_store_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///musmus.db'
db = SQLAlchemy(app)

# --- 資料庫模型 ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # 新增管理員欄位

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(20), unique=True, nullable=False)
    username = db.Column(db.String(80), nullable=False)
    items_json = db.Column(db.Text, nullable=False)
    total_price = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="待付款")
    created_at = db.Column(db.DateTime, default=datetime.now)
    completed_at = db.Column(db.DateTime)  # 新增完成時間紀錄

# --- 會員系統配置 ---

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 原始 JSON 資料讀取邏輯 (保留並修復) ---

def get_data():
    file_path = os.path.join(app.root_path, 'data.json')
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    return {"games": []}

# --- 路由與 API ---

@app.route('/')
def index():
    data = get_data()
    return render_template('index.html', games=data['games'])

@app.route('/api/game/<int:game_id>')
def get_game_api(game_id):
    data = get_data()
    if 0 <= game_id < len(data['games']):
        return jsonify(data['games'][game_id])
    return jsonify({"error": "找不到資料"}), 404

@app.route('/price/<int:game_id>')
def price(game_id):
    return render_template('price.html', game_id=game_id)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        hashed_password = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        
        if User.query.filter_by(username=username).first():
            flash('帳號已存在')
            return redirect(url_for('register'))
            
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('註冊成功，請登入！')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash('登入失敗，請檢查帳號密碼')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('cart', None)
    return redirect(url_for('index'))

@app.route('/cart')
@login_required
def cart():
    items = session.get('cart', [])
    total = sum(item['price'] for item in items)
    past_orders = Order.query.filter_by(username=current_user.username).order_by(Order.created_at.desc()).all()
    for order in past_orders:
        order.items_list = json.loads(order.items_json)
    return render_template('cart.html', items=items, total=total, past_orders=past_orders)

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    cart = session.get('cart', [])
    cart.append({
        'game': request.form.get('game_name'),
        'item': request.form.get('item_name'),
        'price': int(request.form.get('price'))
    })
    session['cart'] = cart
    return redirect(request.referrer)

@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_list = session.get('cart', [])
    if not cart_list:
        flash('您的購物車是空的')
        return redirect(url_for('cart'))
    
    total_amount = sum(item['price'] for item in cart_list)
    
    if request.method == 'POST':
        order_id = datetime.now().strftime('%Y%m%d%H%M%S')
        new_order = Order(
            order_id=order_id,
            username=current_user.username,
            items_json=json.dumps(cart_list),
            total_price=total_amount
        )
        db.session.add(new_order)
        db.session.commit()
        session.pop('cart', None)
        
        game_info = {
            'order_id': order_id,
            'member_name': current_user.username,
            'cart_list': cart_list,
            'total': total_amount
        }
        return render_template('order_confirm.html', info=game_info)
    return render_template('checkout.html', items=cart_list, total=total_amount)


@app.route('/activity')
def activity():
    return render_template('activity.html')

@app.route('/about')
def about():
    return render_template('about.html')

# 管理員功能區塊 (Admin Section)

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    return render_template('admin/dashboard.html')

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin: return "權限不足", 403
    users = User.query.all()
    return render_template('admin/users.html', users=users, user_count=len(users))

@app.route('/admin/user/<username>/orders')
@login_required
def admin_user_orders(username):
    if not current_user.is_admin: return "權限不足", 403
    orders = Order.query.filter_by(username=username).order_by(Order.created_at.desc()).all()
    for o in orders:
        o.items_list = json.loads(o.items_json)
    return render_template('admin/user_orders.html', username=username, orders=orders)

@app.route('/admin/orders')
@login_required
def admin_orders():
    if not current_user.is_admin: return "權限不足", 403
    
    # 未完成
    pending = Order.query.filter(Order.status != "已完成").order_by(Order.created_at.desc()).all()
    
    # 近 30 天已完成
    thirty_days_ago = datetime.now() - timedelta(days=30)
    completed = Order.query.filter(Order.status == "已完成", Order.completed_at >= thirty_days_ago).order_by(Order.completed_at.desc()).all()
    
    for o in pending + completed:
        o.items_list = json.loads(o.items_json)
        
    return render_template('admin/orders.html', pending=pending, completed=completed)

@app.route('/admin/update_order/<int:order_db_id>/<new_status>')
@login_required
def update_order_status(order_db_id, new_status):
    if not current_user.is_admin: return "權限不足", 403
    order = Order.query.get(order_db_id)
    if order:
        if new_status == "已完成" and order.status != "已付款":
            return redirect(url_for('admin_orders'))
            
        order.status = new_status
        if new_status == "已完成":
            order.completed_at = datetime.now() 
        db.session.commit()
    return redirect(url_for('admin_orders'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username='admin').first()
        if admin:
            admin.is_admin = True
            db.session.commit()
    app.run(debug=True, port=5000)