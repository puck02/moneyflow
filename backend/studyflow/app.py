import csv
import hashlib
import io
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DEFAULT_DB_PATH = os.environ.get('MONEYFLOW_DB_PATH', '/home/admin/workspace/moneyflow/data/moneyflow.db')


class QQIngest(BaseModel):
    text: str
    sender: str = 'unknown'


class LedgerRecordCreate(BaseModel):
    raw_text: str = Field(..., min_length=1)
    source: str = 'manual'
    direction: str = 'expense'
    category: str = '其他'
    amount: float = 0
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source_hash: Optional[str] = None
    note: str = ''


def connect(db_path: str) -> sqlite3.Connection:
    dirname = os.path.dirname(db_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute('''CREATE TABLE IF NOT EXISTS ledger_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, source TEXT NOT NULL,
        raw_text TEXT NOT NULL, direction TEXT NOT NULL, category TEXT NOT NULL,
        amount REAL NOT NULL DEFAULT 0, summary TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
        source_hash TEXT, note TEXT NOT NULL DEFAULT '')''')
    conn.commit()


def row_to_ledger_record(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    item['tags'] = json.loads(item.get('tags') or '[]')
    return item


def source_hash(sender: str, text: str) -> str:
    norm = re.sub(r'\s+', '', text.strip())
    return hashlib.sha256(f'{sender}:{norm}'.encode('utf-8')).hexdigest()[:24]


def looks_like_ledger(text: str) -> bool:
    has_amount = bool(re.search(r'\d+(?:\.\d+)?\s*(元|块|rmb)?', text, re.I))
    has_keyword = any(
        key in text for key in ['记账', '花', '花了', '用了', '支出', '收入', '到账', '买', '支付', '付款', '消费', '工资', '报销']
    )
    return has_amount and has_keyword


def infer_ledger_direction(text: str) -> str:
    income_keywords = ['收入', '到账', '工资', '报销', '退款', '收了', '赚了', '入账', '转给我']
    return 'income' if any(word in text for word in income_keywords) else 'expense'


def infer_ledger_amount(text: str) -> float:
    match = re.search(r'(\d+(?:\.\d+)?)\s*(元|块|rmb)', text, re.I)
    if not match:
        match = re.search(r'(\d+(?:\.\d+)?)', text)
    return round(float(match.group(1)), 2) if match else 0.0


def infer_ledger_category(text: str, direction: str) -> str:
    category_map = [
        ('餐饮', ['饭', '早餐', '午饭', '晚饭', '夜宵', '奶茶', '咖啡', '外卖', '拉面', '吃', '零食']),
        ('交通', ['地铁', '公交', '打车', '滴滴', '高铁', '火车', '车费', '通勤']),
        ('购物', ['买', '淘宝', '京东', '拼多多', '耳机', '衣服', '裤子', '鞋', '超市', '便利店']),
        ('住房', ['房租', '租房', '水电', '物业']),
        ('娱乐', ['电影', '游戏', '桌游', 'KTV', '演出']),
        ('医疗', ['医院', '药', '挂号', '体检']),
        ('学习', ['书', '课程', '打印', '资料', '题库', '报名']),
        ('社交', ['红包', '请客', '聚餐', '礼物']),
    ]
    if direction == 'income':
        income_map = [
            ('工资', ['工资', '发薪', '薪资']),
            ('兼职', ['兼职', '外快']),
            ('报销', ['报销']),
            ('退款', ['退款', '退回']),
            ('转账', ['转给我', '收款', '转账']),
        ]
        for category, keywords in income_map:
            if any(word in text for word in keywords):
                return category
        return '其他收入'
    for category, keywords in category_map:
        if any(word in text for word in keywords):
            return category
    return '其他'


def clean_ledger_summary(text: str) -> str:
    cleaned = re.sub(r'[，,。；;！!？?]', ' ', text)
    cleaned = re.sub(r'\d+(?:\.\d+)?\s*(元|块|rmb)?', '', cleaned, flags=re.I)
    cleaned = re.sub(r'(记账|花了|花费|支出|收入|到账|付款|支付|消费)', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:80] if cleaned else text[:80]


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return date(y, m, 1)


def parse_month(value: str) -> date:
    return datetime.strptime(value, '%Y-%m').date().replace(day=1)


def parse_date_value(value: str) -> date:
    return datetime.strptime(value, '%Y-%m-%d').date()


def create_app(db_path: str = DEFAULT_DB_PATH) -> FastAPI:
    conn = connect(db_path)
    init_db(conn)
    app = FastAPI(title='MoneyFlow', version='0.7.0')

    def create_ledger_record(payload: LedgerRecordCreate) -> Dict[str, Any]:
        now = datetime.now().isoformat(timespec='seconds')
        summary = payload.summary or payload.raw_text[:120]
        cur = conn.execute(
            '''INSERT INTO ledger_records
            (created_at, source, raw_text, direction, category, amount, summary, tags, source_hash, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                now,
                payload.source,
                payload.raw_text,
                payload.direction,
                payload.category,
                payload.amount,
                summary,
                json.dumps(payload.tags, ensure_ascii=False),
                payload.source_hash,
                payload.note,
            ),
        )
        conn.commit()
        return row_to_ledger_record(conn.execute('SELECT * FROM ledger_records WHERE id=?', (cur.lastrowid,)).fetchone())

    @app.get('/api/health')
    def health():
        return {'ok': True, 'service': 'moneyflow'}

    @app.post('/api/ledger/records')
    def create_ledger(payload: LedgerRecordCreate):
        return create_ledger_record(payload)

    @app.get('/api/ledger/records')
    def list_ledger_records(limit: int = 50, direction: str = 'all'):
        if direction == 'all':
            rows = conn.execute('SELECT * FROM ledger_records ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM ledger_records WHERE direction=? ORDER BY id DESC LIMIT ?', (direction, limit)).fetchall()
        return {'items': [row_to_ledger_record(row) for row in rows]}

    @app.post('/api/ledger/ingest/qq')
    def ingest_ledger_qq(payload: QQIngest):
        text = payload.text.strip()
        hashed = source_hash(payload.sender, f'ledger:{text}')
        if not text or not looks_like_ledger(text):
            return {'ignored': True, 'ignored_reason': 'not_ledger', 'created_record': None}
        existing = conn.execute('SELECT * FROM ledger_records WHERE source_hash=? LIMIT 1', (hashed,)).fetchone()
        if existing:
            return {'ignored': True, 'ignored_reason': 'duplicate', 'created_record': row_to_ledger_record(existing)}
        direction = infer_ledger_direction(text)
        amount = infer_ledger_amount(text)
        category = infer_ledger_category(text, direction)
        summary = clean_ledger_summary(text)
        record = create_ledger_record(
            LedgerRecordCreate(
                raw_text=text,
                source='qq',
                direction=direction,
                category=category,
                amount=amount,
                summary=summary,
                tags=[category],
                source_hash=hashed,
            )
        )
        return {'ignored': False, 'ignored_reason': None, 'created_record': record}

    @app.get('/api/ledger/summary/today')
    def ledger_today_summary():
        prefix = date.today().isoformat()
        rows = conn.execute('SELECT direction,amount FROM ledger_records WHERE created_at LIKE ?', (prefix + '%',)).fetchall()
        expense_total = 0.0
        income_total = 0.0
        expense_count = 0
        income_count = 0
        for row in rows:
            amount = float(row['amount'] or 0)
            if row['direction'] == 'income':
                income_total += amount
                income_count += 1
            else:
                expense_total += amount
                expense_count += 1
        return {
            'date': prefix,
            'expense_total': round(expense_total, 2),
            'income_total': round(income_total, 2),
            'net_total': round(income_total - expense_total, 2),
            'expense_count': expense_count,
            'income_count': income_count,
        }

    def ledger_range_summary(start_prefix: str, end_prefix: str) -> Dict[str, Any]:
        rows = conn.execute(
            'SELECT direction, category, amount FROM ledger_records WHERE created_at>=? AND created_at<?',
            (start_prefix, end_prefix),
        ).fetchall()
        expense_total = 0.0
        income_total = 0.0
        expense_count = 0
        income_count = 0
        expense_by_category: Dict[str, float] = {}
        for row in rows:
            amount = float(row['amount'] or 0)
            if row['direction'] == 'income':
                income_total += amount
                income_count += 1
            else:
                expense_total += amount
                expense_count += 1
                category = row['category'] or '其他'
                expense_by_category[category] = expense_by_category.get(category, 0.0) + amount
        top_expense_category = None
        if expense_by_category:
            top_expense_category = sorted(expense_by_category.items(), key=lambda item: (-item[1], item[0]))[0][0]
        return {
            'expense_total': round(expense_total, 2),
            'income_total': round(income_total, 2),
            'net_total': round(income_total - expense_total, 2),
            'expense_count': expense_count,
            'income_count': income_count,
            'top_expense_category': top_expense_category,
        }

    def resolve_ledger_range(range_key: str = 'today', start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, str]:
        today = date.today()
        if range_key == 'custom':
            if not start or not end:
                raise ValueError('custom range requires start and end')
            start_date = parse_date_value(start)
            end_date = parse_date_value(end)
            if end_date < start_date:
                raise ValueError('end must be on or after start')
            end_exclusive = end_date + timedelta(days=1)
            label = f'{start_date.isoformat()} ~ {end_date.isoformat()}'
        elif range_key == '7d':
            start_date = today - timedelta(days=6)
            end_exclusive = today + timedelta(days=1)
            label = '近 7 天'
        elif range_key == 'month':
            start_date = month_start(today)
            end_exclusive = today + timedelta(days=1)
            label = '本月'
        elif range_key == 'year':
            start_date = date(today.year, 1, 1)
            end_exclusive = today + timedelta(days=1)
            label = '今年'
        else:
            start_date = today
            end_exclusive = today + timedelta(days=1)
            range_key = 'today'
            label = '今日'
        return {
            'range': range_key,
            'label': label,
            'start': start_date.isoformat(),
            'end': (end_exclusive - timedelta(days=1)).isoformat(),
            'end_exclusive': end_exclusive.isoformat(),
        }

    @app.get('/api/ledger/summary/range')
    def ledger_summary_range(range: str = 'today', start: Optional[str] = None, end: Optional[str] = None):
        try:
            info = resolve_ledger_range(range, start, end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        summary = ledger_range_summary(info['start'], info['end_exclusive'])
        summary.update({
            'range': info['range'],
            'label': info['label'],
            'start': info['start'],
            'end': info['end'],
        })
        return summary

    @app.get('/api/ledger/summary/month')
    def ledger_month_summary(month: Optional[str] = None):
        target = parse_month(month) if month else month_start(date.today())
        next_month = add_months(target, 1)
        summary = ledger_range_summary(target.isoformat(), next_month.isoformat())
        summary['month'] = target.strftime('%Y-%m')
        return summary

    @app.get('/api/ledger/stats/monthly-categories')
    def ledger_monthly_categories(direction: str = 'expense', month: Optional[str] = None):
        target = parse_month(month) if month else month_start(date.today())
        next_month = add_months(target, 1)
        rows = conn.execute(
            'SELECT category, SUM(amount) total FROM ledger_records WHERE direction=? AND created_at>=? AND created_at<? GROUP BY category ORDER BY total DESC, category ASC',
            (direction, target.isoformat(), next_month.isoformat()),
        ).fetchall()
        total_amount = round(sum(float(row['total'] or 0) for row in rows), 2)
        items = []
        for row in rows:
            amount = round(float(row['total'] or 0), 2)
            items.append({
                'category': row['category'],
                'amount': amount,
                'percent': round(amount / total_amount * 100, 1) if total_amount else 0,
            })
        return {'month': target.strftime('%Y-%m'), 'direction': direction, 'total_amount': total_amount, 'items': items}

    @app.get('/api/ledger/stats/monthly-overview')
    def ledger_monthly_overview(months: int = 6):
        count = max(1, min(months, 24))
        current = month_start(date.today())
        start = add_months(current, -(count - 1))
        out = []
        cursor = start
        while cursor <= current:
            next_month = add_months(cursor, 1)
            summary = ledger_range_summary(cursor.isoformat(), next_month.isoformat())
            out.append({'month': cursor.strftime('%Y-%m'), **summary})
            cursor = next_month
        return {'months': out}

    @app.get('/api/ledger/stats/category-breakdown')
    def ledger_category_breakdown(direction: str = 'expense', range: str = 'today', start: Optional[str] = None, end: Optional[str] = None):
        resolved = resolve_ledger_range(range, start, end)
        rows = conn.execute(
            'SELECT category, SUM(amount) total FROM ledger_records WHERE direction=? AND created_at>=? AND created_at<? GROUP BY category ORDER BY total DESC, category ASC',
            (direction, resolved['start'], resolved['end_exclusive']),
        ).fetchall()
        total_amount = round(sum(float(row['total'] or 0) for row in rows), 2)
        items = []
        for row in rows:
            amount = round(float(row['total'] or 0), 2)
            items.append({
                'category': row['category'],
                'amount': amount,
                'percent': round(amount / total_amount * 100, 1) if total_amount else 0,
            })
        return {
            'direction': direction,
            'range': resolved['range'],
            'label': resolved['label'],
            'start': resolved['start'],
            'end': resolved['end'],
            'total_amount': total_amount,
            'items': items,
        }

    @app.get('/api/ledger/stats/daily')
    def ledger_daily(days: int = 14):
        end = date.today()
        start = end - timedelta(days=max(days - 1, 0))
        cursor = start
        out = []
        while cursor <= end:
            prefix = cursor.isoformat()
            rows = conn.execute('SELECT direction,amount FROM ledger_records WHERE created_at LIKE ?', (prefix + '%',)).fetchall()
            expense_total = 0.0
            income_total = 0.0
            for row in rows:
                amount = float(row['amount'] or 0)
                if row['direction'] == 'income':
                    income_total += amount
                else:
                    expense_total += amount
            out.append({
                'date': prefix,
                'expense_total': round(expense_total, 2),
                'income_total': round(income_total, 2),
                'net_total': round(income_total - expense_total, 2),
            })
            cursor += timedelta(days=1)
        return {'days': out}

    frontend_dir = '/home/admin/workspace/moneyflow/frontend'
    if os.path.isdir(frontend_dir):
        app.mount('/static', StaticFiles(directory=frontend_dir), name='static')

        @app.get('/')
        def index():
            return FileResponse(os.path.join(frontend_dir, 'ledger.html'))

        @app.get('/ledger')
        def ledger_clean():
            return FileResponse(os.path.join(frontend_dir, 'ledger.html'))

        @app.get('/ledger.html')
        def ledger_html():
            return FileResponse(os.path.join(frontend_dir, 'ledger.html'))

        @app.get('/ledger.js')
        def ledger_js():
            return FileResponse(os.path.join(frontend_dir, 'ledger.js'))

        @app.get('/style.css')
        def style_css():
            return FileResponse(os.path.join(frontend_dir, 'style.css'))

    return app


app = create_app()
