from flask import Flask, render_template, request, redirect, url_for, g, jsonify, flash, send_file
import sqlite3
import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # 添加secret_key用于flash消息

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
        'placeholder': 'https://t.me/... ',
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
    try:
        db = getattr(g, '_database', None)
        if db is None:
            if not os.path.exists(DATABASE):
                init_db()  # 如果数据库文件不存在，先初始化
            db = g._database = sqlite3.connect(DATABASE)
            db.row_factory = sqlite3.Row
        return db
    except Exception as e:
        print(f"获取数据库连接错误: {e}")
        init_db()  # 发生错误时尝试重新初始化
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        return db

@app.teardown_appcontext
def close_connection(exception):
    """关闭数据库连接"""
    db = getattr(g, '_database', None)
    if db is not None:
        try:
            db.close()
        except:
            pass

def init_db():
    """初始化数据库"""
    try:
        db = sqlite3.connect(DATABASE)
        
        # 创建资源表
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  
            )  
        ''')  
          
        # 创建公告表  
        db.execute('''  
            CREATE TABLE IF NOT EXISTS notices (  
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                content TEXT NOT NULL,  
                is_enabled INTEGER DEFAULT 0,  
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  
            )  
        ''')  
          
        # 检查是否有公告数据，没有则初始化一条默认公告  
        cursor = db.execute('SELECT COUNT(*) as count FROM notices')  
        notice_count = cursor.fetchone()[0]  
        if notice_count == 0:  
            db.execute('''  
                INSERT INTO notices (content, is_enabled)   
                VALUES ('欢迎使用资源分享站！', 0)  
            ''')  
              
        # 检查是否需要添加 sort_order 列  
        try:  
            cursor = db.execute("PRAGMA table_info(resources)")  
            columns = [column[1] for column in cursor.fetchall()]  
              
            if 'sort_order' not in columns:  
                db.execute("ALTER TABLE resources ADD COLUMN sort_order INTEGER DEFAULT 0")  
                  
                # 为现有数据设置排序
                try:
                    cursor = db.execute('SELECT id FROM resources ORDER BY created_at DESC')  
                    existing_resources = cursor.fetchall()  
                    for i, resource in enumerate(existing_resources):  
                        db.execute('UPDATE resources SET sort_order = ? WHERE id = ?', (i, resource[0],))  
                except:
                    pass  # 如果没有数据，忽略错误
                    
            # 检查是否需要添加 updated_at 列  
            if 'updated_at' not in columns:  
                db.execute("ALTER TABLE resources ADD COLUMN updated_at TIMESTAMP")  
                  
                try:
                    cursor = db.execute('SELECT id FROM resources WHERE updated_at IS NULL')  
                    existing_resources = cursor.fetchall()  
                    for resource in existing_resources:  
                        db.execute('UPDATE resources SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (resource[0],))  
                except:
                    pass  # 如果没有数据，忽略错误
                    
        except Exception as e:  
            print(f"检查列结构时出错: {e}")  
          
        db.commit()
        db.close()
        print("数据库初始化完成")
            
    except Exception as e:
        print(f"数据库初始化错误: {e}")

def get_current_notice():
    """获取当前激活的公告"""
    try:
        db = get_db()
        cursor = db.execute('SELECT id, content, updated_at FROM notices WHERE is_enabled = 1 ORDER BY updated_at DESC LIMIT 1')
        return cursor.fetchone()
    except Exception as e:
        print(f"获取公告错误: {e}")
        return None

def check_db_tables():
    """检查数据库表是否存在"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['resources', 'notices']
        missing_tables = [table for table in required_tables if table not in tables]
        
        if missing_tables:
            print(f"缺少表: {missing_tables}")
            init_db()  # 重新初始化数据库
            return False
        return True
    except Exception as e:
        print(f"检查数据库表错误: {e}")
        init_db()
        return False

# --- 路由逻辑 ---

@app.route('/')
def index():
    """首页 - 显示资源列表"""
    try:
        # 确保数据库表存在
        if not check_db_tables():
            flash('数据库已重新初始化', 'info')
        
        db = get_db()
        query = request.args.get('q')  # 获取搜索关键词

        if query:  
            search_term = f'%{query}%'  
            sql = '''  
                SELECT * FROM resources   
                WHERE name LIKE ? OR tags LIKE ? OR description LIKE ?   
                ORDER BY sort_order ASC, updated_at DESC, created_at DESC  
            '''  
            cur = db.execute(sql, (search_term, search_term, search_term))  
            # 搜索时不显示公告  
            notice = None  
            notice_id = None  
            notice_updated_at = None  
        else:  
            cur = db.execute('SELECT * FROM resources ORDER BY sort_order ASC, updated_at DESC, created_at DESC')  
            # 只有主页才显示公告  
            notice = get_current_notice()  
            if notice:  
                notice_id = notice['id']  
                notice_updated_at = notice['updated_at']  
            else:  
                notice_id = None  
                notice_updated_at = None  
          
        resources = cur.fetchall()  
        return render_template('index.html',   
                               resources=resources,   
                               search_query=query,   
                               notice=notice,   
                               notice_id=notice_id,   
                               notice_updated_at=notice_updated_at)
    except Exception as e:
        print(f"首页错误: {e}")
        flash('系统错误，正在重新初始化数据库...', 'error')
        init_db()
        return redirect(url_for('index'))

@app.route('/admin/notice/toggle', methods=['POST'])
def toggle_notice():
    """切换公告开关状态"""
    try:
        if not check_db_tables():
            return jsonify({'success': False, 'message': '数据库表不存在，已重新初始化'})
            
        data = request.get_json()
        enabled = data.get('enabled', False)

        db = get_db()  
        db.execute('''  
            UPDATE notices   
            SET is_enabled = ?, updated_at = CURRENT_TIMESTAMP  
            WHERE id = (SELECT id FROM notices ORDER BY updated_at DESC LIMIT 1)  
        ''', (1 if enabled else 0,))  
        db.commit()  
          
        return jsonify({'success': True, 'enabled': enabled})  
          
    except Exception as e:
        print(f"切换公告错误: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/700370', methods=['GET', 'POST'])
def admin():
    """管理员页面 - 添加和管理资源"""
    try:
        # 确保数据库表存在
        if not check_db_tables():
            flash('数据库已重新初始化', 'info')
        
        if request.method == 'POST':
            # 处理资源添加
            if 'name' in request.form:
                name = request.form['name']
                r_type = request.form['r_type']
                description = request.form['description']
                tg_link = request.form['tg_link']
                pan_link = request.form['pan_link']
                pan_pass = request.form['pan_pass']
                tags = request.form['tags']

                db = get_db()  
              
                try:  
                    cursor = db.execute('SELECT MAX(sort_order) as max_order FROM resources')  
                    result = cursor.fetchone()  
                    max_order = result['max_order'] if result and result['max_order'] is not None else -1  
                    new_order = max_order + 1  
                except:  
                    new_order = 0  
              
                db.execute('''  
                    INSERT INTO resources (name, r_type, description, tg_link, pan_link, pan_pass, tags, sort_order)   
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)  
                ''', (name, r_type, description, tg_link, pan_link, pan_pass, tags, new_order))  
                db.commit()  
                flash('资源添加成功！', 'success')
              
            # 处理公告更新 - 修复这里
            elif 'notice_content' in request.form:  
                notice_content = request.form['notice_content']  
                
                # 获取当前公告状态，保持开关状态不变
                db = get_db()
                cursor = db.execute('SELECT is_enabled FROM notices ORDER BY updated_at DESC LIMIT 1')
                current_notice = cursor.fetchone()
                current_enabled = current_notice['is_enabled'] if current_notice else 0
                
                db.execute('''  
                    UPDATE notices   
                    SET content = ?, is_enabled = ?, updated_at = CURRENT_TIMESTAMP   
                    WHERE id = (SELECT id FROM notices ORDER BY updated_at DESC LIMIT 1)  
                ''', (notice_content, current_enabled))  
                db.commit()  
                flash('公告更新成功！', 'success')
          
            return redirect(url_for('admin'))  
      
        # GET请求 - 显示管理页面  
        db = get_db()  
        cur = db.execute('SELECT * FROM resources ORDER BY sort_order ASC')  
        resources = cur.fetchall()  
  
        # 获取当前公告设置  
        notice_cur = db.execute('SELECT * FROM notices ORDER BY updated_at DESC LIMIT 1')  
        notice = notice_cur.fetchone()  
  
        return render_template('admin.html', resources=resources, form_config=FORM_CONFIG, notice=notice or {})
        
    except Exception as e:
        print(f"管理员页面错误: {e}")
        flash('系统错误，正在重新初始化数据库...', 'error')
        init_db()
        return redirect(url_for('admin'))

@app.route('/admin/edit/<int:resource_id>', methods=['GET', 'POST'])
def edit_resource(resource_id):
    """编辑资源页面"""
    try:
        if not check_db_tables():
            flash('数据库已重新初始化', 'info')
            return redirect(url_for('admin'))
            
        db = get_db()

        if request.method == 'POST':  
            name = request.form['name']  
            r_type = request.form['r_type']  
            description = request.form['description']  
            tg_link = request.form['tg_link']  
            pan_link = request.form['pan_link']  
            pan_pass = request.form['pan_pass']  
            tags = request.form['tags']  
              
            db.execute('''  
                UPDATE resources   
                SET name = ?, r_type = ?, description = ?, tg_link = ?, pan_link = ?, pan_pass = ?, tags = ?, updated_at = CURRENT_TIMESTAMP   
                WHERE id = ?  
            ''', (name, r_type, description, tg_link, pan_link, pan_pass, tags, resource_id))  
            db.commit()  
            flash('资源更新成功！', 'success')
              
            return redirect(url_for('admin'))  
      
        cur = db.execute('SELECT * FROM resources WHERE id = ?', (resource_id,))  
        resource = cur.fetchone()  
      
        if not resource:  
            return redirect(url_for('admin'))  
      
        return render_template('edit.html', resource=resource, form_config=FORM_CONFIG)
    except Exception as e:
        print(f"编辑资源错误: {e}")
        flash('系统错误，正在重新初始化数据库...', 'error')
        init_db()
        return redirect(url_for('admin'))

@app.route('/admin/update_order', methods=['POST'])
def update_order():
    """更新资源排序"""
    try:
        order_data = request.get_json()
        if not order_data:
            return jsonify({'success': False, 'message': '无效的数据'})

        if not check_db_tables():
            return jsonify({'success': False, 'message': '数据库表不存在，已重新初始化'})

        db = get_db()  
      
        for index, item_id in enumerate(order_data):  
            db.execute('UPDATE resources SET sort_order = ? WHERE id = ?', (index, int(item_id)))  
      
        db.commit()  
      
        return jsonify({'success': True, 'message': '排序更新成功！'})  
      
    except Exception as e:
        print(f"更新排序错误: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/delete/<int:resource_id>', methods=['POST'])
def delete_resource(resource_id):
    """删除资源"""
    try:
        if not check_db_tables():
            flash('数据库已重新初始化', 'info')
            return redirect(url_for('admin'))
            
        db = get_db()
        db.execute('DELETE FROM resources WHERE id = ?', (resource_id,))
        db.commit()
        flash('资源删除成功！', 'success')

        return redirect(url_for('admin'))  
    except Exception as e:  
        print(f"删除错误: {e}")  
        flash('删除失败，请重试！', 'danger')
        return redirect(url_for('admin'))

@app.route('/admin/export_db')
def export_db():
    """导出SQLite数据库文件"""
    try:
        if not os.path.exists(DATABASE):
            flash('数据库文件不存在！', 'danger')
            return redirect(url_for('admin'))
        
        if not check_db_tables():
            flash('数据库表不完整，正在重新初始化...', 'warning')
            init_db()
        
        # 导出的文件名固定为 resources_backup_时间戳.db
        backup_filename = f'resources_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
        
        # 复制数据库文件到临时位置进行下载
        backup_path = os.path.join(app.root_path, backup_filename)
        shutil.copy2(DATABASE, backup_path)
        
        return send_file(
            backup_path, 
            as_attachment=True, 
            download_name=backup_filename,  # 这个就是用户下载时看到的文件名
            mimetype='application/x-sqlite3'
        )
        
    except Exception as e:
        print(f"导出数据库错误: {e}")
        flash(f'导出数据库失败：{str(e)}', 'danger')
        return redirect(url_for('admin'))

@app.route('/admin/import_db', methods=['POST'])
def import_db():
    """导入SQLite数据库文件"""
    temp_path = None
    try:
        if 'db_file' not in request.files:
            flash('没有选择文件！', 'danger')
            return redirect(url_for('admin'))
        
        file = request.files['db_file']
        if file.filename == '':
            flash('没有选择文件！', 'danger')
            return redirect(url_for('admin'))
        
        # 验证文件扩展名
        if not file.filename.lower().endswith('.db'):
            flash('只支持.db格式的SQLite数据库文件！', 'danger')
            return redirect(url_for('admin'))
        
        # 获取原始文件名（不含扩展名）用于提示
        original_name = os.path.splitext(file.filename)[0]
        
        # 保存上传的文件到临时位置
        temp_path = os.path.join(app.root_path, 'temp_import.db')
        
        # 删除可能存在的临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        file.save(temp_path)
        
        # 验证上传的文件是否为有效的SQLite数据库
        try:
            test_conn = sqlite3.connect(temp_path)
            test_cursor = test_conn.cursor()
            
            # 检查必要的表是否存在
            test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in test_cursor.fetchall()]
            
            print(f"数据库 '{original_name}' 中的表: {tables}")
            
            required_tables = ['resources', 'notices']
            missing_tables = [table for table in required_tables if table not in tables]
            
            if missing_tables:
                test_conn.close()
                os.remove(temp_path)
                flash(f'数据库文件 "{original_name}" 缺少必要的表：{", ".join(missing_tables)}', 'danger')
                return redirect(url_for('admin'))
            
            # 检查表结构是否正确
            try:
                test_cursor.execute("SELECT * FROM resources LIMIT 1")
                test_cursor.execute("SELECT * FROM notices LIMIT 1")
                
                # 获取数据统计
                test_cursor.execute("SELECT COUNT(*) FROM resources")
                resource_count = test_cursor.fetchone()[0]
                test_cursor.execute("SELECT COUNT(*) FROM notices")
                notice_count = test_cursor.fetchone()[0]
                
            except sqlite3.Error as e:
                test_conn.close()
                os.remove(temp_path)
                flash(f'数据库 "{original_name}" 表结构不正确：{str(e)}', 'danger')
                return redirect(url_for('admin'))
            
            test_conn.close()
            
        except sqlite3.Error as e:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            flash(f'文件 "{original_name}" 不是有效的SQLite数据库：{str(e)}', 'danger')
            return redirect(url_for('admin'))
        
        # 备份当前数据库
        backup_filename = f'current_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
        backup_path = os.path.join(app.root_path, backup_filename)
        if os.path.exists(DATABASE):
            shutil.copy2(DATABASE, backup_path)
        
        try:
            # 关闭所有数据库连接并替换数据库文件
            db = getattr(g, '_database', None)
            if db:
                db.close()
                g._database = None
            
            # 删除当前的 resources.db
            if os.path.exists(DATABASE):
                os.remove(DATABASE)
            
            # 将上传的文件重命名为 resources.db 并移动到正确位置
            shutil.move(temp_path, DATABASE)
            temp_path = None  # 标记文件已移动，避免后续删除
            
            # 最终验证新数据库是否可用
            new_conn = sqlite3.connect(DATABASE)
            new_cursor = new_conn.cursor()
            
            # 再次检查表
            new_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in new_cursor.fetchall()]
            
            if 'resources' not in tables or 'notices' not in tables:
                new_conn.close()
                # 恢复备份
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, DATABASE)
                flash('导入失败：数据库缺少必要的表，已恢复原数据库', 'danger')
                return redirect(url_for('admin'))
            
            # 验证数据完整性
            new_cursor.execute("SELECT COUNT(*) FROM resources")
            final_resource_count = new_cursor.fetchone()[0]
            new_cursor.execute("SELECT COUNT(*) FROM notices")
            final_notice_count = new_cursor.fetchone()[0]
            new_conn.close()
            
            flash(f'数据库 "{original_name}" 导入成功！已自动重命名为 resources.db。包含 {final_resource_count} 个资源和 {final_notice_count} 个公告。原数据库已备份为 {backup_filename}', 'success')
            
        except Exception as e:
            # 如果导入失败，恢复备份
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, DATABASE)
            raise e
        
    except Exception as e:
        print(f"导入数据库错误: {e}")
        flash(f'导入数据库失败：{str(e)}', 'danger')
    
    # 清理临时文件
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
    
    return redirect(url_for('admin'))

@app.route('/admin/reset_db', methods=['POST'])
def reset_db():
    """重置数据库"""
    try:
        if request.form.get('confirm') != 'RESET_DATABASE':
            flash('无效的重置请求！', 'danger')
            return redirect(url_for('admin'))
        
        # 备份当前数据库
        backup_filename = f'reset_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
        backup_path = os.path.join(app.root_path, backup_filename)
        if os.path.exists(DATABASE):
            shutil.copy2(DATABASE, backup_path)
        
        # 关闭当前连接
        db = getattr(g, '_database', None)
        if db:
            db.close()
            g._database = None
        
        # 删除数据库文件，强制重新初始化
        if os.path.exists(DATABASE):
            os.remove(DATABASE)
        
        # 重新初始化数据库
        init_db()
        
        flash('数据库重置成功！原有数据库已备份为 ' + backup_filename, 'success')
        
    except Exception as e:
        print(f"重置数据库错误: {e}")
        flash('重置数据库失败！', 'danger')
    
    return redirect(url_for('admin'))

if __name__ == '__main__':
    print("启动本地开发服务器...")
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
