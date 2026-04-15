#!/usr/bin/env python3
"""
API-сервер для дашборда Лоппи Поппи.
Запуск: python server.py
Открыть: http://localhost:8080
"""

import sqlite3
import json
import math
import os
from collections import defaultdict
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

MONTH_NAMES_RU = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)


def _period_title_ru(period):
    try:
        y, m = period.split("-")
        return f"{MONTH_NAMES_RU[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return period


def _load_byn_rates_by_currency(c, file_id):
    """Курсы НБ из выгрузки: currency -> {date: BYN за 1 единицу валюты}."""
    rows = c.execute(
        """SELECT date, currency_name, rate, multiplier FROM currency_rates
           WHERE file_id=? AND currency_name IN ('EUR','USD','PLN') ORDER BY date""",
        (file_id,),
    ).fetchall()
    maps = defaultdict(dict)
    for date, name, rate, mult in rows:
        if not date or not name:
            continue
        m = float(mult or 1) or 1.0
        r = float(rate or 0) / m
        if r > 0:
            maps[str(name).strip()][date] = r
    return maps


def _byn_rate_for_date(rate_map, date_str):
    """rate_map: date -> rate; ближайший день <= date_str, иначе первый в месяце."""
    if not rate_map:
        return None
    if date_str and date_str in rate_map:
        return rate_map[date_str]
    keys_sorted = sorted(rate_map.keys())
    best = None
    for k in keys_sorted:
        if k <= (date_str or ""):
            best = rate_map[k]
    if best is not None:
        return best
    return rate_map[keys_sorted[0]] if keys_sorted else None


def _amount_to_byn(maps, amount, currency, date_str):
    """Сумма документа в BYN (валюта BYN — как есть; EUR/USD/PLN * курс на дату)."""
    cur = (currency or "BYN").strip()
    a = float(amount or 0)
    if cur == "BYN" or cur == "":
        return a
    mp = maps.get(cur) or maps.get(cur.upper())
    if not mp:
        return a
    r = _byn_rate_for_date(mp, date_str or "")
    if r is None:
        return a
    return a * r


def _usd_rate_resolver(c, file_id):
    """Курс: сколько BYN за 1 USD (как в регистре 1С)."""
    rows = c.execute(
        """SELECT date, rate, multiplier FROM currency_rates
           WHERE file_id=? AND currency_name='USD' ORDER BY date""",
        (file_id,),
    ).fetchall()
    by_date = {}
    for date, rate, mult in rows:
        if not date:
            continue
        m = float(mult or 1) or 1.0
        r = float(rate or 0) / m
        if r > 0:
            by_date[date] = r
    keys_sorted = sorted(by_date.keys())
    avg = sum(by_date.values()) / len(by_date) if by_date else 3.0

    def byn_per_usd(dt):
        if not dt:
            return avg
        if dt in by_date:
            return by_date[dt]
        best = None
        for k in keys_sorted:
            if k <= dt:
                best = by_date[k]
        if best is not None:
            return best
        return by_date[keys_sorted[0]] if keys_sorted else avg

    def to_usd(byn, dt):
        return float(byn) / byn_per_usd(dt)

    return to_usd, avg, byn_per_usd


def _is_salary_bank_wire(content):
    if not content:
        return False
    u = content
    ul = u.lower()
    if "оплату труда" in ul:
        return True
    if "заработная плата" in ul or "ЗАРАБОТНАЯ ПЛАТА" in u:
        return True
    if "отhr 130102" in ul or "OTHR 130102" in u:
        return True
    if "аванс" in ul and ("зарплат" in ul or "ЗАРПЛАТ" in u):
        return True
    return False


def _classify_bank_expense(content, vid):
    u = (content or "").upper()
    vid = vid or ""
    if "ПЕРЕВОД В РАМКАХ ОДНОГО ЮРИДИЧЕСКОГО" in u or "ПЕРЕВОД В РАМКАХ ОДНОГО ЮР" in u:
        return "internal_transfer"
    if _is_salary_bank_wire(content):
        return "salary_bank_wire"
    if vid in ("ПродажаВалюты", "ПокупкаВалюты"):
        return "currency_ops"
    if vid == "ОплатаПоставщикам":
        return "suppliers"
    if "ПОДОХОДНЫЙ" in u:
        if any(z in u for z in ("ЗАЙМ", "ЗАЙМА", "ЗАЙМУ")):
            return "tax_income_loan"
        return "tax_income_payroll"
    if "СТРАХОВЫЕ ВЗНОСЫ" in u:
        return "fszn"
    if "ДОБРОВОЛЬНОЕ СТРАХОВАНИЕ" in u or "МЕДИЦИНСКИХ РАСХОДОВ" in u:
        return "voluntary_insurance"
    if "САМОЗАНЯТ" in u:
        return "freelance_ip"
    if " ПВТ" in u or "% В ПВТ" in u or "1 % В ПВТ" in u or "1% В ПВТ" in u:
        return "pvt_percent"
    if "УПЛАТА НДС" in u or " НДС " in u or u.startswith("НДС "):
        return "vat_payment"
    if "ПЛАТА ЗА ЗАЧИСЛЕНИЕ" in u:
        return "bank_commission"
    if (" ЗАЙМ " in u or " ЗАЙМУ " in u or "ТЕЛО ЗАЙМА" in u or "ПОГАШЕНИЕ ЗАЙМА" in u) and "ПОДОХОДНЫЙ" not in u:
        return "loan_principal"
    if "АРЕНД" in u:
        return "office_rent"
    if "ИНТЕРНЕТ" in u or "СВЯЗЬ" in u or "СВЯЗ" in u:
        return "office_comm"
    if any(z in u for z in ("КАНЦ", "КОМПЬЮТ", "НОУТБУК", "ТЕХНИК")):
        return "office_supplies"
    if "ЭЦП" in u or "ЭЛЕКТРОННО-" in u or "СЕРТИФИКАТ" in u:
        return "office_edo"
    if "ОФФШОР" in u:
        return "office_offshore"
    if any(z in u for z in ("ПЕРСОНАЛ", "РЕКРУТ", "ПОДБОР ПЕРСОНАЛА")):
        return "office_hr"
    if any(z in u for z in ("КОРПОРАТИВ", "ПОДАРОК")):
        return "corp_events"
    if "БАССЕЙН" in u:
        return "corp_pool"
    if any(z in u for z in ("КОМИССИЯ", "ТАРИФН", "ПЛАТА ЗА РАСЧЕТНО", "ПЛАТА ЗА ЗАЧИСЛЕНИЕ")):
        return "bank_commission"
    if "КУРСОВ" in u:
        return "fx_diff"
    if "СПОНСОР" in u or "АУДИТ" in u:
        return "sponsor_audit"
    return "other_bank"


def _classify_operation(content):
    u = (content or "").upper()
    if "ПВТ" in u:
        return "pvt_percent"
    if "ОФФШОР" in u:
        return "office_offshore"
    if "УСЛУГ БАНКА" in u or "УСЛУГ БАНКУ" in u:
        return "bank_commission"
    if "НДС" in u:
        return "vat_payment"
    if "БГС" in u:
        return "bgs_adjustment"
    return "other_operation"


def query_pnl_table(period):
    """Табличный P&L за месяц: BYN и USD по курсу на дату операции."""
    conn = get_db()
    c = conn.cursor()
    file_row = _file_row_for_period(c, period)
    if not file_row:
        conn.close()
        return {"error": "period not found"}
    fid = file_row[0]
    source_filename = file_row[1] or ""

    to_usd, usd_avg, _ = _usd_rate_resolver(c, fid)
    rate_maps = _load_byn_rates_by_currency(c, fid)

    cats = defaultdict(lambda: {"byn": 0.0, "usd": 0.0})

    def add_cat(key, byn, dt):
        b = float(byn)
        cats[key]["byn"] += b
        cats[key]["usd"] += to_usd(b, dt)

    bank_rows = c.execute(
        """SELECT date, amount, content, vid_oplaty, contragent_name, currency
           FROM bank_operations WHERE file_id=? AND type='expense'""",
        (fid,),
    ).fetchall()
    for r in bank_rows:
        dt, amount, content, vid, _cn, currency = r
        byn_amt = _amount_to_byn(rate_maps, amount, currency, dt)
        cat = _classify_bank_expense(content, vid)
        add_cat(cat, byn_amt, dt)

    op_rows = c.execute(
        """SELECT date, amount, content FROM operations WHERE file_id=?""",
        (fid,),
    ).fetchall()
    for r in op_rows:
        dt, amount, content = r
        amt = float(amount or 0)
        if abs(amt) < 1e-9:
            continue
        cat = _classify_operation(content)
        add_cat(cat, amt, dt)

    bgs_accrual = c.execute(
        """SELECT COALESCE(SUM(amount),0) FROM salary_accruals
           WHERE file_id=? AND calc_type='dfcb7b0a-f2b1-4446-96db-cfc6b51b4de0'""",
        (fid,),
    ).fetchone()[0]
    if bgs_accrual:
        mid = period + "-15"
        add_cat("bgs_accrual", float(bgs_accrual), mid)

    pay_lines = c.execute(
        """SELECT employee_name, employee_ref, date, amount FROM salary_payouts WHERE file_id=? ORDER BY employee_name, date""",
        (fid,),
    ).fetchall()
    emp_byn = defaultdict(float)
    emp_usd = defaultdict(float)
    emp_ref_for = {}
    for name, emp_ref, dt, amount in pay_lines:
        k = _norm_employee_name(name or "")
        if not k:
            continue
        b = float(amount or 0)
        emp_byn[k] += b
        emp_usd[k] += to_usd(b, dt)
        r = (emp_ref or "").strip()
        if r and k not in emp_ref_for:
            emp_ref_for[k] = r

    inc_rows = c.execute(
        """SELECT date, amount, currency FROM bank_operations WHERE file_id=? AND type='income'""",
        (fid,),
    ).fetchall()
    income_byn = 0.0
    income_usd = 0.0
    for dt, amount, currency in inc_rows:
        b_byn = _amount_to_byn(rate_maps, amount, currency, dt)
        income_byn += b_byn
        income_usd += to_usd(b_byn, dt)

    int_rows = c.execute(
        """SELECT date, amount, currency FROM bank_operations
           WHERE file_id=? AND type='expense' AND (
             content LIKE '%ПРОЦЕНТ%' OR content LIKE '%процент%'
             OR content LIKE '%ПРСТ%' OR content LIKE '%PRS%'
           )""",
        (fid,),
    ).fetchall()
    bank_interest_byn = sum(_amount_to_byn(rate_maps, a, cur, d) for d, a, cur in int_rows)
    bank_interest_usd = sum(to_usd(_amount_to_byn(rate_maps, a, cur, d), d) for d, a, cur in int_rows)

    internal_byn = cats["internal_transfer"]["byn"]
    salary_wire_byn = cats["salary_bank_wire"]["byn"]

    keys_for_pnl = [
        k for k in cats
        if k not in ("internal_transfer", "salary_bank_wire")
    ]
    pnl_bank_ops_byn = sum(cats[k]["byn"] for k in keys_for_pnl)
    pnl_bank_ops_usd = sum(cats[k]["usd"] for k in keys_for_pnl)

    emp_total_byn = sum(emp_byn.values())
    emp_total_usd = sum(emp_usd.values())

    by_emp_acc, by_ref_acc = _aggregate_salary_accruals(c, fid)
    calc_names = _calc_type_names(c)
    emp_last_payout_dt = {}
    for name, _eref, dt, _amount in pay_lines:
        if not dt:
            continue
        k = _norm_employee_name(name or "")
        if not k:
            continue
        cur = emp_last_payout_dt.get(k)
        if cur is None or dt > cur:
            emp_last_payout_dt[k] = dt
    _usd_ref_default = period + "-15"

    def _payroll_expand_for_pnl(emp_name, emp_ref=""):
        agg = _aggregate_accruals_sql_for_employee(c, fid, emp_name, emp_ref, calc_names)
        if not _acc_bucket_nonempty(agg):
            agg = _pick_salary_agg(by_emp_acc, by_ref_acc, emp_name, emp_ref)
        br = _salary_breakdown_byn(agg)
        k = _norm_employee_name(emp_name or "")
        dt = emp_last_payout_dt.get(k) or _usd_ref_default

        def conv(x):
            return round(to_usd(float(x), dt), 2)

        return {
            "ref_date": dt,
            "oklad_byn": br["accrual_oklad"],
            "oklad_usd": conv(br["accrual_oklad"]),
            "advance_byn": br["advance_in_calc_sheet"],
            "advance_usd": conv(br["advance_in_calc_sheet"]),
            "premiya_byn": br["accrual_premiya"],
            "premiya_usd": conv(br["accrual_premiya"]),
            "other_byn": br["accrual_other"],
            "other_usd": conv(br["accrual_other"]),
            "pn_byn": br["pn_13"],
            "pn_usd": conv(br["pn_13"]),
            "pf_byn": br["pf_1"],
            "pf_usd": conv(br["pf_1"]),
            "fszn_byn": br["fszn_34_est"],
            "fszn_usd": conv(br["fszn_34_est"]),
            "bgs_byn": br["bgs_06_est"],
            "bgs_usd": conv(br["bgs_06_est"]),
            "net_byn": br["net_after_tax"],
            "net_usd": conv(br["net_after_tax"]),
        }

    total_expense_pnl_byn = emp_total_byn + pnl_bank_ops_byn
    total_expense_pnl_usd = emp_total_usd + pnl_bank_ops_usd

    margin_pct = None
    if income_usd > 1e-6:
        margin_pct = round((income_usd - total_expense_pnl_usd) / income_usd * 100, 2)

    exp_for_total = c.execute(
        "SELECT date, amount, currency FROM bank_operations WHERE file_id=? AND type='expense'",
        (fid,),
    ).fetchall()
    bank_total_exp = sum(_amount_to_byn(rate_maps, a, cur, d) for d, a, cur in exp_for_total)

    def row_obj(label, byn, usd, kind="data"):
        return {"label": label, "byn": round(byn, 2), "usd": round(usd, 2), "kind": kind}

    sections = []

    emp_rows_out = []
    for n in sorted(emp_byn.keys(), key=lambda x: (-emp_byn[x], x)):
        er = row_obj(n, emp_byn[n], emp_usd[n])
        er["expand"] = _payroll_expand_for_pnl(n, emp_ref_for.get(n, ""))
        emp_rows_out.append(er)
    sections.append({
        "id": "employees",
        "title": "сотрудники",
        "subtitle": "к выдаче по ведомости; USD — по курсу НБ РБ на дату строки. Разверните строку — детализация начислений и налогов (оценка ФСЗН/БГС).",
        "rows": emp_rows_out,
        "subtotal": row_obj("итого", emp_total_byn, emp_total_usd, "subtotal"),
    })

    tax_rows = []
    if cats["tax_income_payroll"]["byn"]:
        tax_rows.append(row_obj("Подоходный (из зарплаты / выписка)", cats["tax_income_payroll"]["byn"], cats["tax_income_payroll"]["usd"]))
    if cats["fszn"]["byn"]:
        tax_rows.append(row_obj("ФСЗН", cats["fszn"]["byn"], cats["fszn"]["usd"]))
    bgs_byn = cats["voluntary_insurance"]["byn"] + cats["bgs_accrual"]["byn"] + cats["bgs_adjustment"]["byn"]
    bgs_usd = cats["voluntary_insurance"]["usd"] + cats["bgs_accrual"]["usd"] + cats["bgs_adjustment"]["usd"]
    if bgs_byn:
        tax_rows.append(row_obj("Белгосстрах / добровольные взносы / начисления БГС", bgs_byn, bgs_usd))
    tax_sub_byn = sum(r["byn"] for r in tax_rows)
    tax_sub_usd = sum(r["usd"] for r in tax_rows)
    if tax_rows:
        sections.append({
            "id": "taxes",
            "title": "налоги и взносы",
            "rows": tax_rows,
            "subtotal": row_obj("итого", tax_sub_byn, tax_sub_usd, "subtotal"),
        })

    loan_rows = []
    if cats["loan_principal"]["byn"]:
        loan_rows.append(row_obj("Займ (тело / выписка)", cats["loan_principal"]["byn"], cats["loan_principal"]["usd"]))
    if cats["tax_income_loan"]["byn"]:
        loan_rows.append(row_obj("Подоходный из займа", cats["tax_income_loan"]["byn"], cats["tax_income_loan"]["usd"]))
    if loan_rows:
        loan_sub_byn = sum(r["byn"] for r in loan_rows)
        loan_sub_usd = sum(r["usd"] for r in loan_rows)
        sections.append({
            "id": "loans",
            "title": "займы",
            "rows": loan_rows,
            "subtotal": row_obj("итого", loan_sub_byn, loan_sub_usd, "subtotal"),
        })

    ip_rows = []
    if cats["freelance_ip"]["byn"]:
        ip_rows.append(row_obj("Самозанятые и ИП (по тексту платежа)", cats["freelance_ip"]["byn"], cats["freelance_ip"]["usd"]))
    if cats["suppliers"]["byn"]:
        ip_rows.append(row_obj("Оплата поставщикам (вид оплаты 1С)", cats["suppliers"]["byn"], cats["suppliers"]["usd"]))
    if cats["vat_payment"]["byn"]:
        ip_rows.append(row_obj("НДС и пр. (платежи и операции)", cats["vat_payment"]["byn"], cats["vat_payment"]["usd"]))
    if ip_rows:
        ip_sub_byn = sum(r["byn"] for r in ip_rows)
        ip_sub_usd = sum(r["usd"] for r in ip_rows)
        sections.append({
            "id": "contractors",
            "title": "сторонние исполнители и закупки",
            "rows": ip_rows,
            "subtotal": row_obj("итого", ip_sub_byn, ip_sub_usd, "subtotal"),
        })

    fee_rows = []
    if cats["pvt_percent"]["byn"]:
        fee_rows.append(row_obj("1 % ПВТ (банк + документ «Операция»)", cats["pvt_percent"]["byn"], cats["pvt_percent"]["usd"]))
    if cats["sponsor_audit"]["byn"]:
        fee_rows.append(row_obj("Спонсорская помощь / аудит", cats["sponsor_audit"]["byn"], cats["sponsor_audit"]["usd"]))
    if fee_rows:
        fee_sub_byn = sum(r["byn"] for r in fee_rows)
        fee_sub_usd = sum(r["usd"] for r in fee_rows)
        sections.append({
            "id": "fees",
            "title": "сборы и прочее",
            "rows": fee_rows,
            "subtotal": row_obj("итого", fee_sub_byn, fee_sub_usd, "subtotal"),
        })

    office_labels = (
        ("office_rent", "Аренда / коммуналка"),
        ("office_comm", "Интернет / связь"),
        ("office_supplies", "Техника, канцтовары"),
        ("office_edo", "ЭЦП, доступ к справочным системам"),
        ("office_offshore", "Оффшорный сбор за эл. сервисы"),
        ("office_hr", "Подбор персонала"),
        ("bank_commission", "Комиссия банка, РКО"),
        ("other_operation", "Прочие операции 1С"),
        ("other_bank", "Прочие списания по банку"),
    )
    office_rows = []
    for key, label in office_labels:
        if cats[key]["byn"]:
            office_rows.append(row_obj(label, cats[key]["byn"], cats[key]["usd"]))
    if cats["currency_ops"]["byn"]:
        office_rows.append(row_obj("Покупка / продажа валюты (вид оплаты)", cats["currency_ops"]["byn"], cats["currency_ops"]["usd"]))
    if cats["fx_diff"]["byn"]:
        office_rows.append(row_obj("Курсовые разницы (по выписке)", cats["fx_diff"]["byn"], cats["fx_diff"]["usd"]))
    if office_rows:
        off_sub_byn = sum(r["byn"] for r in office_rows)
        off_sub_usd = sum(r["usd"] for r in office_rows)
        sections.append({
            "id": "office",
            "title": "офис и операционные",
            "rows": office_rows,
            "subtotal": row_obj("итого", off_sub_byn, off_sub_usd, "subtotal"),
        })

    corp_rows = []
    if cats["corp_events"]["byn"]:
        corp_rows.append(row_obj("Корпоратив / подарки", cats["corp_events"]["byn"], cats["corp_events"]["usd"]))
    if cats["corp_pool"]["byn"]:
        corp_rows.append(row_obj("Бассейн", cats["corp_pool"]["byn"], cats["corp_pool"]["usd"]))
    if corp_rows:
        corp_sub_byn = sum(r["byn"] for r in corp_rows)
        corp_sub_usd = sum(r["usd"] for r in corp_rows)
        sections.append({
            "id": "corp",
            "title": "корпоратив и льготы",
            "rows": corp_rows,
            "subtotal": row_obj("итого", corp_sub_byn, corp_sub_usd, "subtotal"),
        })

    foot_rows = []
    if internal_byn:
        foot_rows.append(row_obj("Переводы между своими счетами (не расход P&L)", internal_byn, cats["internal_transfer"]["usd"]))
    if salary_wire_byn:
        foot_rows.append(row_obj("Справочно: зарплата по банку (дублирует ведомость)", salary_wire_byn, cats["salary_bank_wire"]["usd"]))
    if bank_interest_byn:
        foot_rows.append(row_obj("Проценты банка (если есть в выписке)", bank_interest_byn, bank_interest_usd))

    conn.close()

    return {
        "period": period,
        "period_title": _period_title_ru(period),
        "source_file": source_filename,
        "byn_sources": (
            "BYN: операции банка и валютные суммы приведены по курсам НБ из этой же выгрузки 1С. "
            "Блок «сотрудники» — суммы «к выдаче» из документов «Выплата по ведомости» (таблица salary_payouts). "
            "Разворот строки — из «Начисление заработной платы» (salary_accruals) и справочника видов расчёта; "
            "ФСЗН 34% и Белгосстрах 0,6% — оценка от базы взносов по правилам зарплатного отчёта."
        ),
        "usd_note": "Поступления в EUR/USD/PLN сначала в BYN по курсу НБ на дату; затем USD — по курсу USD на дату. При отсутствии курса на дату — ближайший предыдущий день в выгрузке.",
        "usd_avg": round(usd_avg, 4),
        "sections": sections,
        "summary": {
            "expense_pnl_byn": round(total_expense_pnl_byn, 2),
            "expense_pnl_usd": round(total_expense_pnl_usd, 2),
            "income_byn": round(income_byn, 2),
            "income_usd": round(income_usd, 2),
            "margin_pct": margin_pct,
            "bank_expense_total_byn": round(float(bank_total_exp), 2),
            "internal_transfer_byn": round(internal_byn, 2),
        },
        "footnotes": foot_rows,
        "bank_interest_byn": round(bank_interest_byn, 2),
        "bank_interest_usd": round(bank_interest_usd, 2),
    }

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loppipoppi.db")
FRONTEND_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")


def _sanitize_for_json(obj):
    """Убирает NaN/Inf — иначе JSON.parse в браузере падает."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


def _api_path_key(path):
    p = (path or "").strip()
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _file_row_for_period(c, period):
    """При нескольких XML с одним period=YYYY-MM берём последний импорт по id (иначе ведомость и начисления могут относиться к разным file_id → нули в развороте)."""
    return c.execute(
        "SELECT id, filename FROM files WHERE period=? ORDER BY id DESC LIMIT 1",
        (period,),
    ).fetchone()


def _file_id_for_period(c, period):
    row = _file_row_for_period(c, period)
    return row[0] if row else None


# Виды расчётов из выгрузки 1С (Бухгалтерия)
_CALC_OKLAD = "42147e61-9a0d-4683-bde8-af4751f4314c"
_CALC_PN = "a0c8cdb2-17cf-4b25-ade4-e263ebacf8dc"
_CALC_PF = "dfcb7b0a-f2b1-4446-96db-cfc6b51b4de0"
_CALC_ADVANCE_SHEET = "5b0c37b5-b206-4923-93ee-bb9e423a779a"
_CALC_PREMIYA = "d719d05e-79cb-44a8-91dc-677eedde4aa3"
# Не входят в базу отчислений ФСЗН/БГС (оценка)
_CALC_EXCLUDE_CONTRIB = frozenset(
    {
        "42a8c42d-e17d-11ec-a20b-c46e1f00354f",  # Оплата по договору подряда
        "5632b773-b0a3-42ba-9c82-6092f1c73929",  # Дополнительный отпуск
        "83c9fef0-086d-42dc-9f24-376893de5ba6",  # Отпуск очередной
        "1503710f-e070-4402-8836-229eb199f736",  # Отпуск будущего периода
    }
)
_FSZN_RATE = 0.34
_BGS_RATE = 0.006


def _calc_type_names(c):
    try:
        return {r[0]: (r[1] or "") for r in c.execute("SELECT ref, name FROM payroll_calc_types").fetchall()}
    except sqlite3.OperationalError:
        return {}


def _is_premiya_calc(calc_ref, names):
    if calc_ref == _CALC_PREMIYA:
        return True
    n = (names.get(calc_ref) or "").lower()
    return "премия" in n


def _exclude_from_contrib_by_name(name):
    n = (name or "").lower()
    if "отпуск" in n:
        return True
    if "подряд" in n:
        return True
    if "мат" in n and "помощ" in n:
        return True
    return False


def _new_acc_bucket():
    return {
        "oklad": 0.0,
        "premiya": 0.0,
        "other_accrual": 0.0,
        "contrib_extra": 0.0,
        "pn": 0.0,
        "pf": 0.0,
        "advance_sheet": 0.0,
    }


def _norm_employee_name(s):
    """ФИО для сопоставления ведомости и начислений: NBSP/узкие пробелы → обычный, схлопывание."""
    if not s:
        return ""
    t = (
        str(s)
        .replace("\u00a0", " ")
        .replace("\u2009", " ")
        .replace("\u202f", " ")
        .replace("\u2007", " ")
    )
    return " ".join(t.split()).strip()


# Сравнение employee_name в SQLite: те же замены, что в _norm_employee_name (CHAR(160)=NBSP, 8239=NNBSP).
_EMP_NAME_SQL = (
    "TRIM(REPLACE(REPLACE(COALESCE(employee_name,''), CHAR(160), ' '), CHAR(8239), ' ')) = "
    "TRIM(REPLACE(REPLACE(?, CHAR(160), ' '), CHAR(8239), ' '))"
)


def _coerce_is_accrual(is_acc):
    """SQLite / разные выгрузки: 0/1, bool, строка true/false."""
    if is_acc is None:
        return 0
    if isinstance(is_acc, (bytes, bytearray)):
        try:
            is_acc = is_acc.decode("utf-8", errors="ignore")
        except Exception:
            return 0
    if isinstance(is_acc, str):
        t = is_acc.strip().lower()
        return 1 if t in ("1", "true", "yes", "да") else 0
    try:
        return 1 if int(float(is_acc)) != 0 else 0
    except (TypeError, ValueError):
        return 1 if is_acc else 0


def _apply_accrual_to_bucket(d, names, calc_type, is_acc, amount):
    """Одна строка начисления/удержания → поля ведра (как в parse → salary_accruals)."""
    ct = (calc_type or "").strip()
    nm = names.get(ct, "")
    amt = float(amount or 0)
    acc = _coerce_is_accrual(is_acc)
    if acc:
        if ct == _CALC_OKLAD:
            d["oklad"] += amt
        elif _is_premiya_calc(ct, names):
            d["premiya"] += amt
        else:
            d["other_accrual"] += amt
            if ct not in _CALC_EXCLUDE_CONTRIB and not _exclude_from_contrib_by_name(nm):
                d["contrib_extra"] += amt
    else:
        if ct == _CALC_PN:
            d["pn"] += amt
        elif ct == _CALC_PF:
            d["pf"] += amt
        elif ct == _CALC_ADVANCE_SHEET:
            d["advance_sheet"] += amt


def _aggregate_accruals_sql_for_employee(c, fid, emp_name, emp_ref, names):
    """Прямой запрос к salary_accruals по ФИО и/или employee_ref — разворот P&L не зависит от промежуточных словарей."""
    d = _new_acc_bucket()
    en = _norm_employee_name(emp_name or "")
    er = (emp_ref or "").strip()
    if not en and not er:
        return d
    parts = []
    params = [fid]
    if en:
        parts.append(_EMP_NAME_SQL)
        params.append(en)
    if er:
        parts.append("TRIM(COALESCE(employee_ref, '')) = ?")
        params.append(er)
    sql = "SELECT calc_type, is_accrual, amount FROM salary_accruals WHERE file_id=? AND (" + " OR ".join(parts) + ")"
    for calc_type, is_acc, amt in c.execute(sql, tuple(params)).fetchall():
        _apply_accrual_to_bucket(d, names, calc_type, is_acc, amt)
    return d


def _acc_bucket_nonempty(d):
    return (
        abs(float(d.get("oklad") or 0))
        + abs(float(d.get("premiya") or 0))
        + abs(float(d.get("other_accrual") or 0))
        + abs(float(d.get("pn") or 0))
        + abs(float(d.get("pf") or 0))
        + abs(float(d.get("advance_sheet") or 0))
    ) > 1e-9


def _aggregate_salary_accruals(c, fid):
    """Суммы по видам из salary_accruals (BYN). Два индекса: по ФИО (trim) и по employee_ref — ведомость и начисление могут расходиться в пробелах/пустом ФИО."""
    names = _calc_type_names(c)
    by_emp = {}
    by_ref = {}

    for ename, eref, calc_type, is_acc, amount in c.execute(
        "SELECT employee_name, employee_ref, calc_type, is_accrual, amount FROM salary_accruals WHERE file_id=?",
        (fid,),
    ).fetchall():
        nm = _norm_employee_name(ename or "")
        rf = (eref or "").strip()
        buckets = []
        if nm:
            buckets.append(by_emp.setdefault(nm, _new_acc_bucket()))
        if rf:
            buckets.append(by_ref.setdefault(rf, _new_acc_bucket()))
        if not buckets:
            continue
        for d in buckets:
            _apply_accrual_to_bucket(d, names, calc_type, is_acc, amount)
    return by_emp, by_ref


def _pick_salary_agg(by_emp, by_ref, name, ref=None):
    """Сопоставление ведомости (ФИО) с начислениями: имя, затем ref, затем совпадение ФИО без учёта регистра."""
    z = _new_acc_bucket()
    n = _norm_employee_name(name or "")
    r = (ref or "").strip()
    a = by_emp.get(n)
    if a is None:
        a = z
    if not _acc_bucket_nonempty(a) and r:
        a = by_ref.get(r) or a
    if not _acc_bucket_nonempty(a) and n:
        nl = n.lower()
        for k, v in by_emp.items():
            if k.strip().lower() == nl and _acc_bucket_nonempty(v):
                return v
    if _acc_bucket_nonempty(a):
        return a
    if r:
        return by_ref.get(r) or z
    return z


def _salary_breakdown_byn(a):
    """Расчёт полей в BYN из агрегата _aggregate_salary_accruals."""
    oklad = round(a["oklad"], 2)
    premiya = round(a["premiya"], 2)
    other_acc = round(a["other_accrual"], 2)
    gross_sheet = round(oklad + premiya + other_acc, 2)
    contrib_base = max(0.0, round(a["oklad"] + a["premiya"] + a["contrib_extra"], 2))
    fszn = round(contrib_base * _FSZN_RATE, 2)
    bgs = round(contrib_base * _BGS_RATE, 2)
    pn = round(a["pn"], 2)
    pf = round(a["pf"], 2)
    adv_sheet = round(a["advance_sheet"], 2)
    net_calc = round(gross_sheet - pn - pf, 2)
    company_cost = round(gross_sheet + fszn + bgs, 2)
    return {
        "accrual_oklad": oklad,
        "accrual_premiya": premiya,
        "accrual_other": other_acc,
        "advance_in_calc_sheet": adv_sheet,
        "pn_13": pn,
        "pf_1": pf,
        "fszn_34_est": fszn,
        "bgs_06_est": bgs,
        "gross_accruals": gross_sheet,
        "net_after_tax": net_calc,
        "company_cost_est": company_cost,
        "contrib_base_est": round(contrib_base, 2),
        "has_premiya": premiya > 0.005,
    }


def query_periods():
    conn = get_db()
    rows = conn.execute("SELECT id, period, filename FROM files ORDER BY period DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_overview(period):
    conn = get_db()
    c = conn.cursor()

    fid = _file_id_for_period(c, period)
    if fid is None:
        conn.close()
        return {"error": "period not found"}
    rate_maps = _load_byn_rates_by_currency(c, fid)
    bank_all = c.execute(
        """SELECT date, type, amount, currency, vid_oplaty, contragent_name
           FROM bank_operations WHERE file_id=?""",
        (fid,),
    ).fetchall()

    income = 0.0
    expense = 0.0
    daily_acc = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    cat_acc = defaultdict(float)
    ctr_acc = defaultdict(float)

    for date, typ, amount, currency, vid, cname in bank_all:
        byn = _amount_to_byn(rate_maps, amount, currency, date)
        if typ == "income":
            income += byn
            daily_acc[date]["income"] += byn
        else:
            expense += byn
            daily_acc[date]["expense"] += byn
            cat_acc[vid or ""] += byn
            if cname:
                ctr_acc[cname] += byn

    daily = [{"date": d, "income": daily_acc[d]["income"], "expense": daily_acc[d]["expense"]} for d in sorted(daily_acc.keys())]
    categories = sorted(({"vid_oplaty": k, "total": v} for k, v in cat_acc.items()), key=lambda x: -x["total"])
    top_contragents = sorted(({"contragent_name": k, "total": v} for k, v in ctr_acc.items()), key=lambda x: -x["total"])[:10]

    conn.close()
    return {
        "income": income,
        "expense": expense,
        "daily": daily,
        "categories": categories,
        "top_contragents": top_contragents,
        "currency_note": "Суммы в EUR, USD, PLN приведены к BYN по курсу НБ РБ на дату операции из выгрузки.",
    }


def query_salary(period):
    conn = get_db()
    c = conn.cursor()
    fid = _file_id_for_period(c, period)
    if fid is None:
        conn.close()
        return {"error": "period not found"}

    payouts = c.execute(
        """
        SELECT employee_name,
               MAX(COALESCE(employee_ref, '')) as employee_ref,
               SUM(CASE WHEN payout_type='Зарплата' THEN amount ELSE 0 END) as salary,
               SUM(CASE WHEN payout_type='Аванс' THEN amount ELSE 0 END) as advance,
               SUM(CASE WHEN payout_type='Прочее' THEN amount ELSE 0 END) as other,
               SUM(amount) as total
        FROM salary_payouts WHERE file_id=?
        GROUP BY employee_name ORDER BY total DESC
        """,
        (fid,),
    ).fetchall()

    by_emp_acc, by_ref_acc = _aggregate_salary_accruals(c, fid)
    calc_names = _calc_type_names(c)

    employees_detail = []
    payout_by_name = {}
    for r in payouts:
        k = _norm_employee_name(r["employee_name"] or "")
        if not k:
            continue
        d = dict(r)
        if k in payout_by_name:
            prev = payout_by_name[k]
            prev["salary"] = float(prev["salary"] or 0) + float(d["salary"] or 0)
            prev["advance"] = float(prev["advance"] or 0) + float(d["advance"] or 0)
            prev["other"] = float(prev["other"] or 0) + float(d["other"] or 0)
            prev["total"] = float(prev["total"] or 0) + float(d["total"] or 0)
            pr = str(prev.get("employee_ref") or "").strip()
            dr = str(d.get("employee_ref") or "").strip()
            if not pr and dr:
                prev["employee_ref"] = dr
        else:
            payout_by_name[k] = d

    raw_pay = c.execute(
        "SELECT employee_name, payout_type, date, amount FROM salary_payouts WHERE file_id=?",
        (fid,),
    ).fetchall()
    to_usd, usd_avg, _ = _usd_rate_resolver(c, fid)
    usd_tot = defaultdict(lambda: {"salary": 0.0, "advance": 0.0, "other": 0.0, "total": 0.0})
    for ename, ptype, dt, amt in raw_pay:
        k = _norm_employee_name(ename or "")
        if not k:
            continue
        u_amt = to_usd(float(amt or 0), str(dt or "")[:10])
        b = usd_tot[k]
        pt = (ptype or "").strip()
        if pt == "Зарплата":
            b["salary"] += u_amt
        elif pt == "Аванс":
            b["advance"] += u_amt
        else:
            b["other"] += u_amt
        b["total"] += u_amt

    for ename in sorted(payout_by_name.keys(), key=lambda n: -float(payout_by_name[n]["total"] or 0)):
        p = payout_by_name[ename]
        ref = (p.get("employee_ref") or "").strip()
        agg = _aggregate_accruals_sql_for_employee(c, fid, ename, ref, calc_names)
        if not _acc_bucket_nonempty(agg):
            agg = _pick_salary_agg(by_emp_acc, by_ref_acc, ename, ref)
        br = _salary_breakdown_byn(agg)
        employees_detail.append(
            {
                "employee_name": ename,
                "payout_salary": round(float(p["salary"] or 0), 2),
                "payout_advance": round(float(p["advance"] or 0), 2),
                "payout_other": round(float(p["other"] or 0), 2),
                "payout_total": round(float(p["total"] or 0), 2),
                **br,
            }
        )

    for ename, a in by_emp_acc.items():
        if ename in payout_by_name:
            continue
        br = _salary_breakdown_byn(a)
        employees_detail.append(
            {
                "employee_name": ename,
                "payout_salary": 0.0,
                "payout_advance": 0.0,
                "payout_other": 0.0,
                "payout_total": 0.0,
                **br,
            }
        )

    employees_detail.sort(key=lambda r: -r["company_cost_est"])

    accrual_summary = []
    for ename in sorted(by_emp_acc.keys(), key=lambda n: -(by_emp_acc[n]["oklad"] + by_emp_acc[n]["premiya"] + by_emp_acc[n]["other_accrual"])):
        x = by_emp_acc[ename]
        accrual_summary.append(
            {
                "employee_name": ename,
                "gross": round(x["oklad"] + x["premiya"] + x["other_accrual"], 2),
                "pn": round(x["pn"], 2),
                "pf": round(x["pf"], 2),
            }
        )

    payouts_out = []
    for ename in sorted(payout_by_name.keys(), key=lambda n: -float(payout_by_name[n]["total"] or 0)):
        p = dict(payout_by_name[ename])
        p["employee_name"] = ename
        u = usd_tot.get(ename) or {}
        p["salary_usd"] = round(float(u.get("salary") or 0), 2)
        p["advance_usd"] = round(float(u.get("advance") or 0), 2)
        p["other_usd"] = round(float(u.get("other") or 0), 2)
        p["total_usd"] = round(float(u.get("total") or 0), 2)
        payouts_out.append(p)

    adv_raw = c.execute(
        """SELECT date, employee_name, amount FROM advance_reports
           WHERE file_id=? ORDER BY date DESC, employee_name""",
        (fid,),
    ).fetchall()
    advance_reports = []
    for r in adv_raw:
        rr = dict(r)
        advance_reports.append(
            {
                "date": (rr.get("date") or "")[:10],
                "employee_name": (rr.get("employee_name") or "").strip() or "—",
                "amount": round(float(rr.get("amount") or 0), 2),
            }
        )
    advance_reports_total = round(sum(x["amount"] for x in advance_reports), 2)

    conn.close()
    return {
        "period": period,
        "payouts": payouts_out,
        "accruals": accrual_summary,
        "employees_detail": employees_detail,
        "advance_reports": advance_reports,
        "advance_reports_total": advance_reports_total,
        "advance_reports_note": (
            "Документы 1С «Авансовый отчёт»: сумма документа и дата из выгрузки. "
            "Не смешивается с ведомостью зарплаты — это подотчётные расходы сотрудников."
        ),
        "payouts_usd_note": (
            "Суммы в USD: каждая строка «Выплата по ведомости» переведена из BYN по курсу USD из регистра «Курсы валют» "
            "выгрузки 1С на дату документа; при отсутствии курса на дату — ближайший предыдущий день в файле. "
            f"Средний курс USD в файле (справочно): {round(float(usd_avg or 0), 4)} BYN/USD."
        ),
        "notes": (
            "ФСЗН (34%) и БГС (0,6%) оценены от базы: оклад + премия + прочие начисления, "
            "входящие в объект страхования (без отпусков, подряда, мат. помощи по справочнику). "
            "Выплаты «Зарплата» / «Аванс» / «Прочее» — из ведомости; аванс в расчётном листе — удержание к основной выплате."
        ),
    }


def query_currency(period):
    conn = get_db()
    c = conn.cursor()
    fid = _file_id_for_period(c, period)
    if fid is None:
        conn.close()
        return {"error": "period not found"}

    rates = c.execute("""
        SELECT date, currency_name, rate/multiplier as rate
        FROM currency_rates WHERE file_id=? AND currency_name IN ('EUR','USD','PLN')
        ORDER BY date, currency_name
    """, (fid,)).fetchall()

    conn.close()
    return {"rates": [dict(r) for r in rates]}


def query_staff():
    conn = get_db()
    active = conn.execute("SELECT * FROM employees WHERE active=1 ORDER BY hired").fetchall()
    fired = conn.execute("SELECT * FROM employees WHERE active=0 AND fired!='' ORDER BY fired DESC").fetchall()
    conn.close()
    return {
        "active": [dict(r) for r in active],
        "fired": [dict(r) for r in fired],
    }


def query_assets():
    conn = get_db()
    assets = conn.execute("SELECT name, inv_number, commissioned_date FROM fixed_assets ORDER BY commissioned_date DESC").fetchall()
    conn.close()
    return {"assets": [dict(r) for r in assets]}


def query_pnl(q):
    """q — результат parse_qs. При format=table отдаётся JSON для вкладки «P&L (таблица)» (тот же хост, что и /api/pnl)."""
    period = (q.get("period") or [""])[0]
    fmt = (q.get("format") or [""])[0]
    if fmt == "table":
        return query_pnl_table(period)

    conn = get_db()
    c = conn.cursor()
    fid = _file_id_for_period(c, period)
    if fid is None:
        conn.close()
        return {"error": "period not found"}
    rate_maps = _load_byn_rates_by_currency(c, fid)

    expenses_raw = c.execute("""
        SELECT date, amount, contragent_name, content, vid_oplaty, currency
        FROM bank_operations WHERE file_id=? AND type='expense'
    """, (fid,)).fetchall()
    income_raw = c.execute("""
        SELECT date, amount, contragent_name, content, currency
        FROM bank_operations WHERE file_id=? AND type='income'
    """, (fid,)).fetchall()

    expenses = []
    for date, amount, contragent_name, content, vid_oplaty, currency in expenses_raw:
        byn = _amount_to_byn(rate_maps, amount, currency, date)
        expenses.append({
            "date": date,
            "amount": amount,
            "amount_byn": byn,
            "contragent_name": contragent_name,
            "content": content,
            "vid_oplaty": vid_oplaty,
            "currency": currency,
        })

    income = []
    for date, amount, contragent_name, content, currency in income_raw:
        byn = _amount_to_byn(rate_maps, amount, currency, date)
        income.append({
            "date": date,
            "amount": amount,
            "amount_byn": byn,
            "contragent_name": contragent_name,
            "content": content,
            "currency": currency,
        })

    payouts = c.execute("""
        SELECT employee_name, payout_type, SUM(amount) as total
        FROM salary_payouts WHERE file_id=?
        GROUP BY employee_name, payout_type
    """, (fid,)).fetchall()

    usd_avg = c.execute("""
        SELECT AVG(rate/multiplier) FROM currency_rates
        WHERE file_id=? AND currency_name='USD'
    """, (fid,)).fetchone()[0] or 1

    total_income = sum(x["amount_byn"] for x in income)
    total_expense = sum(x["amount_byn"] for x in expenses)
    tax_total = sum(x["amount_byn"] for x in expenses if "ПОДОХОДНЫЙ" in (x.get("content") or ""))
    fszn_total = sum(x["amount_byn"] for x in expenses if "СТРАХОВЫЕ ВЗНОСЫ" in (x.get("content") or ""))
    salary_bank = sum(x["amount_byn"] for x in expenses if _is_salary_bank_wire(x.get("content")))
    salary_payout = c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM salary_payouts WHERE file_id=?", (fid,)
    ).fetchone()[0]
    other_bank = total_expense - tax_total - fszn_total - salary_bank

    vid_acc = defaultdict(float)
    for x in expenses:
        vid_acc[x.get("vid_oplaty") or ""] += x["amount_byn"]
    expense_by_vid = sorted(
        ({"vid": k, "total": v} for k, v in vid_acc.items()),
        key=lambda r: -r["total"],
    )

    conn.close()
    return {
        "expenses": expenses,
        "income": income,
        "payouts": [dict(r) for r in payouts],
        "usd_avg": usd_avg,
        "currency_note": "Поступления и списания в EUR/USD/PLN в итогах приведены к BYN по курсу НБ на дату.",
        "totals": {
            "total_income": total_income,
            "total_expense": total_expense,
            "tax_podoh": tax_total,
            "fszn": fszn_total,
            "salary_bank": salary_bank,
            "salary_payout": salary_payout,
            "other_bank": other_bank,
            "expense_by_vid": expense_by_vid,
        },
    }


def query_history():
    """Multi-period comparison data."""
    conn = get_db()
    c = conn.cursor()

    cash_acc = {}
    for (p,) in c.execute("SELECT DISTINCT period FROM files ORDER BY period"):
        cash_acc[p] = {"income": 0.0, "expense": 0.0}

    bank_rows = c.execute("""
        SELECT f.period, b.date, b.type, b.amount, b.currency, b.file_id
        FROM files f
        JOIN bank_operations b ON b.file_id = f.id
        ORDER BY f.period, b.date
    """).fetchall()
    maps_cache = {}

    def maps_for(fid):
        if fid not in maps_cache:
            maps_cache[fid] = _load_byn_rates_by_currency(c, fid)
        return maps_cache[fid]

    for period, date, typ, amount, currency, fid in bank_rows:
        m = maps_for(fid)
        byn = _amount_to_byn(m, amount, currency, date)
        if typ == "income":
            cash_acc[period]["income"] += byn
        else:
            cash_acc[period]["expense"] += byn
    rows = [
        {"period": p, "income": v["income"], "expense": v["expense"]}
        for p, v in sorted(cash_acc.items(), key=lambda x: x[0])
    ]

    sal_rows = c.execute("""
        SELECT f.period, COALESCE(SUM(sp.amount), 0) as payout
        FROM files f
        LEFT JOIN salary_payouts sp ON sp.file_id = f.id
        GROUP BY f.period ORDER BY f.period
    """).fetchall()

    staff_rows = c.execute("""
        SELECT f.period, COUNT(DISTINCT sp.employee_name) as headcount
        FROM files f
        LEFT JOIN salary_payouts sp ON sp.file_id = f.id
        GROUP BY f.period ORDER BY f.period
    """).fetchall()

    conn.close()
    return {
        "cashflow": [dict(r) for r in rows],
        "salary": [dict(r) for r in sal_rows],
        "headcount": [dict(r) for r in staff_rows],
    }


API_ROUTES = {
    "/api/periods": lambda q: query_periods(),
    "/api/overview": lambda q: query_overview(q.get("period", [""])[0]),
    "/api/salary": lambda q: query_salary(q.get("period", [""])[0]),
    "/api/currency": lambda q: query_currency(q.get("period", [""])[0]),
    "/api/staff": lambda q: query_staff(),
    "/api/assets": lambda q: query_assets(),
    "/api/pnl": lambda q: query_pnl(q),
    "/api/pnl-table": lambda q: query_pnl_table(q.get("period", [""])[0]),
    "/api/pnl_table": lambda q: query_pnl_table(q.get("period", [""])[0]),
    "/api/history": lambda q: query_history(),
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_PATH, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path.startswith("/api/"):
            api_key = _api_path_key(path)
            handler = API_ROUTES.get(api_key)
            if handler:
                try:
                    result = handler(query)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    safe = _sanitize_for_json(result)
                    self.wfile.write(json.dumps(safe, ensure_ascii=False, default=str).encode("utf-8"))
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"error": "unknown_api", "path": path, "hint": "Перезапустите server.py — возможно, старая версия без этого маршрута."},
                        ensure_ascii=False,
                    ).encode("utf-8")
                )
            return

        # Serve frontend files
        super().do_GET()

    def log_message(self, format, *args):
        if "/api/" in str(args[0]):
            print(f"  API: {args[0]}")


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ База не найдена: {DB_PATH}")
        print(f"   Сначала запустите: python parse_1c.py <путь_к_XML>")
        return

    if not os.path.exists(FRONTEND_PATH):
        os.makedirs(FRONTEND_PATH, exist_ok=True)

    candidates = [8080, 8765, 8877, 9000] + list(range(8081, 8096))
    server = None
    port = 8080
    for port in candidates:
        try:
            server = HTTPServer(("0.0.0.0", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        print("❌ Не удалось занять порт из списка 8080–8095, 8765, 8877, 9000")
        return
    print(f"🚀 Сервер запущен: http://localhost:{port}")
    if port != 8080:
        print(f"   (порт 8080 занят — откройте именно этот адрес, вкладка P&L и API на нём)")
    print(f"🗄  База данных: {DB_PATH}")
    print(f"📁 Фронтенд: {FRONTEND_PATH}")
    print(f"   Нажмите Ctrl+C для остановки\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹  Сервер остановлен")
        server.server_close()


if __name__ == "__main__":
    main()
