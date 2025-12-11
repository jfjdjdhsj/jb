from flask import Flask, render_template, request, redirect, url_for, g, jsonify
import sqlite3
import os

app = Flask(__name__)

# 自定义表单配置
FORM_CONFIG = {
    'name': {
        'label': '资源名称',
        'placeholder': '输入资源名称',
        'required': True
    },
    'r_type': {
        'label': '资源类型',
        'placeholder': '选择或输入...',
        'required': False,
        'options': ['软件工具', '影视资源', '学习教程', '游戏资源', '文档资料']
    },
    'description': {
        'label': '资源描述',
        'placeholder': '资源特点和使用说明...',
        'required': False
    },
    'tg_link': {
        'label': 'Telegram 频道',
        'placeholder': 'https://t.me/...',
        'required': False
    },
    'pan_link': {
        'label': '下载链接',
        'placeholder': 'https://pan...',
        'required': False
    },
    'pan_pass': {
        'label': '提取密码',
        'placeholder': '选填',
        'required': False
    },
    'tags': {
        'label': '分类标签',
        'placeholder': '逗号分隔，如：破解, 绿色版',
        'hint': '不填写的不显示',
        'required': False
    }
}

# 本地 SQLite 数据库
DATABASE = 'resources.db'

def get_db():
    """获取数据库连接"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """关闭数据库连接"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """初始化数据库"""
    with app.app_context():
        db = get_db()
        
        # 创建表
        db.execute('''
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                r_type TEXT,
                description TEXT,
                tg_link TEXT,
                pan_link TEXT,
                pan_pass TEXT,
                tags TEXT,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 检查是否需要添加 sort_order 列
        try:
            cursor = db.execute("PRAGMA table_info(resources)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'sort_order' not in columns:
                # 添加缺少的 sort_order 列
                db.execute("ALTER TABLE resources ADD COLUMN sort_order INTEGER DEFAULT 0")
                
                # 为现有资源初始化排序值
                cursor = db.execute('SELECT id FROM resources ORDER BY created_at DESC')
                existing_resources = cursor.fetchall()
                for i, resource in enumerate(existing_resources):
                    db.execute('UPDATE resources SET sort_order = ? WHERE id = ?', (i, resource['id']))
                    
        except Exception as e:
            print(f"数据库初始化错误: {e}")
        
        db.commit()

# --- 路由逻辑 ---

@app.route('/')
def index():
    """首页 - 显示资源列表"""
    db = get_db()
    query = request.args.get('q')  # 获取搜索关键词
    
    if query:
        search_term = f'%{query}%'
        sql = '''
            SELECT * FROM resources 
            WHERE name LIKE ? OR tags LIKE ? OR description LIKE ? 
            ORDER BY sort_order ASC, created_at DESC
        '''
        cur = db.execute(sql, (search_term, search_term, search_term))
    else:
        cur = db.execute('SELECT * FROM resources ORDER BY sort_order ASC, created_at DESC')
        
    resources = cur.fetchall()
    return render_template('index.html', resources=resources, search_query=query)

@app.route('/admin/700370', methods=['GET', 'POST'])
def admin():
    """管理员页面 - 添加和管理资源"""
    if request.method == 'POST':
        # 获取表单数据
        name = request.form['name']
        r_type = request.form['r_type']
        description = request.form['description']
        tg_link = request.form['tg_link']
        pan_link = request.form['pan_link']
        pan_pass = request.form['pan_pass']
        tags = request.form['tags']

        db = get_db()
        
        # 获取当前最大的排序值
        try:
            cursor = db.execute('SELECT MAX(sort_order) as max_order FROM resources')
            result = cursor.fetchone()
            max_order = result['max_order'] if result and result['max_order'] is not None else -1
            new_order = max_order + 1
        except:
            new_order = 0
        
        # 插入新资源
        db.execute('''
            INSERT INTO resources (name, r_type, description, tg_link, pan_link, pan_pass, tags, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, r_type, description, tg_link, pan_link, pan_pass, tags, new_order))
        db.commit()

        return redirect(url_for('admin'))

    # GET请求 - 显示管理页面
    db = get_db()
    cur = db.execute('SELECT * FROM resources ORDER BY sort_order ASC')
    resources = cur.fetchall()
    return render_template('admin.html', resources=resources, form_config=FORM_CONFIG)

@app.route('/admin/edit/<int:resource_id>', methods=['GET', 'POST'])
def edit_resource(resource_id):
    """编辑资源页面"""
    db = get_db()
    
    if request.method == 'POST':
        # 获取表单数据
        name = request.form['name']
        r_type = request.form['r_type']
        description = request.form['description']
        tg_link = request.form['tg_link']
        pan_link = request.form['pan_link']
        pan_pass = request.form['pan_pass']
        tags = request.form['tags']

        # 更新资源
        db.execute('''
            UPDATE resources 
            SET name = ?, r_type = ?, description = ?, tg_link = ?, pan_link = ?, pan_pass = ?, tags = ?
            WHERE id = ?
        ''', (name, r_type, description, tg_link, pan_link, pan_pass, tags, resource_id))
        db.commit()
        
        return redirect(url_for('admin'))
    
    # GET请求 - 显示编辑表单
    cur = db.execute('SELECT * FROM resources WHERE id = ?', (resource_id,))
    resource = cur.fetchone()
    
    if not resource:
        return redirect(url_for('admin'))
    
    return render_template('edit.html', resource=resource, form_config=FORM_CONFIG)

@app.route('/admin/update_order', methods=['POST'])
def update_order():
    """更新资源排序"""
    try:
        order_data = request.get_json()
        if not order_data:
            return jsonify({'success': False, 'message': '无效的数据'})
        
        db = get_db()
        
        # 更新每个资源的排序值
        for index, item_id in enumerate(order_data):
            db.execute('UPDATE resources SET sort_order = ? WHERE id = ?', (index, int(item_id)))
        
        db.commit()
        
        return jsonify({'success': True, 'message': '排序更新成功！'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/delete/<int:resource_id>', methods=['POST'])
def delete_resource(resource_id):
    """删除资源"""
    try:
        db = get_db()
        db.execute('DELETE FROM resources WHERE id = ?', (resource_id,))
        db.commit()
            
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"删除错误: {e}")
        return redirect(url_for('admin'))

if __name__ == '__main__':
    print("启动本地开发服务器...")
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)