import os
import tempfile
from datetime import date, timedelta

from fastapi.testclient import TestClient

from studyflow.app import create_app, connect


def make_client():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    app = create_app(db_path=tmp.name)
    return TestClient(app), tmp.name


def test_ingest_qq_expense_creates_ledger_record_and_extracts_fields():
    client, path = make_client()
    try:
        res = client.post('/api/ledger/ingest/qq', json={'text': '今天午饭兰州拉面 18 元，记账', 'sender': 'aton_puck'})
        assert res.status_code == 200
        body = res.json()
        assert body['ignored'] is False
        record = body['created_record']
        assert record['direction'] == 'expense'
        assert record['amount'] == 18
        assert record['category'] == '餐饮'
        assert '兰州拉面' in record['summary']
        listed = client.get('/api/ledger/records').json()['items']
        assert len(listed) == 1
        assert listed[0]['amount'] == 18
    finally:
        os.unlink(path)


def test_ingest_qq_income_creates_income_record():
    client, path = make_client()
    try:
        res = client.post('/api/ledger/ingest/qq', json={'text': '今天工资到账 3500 元，记账', 'sender': 'aton_puck'})
        assert res.status_code == 200
        record = res.json()['created_record']
        assert record['direction'] == 'income'
        assert record['amount'] == 3500
        assert record['category'] == '工资'
    finally:
        os.unlink(path)


def test_ledger_dashboard_summary_and_breakdowns():
    client, path = make_client()
    try:
        client.post('/api/ledger/records', json={'raw_text': '午饭 20 元', 'source': 'qq', 'direction': 'expense', 'category': '餐饮', 'amount': 20, 'summary': '午饭'})
        client.post('/api/ledger/records', json={'raw_text': '地铁 4 元', 'source': 'qq', 'direction': 'expense', 'category': '交通', 'amount': 4, 'summary': '地铁'})
        client.post('/api/ledger/records', json={'raw_text': '兼职收入 100 元', 'source': 'qq', 'direction': 'income', 'category': '兼职', 'amount': 100, 'summary': '兼职'})
        summary = client.get('/api/ledger/summary/today')
        assert summary.status_code == 200
        body = summary.json()
        assert body['date'] == date.today().isoformat()
        assert body['expense_total'] == 24
        assert body['income_total'] == 100
        assert body['net_total'] == 76
        pie = client.get('/api/ledger/stats/category-breakdown?direction=expense&range=today')
        assert pie.status_code == 200
        items = pie.json()['items']
        assert items[0]['category'] == '餐饮'
        assert items[0]['amount'] == 20
        trend = client.get('/api/ledger/stats/daily?days=7')
        assert trend.status_code == 200
        assert len(trend.json()['days']) == 7
    finally:
        os.unlink(path)


def test_ledger_category_breakdown_custom_range_only_counts_selected_dates():
    client, path = make_client()
    try:
        client.post('/api/ledger/records', json={'raw_text': '今天午饭 20 元', 'source': 'qq', 'direction': 'expense', 'category': '餐饮', 'amount': 20, 'summary': '午饭'})
        client.post('/api/ledger/records', json={'raw_text': '今天地铁 6 元', 'source': 'qq', 'direction': 'expense', 'category': '交通', 'amount': 6, 'summary': '地铁'})
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        client.post('/api/ledger/records', json={'raw_text': '昨天零食 34.6 元', 'source': 'qq', 'direction': 'expense', 'category': '餐饮', 'amount': 34.6, 'summary': '零食'})
        conn = connect(path)
        conn.execute("UPDATE ledger_records SET created_at=? WHERE summary='零食'", (f"{yesterday}T12:00:00",))
        conn.commit()
        custom = client.get(f'/api/ledger/stats/category-breakdown?direction=expense&range=custom&start={yesterday}&end={yesterday}')
        assert custom.status_code == 200
        body = custom.json()
        assert body['range'] == 'custom'
        assert body['total_amount'] == 34.6
        assert len(body['items']) == 1
    finally:
        os.unlink(path)
