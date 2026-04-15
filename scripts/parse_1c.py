#!/usr/bin/env python3
"""
Лоппи Поппи — парсер выгрузок 1С в SQLite.

Использование:
    python parse_1c.py /path/to/xml/files/
    python parse_1c.py /path/to/single_file.xml

Парсит все .xml файлы из указанной папки (или один файл),
извлекает финансовые данные и сохраняет в loppipoppi.db.
"""

import xml.etree.ElementTree as ET
import sqlite3
import os
import sys
import glob
import hashlib
import re
from collections import defaultdict
from datetime import datetime


DB_NAME = "loppipoppi.db"


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            filename TEXT UNIQUE,
            hash TEXT,
            parsed_at TEXT,
            period TEXT
        );

        CREATE TABLE IF NOT EXISTS employees (
            ref TEXT PRIMARY KEY,
            name TEXT,
            hired TEXT,
            fired TEXT,
            gender TEXT,
            contract_type TEXT,
            work_type TEXT,
            contract_end TEXT,
            active INTEGER
        );

        CREATE TABLE IF NOT EXISTS bank_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            date TEXT,
            type TEXT,
            amount REAL,
            contragent_ref TEXT,
            contragent_name TEXT,
            content TEXT,
            vid_oplaty TEXT,
            currency TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS payroll_calc_types (
            ref TEXT PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE IF NOT EXISTS salary_accruals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            period TEXT,
            employee_ref TEXT,
            employee_name TEXT,
            calc_type TEXT,
            is_accrual INTEGER,
            amount REAL,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS salary_payouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            date TEXT,
            employee_ref TEXT,
            employee_name TEXT,
            payout_type TEXT,
            amount REAL,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS currency_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            date TEXT,
            currency_ref TEXT,
            currency_name TEXT,
            rate REAL,
            multiplier REAL,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS fixed_assets (
            ref TEXT,
            file_id INTEGER,
            name TEXT,
            inv_number TEXT,
            commissioned_date TEXT,
            PRIMARY KEY (ref, file_id),
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            date TEXT,
            amount REAL,
            content TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS advance_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            date TEXT,
            employee_ref TEXT,
            employee_name TEXT,
            amount REAL,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS contragents (
            ref TEXT PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE IF NOT EXISTS pnl_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            period TEXT,
            total_income REAL,
            total_expense REAL,
            salary_payout REAL,
            tax_income REAL,
            fszn REAL,
            bgs REAL,
            contractors REAL,
            pvt REAL,
            office REAL,
            benefits REAL,
            fx_diff REAL,
            bank_fees REAL,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );
    """)

    conn.commit()
    return conn


def file_hash(filepath):
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_file(filepath, conn):
    fname = os.path.basename(filepath)
    fhash = file_hash(filepath)

    c = conn.cursor()
    c.execute("SELECT id, hash FROM files WHERE filename = ?", (fname,))
    row = c.fetchone()
    ns = {
        "v8": "http://v8.1c.ru/8.1/data/enterprise/current-config",
        "V8Exch": "http://www.1c.ru/V8/1CV8DtUD/",
    }

    if row and row[1] == fhash:
        print(f"  ⏭  {fname} — не изменился, пропускаю")
        tree = ET.parse(filepath)
        data = tree.getroot().find(".//V8Exch:Data", ns)
        if data is not None:
            for cat in data.findall("v8:CatalogObject.ВидыРасчетов", ns):
                is_folder = cat.find("v8:IsFolder", ns)
                if is_folder is not None and is_folder.text == "true":
                    continue
                ref = cat.find("v8:Ref", ns)
                desc = cat.find("v8:Description", ns)
                if ref is not None and ref.text:
                    c.execute(
                        "INSERT OR REPLACE INTO payroll_calc_types (ref, name) VALUES (?,?)",
                        (ref.text.strip(), desc.text.strip() if desc is not None and desc.text else ""),
                    )
            conn.commit()
        return row[0]

    print(f"  📄 Парсинг {fname} ({os.path.getsize(filepath) / 1024 / 1024:.1f} MB)...")

    tree = ET.parse(filepath)
    root = tree.getroot()
    data = root.find(".//V8Exch:Data", ns)
    if data is None:
        print(f"  ⚠️  Нет секции Data в {fname}")
        return None

    # Detect period from first bank statement date
    period = ""
    for doc in data.findall("v8:DocumentObject.ВыпискаБанка", ns):
        d = doc.find("v8:Date", ns)
        if d is not None and d.text:
            period = d.text[:7]  # YYYY-MM
            break
    if not period:
        m = re.search(r"(20\d{2})[_\s-](\d{2})", fname)
        if m:
            period = f"{m.group(1)}-{m.group(2)}"
    if not period:
        for doc in data.findall("v8:DocumentObject.НачислениеЗаработнойПлаты", ns):
            de = doc.find("v8:Date", ns)
            if de is not None and de.text and len(de.text) >= 7:
                period = de.text[:7]
                break

    # Upsert file record
    if row:
        file_id = row[0]
        c.execute("UPDATE files SET hash=?, parsed_at=?, period=? WHERE id=?",
                  (fhash, datetime.now().isoformat(), period, file_id))
        # Clear old data for this file
        for table in ["bank_operations", "salary_accruals", "salary_payouts",
                      "currency_rates", "operations", "advance_reports", "pnl_summary"]:
            c.execute(f"DELETE FROM {table} WHERE file_id = ?", (file_id,))
        c.execute("DELETE FROM fixed_assets WHERE file_id = ?", (file_id,))
    else:
        c.execute("INSERT INTO files (filename, hash, parsed_at, period) VALUES (?,?,?,?)",
                  (fname, fhash, datetime.now().isoformat(), period))
        file_id = c.lastrowid

    # ===== CATALOGS =====

    # Contragents
    for cat in data.findall("v8:CatalogObject.Контрагенты", ns):
        ref = cat.find("v8:Ref", ns)
        desc = cat.find("v8:Description", ns)
        if ref is not None and desc is not None and ref.text and desc.text:
            c.execute("INSERT OR REPLACE INTO contragents (ref, name) VALUES (?,?)",
                      (ref.text.strip(), desc.text.strip()))

    # Виды расчёта (для подписей налогов/начислений в API зарплат)
    for cat in data.findall("v8:CatalogObject.ВидыРасчетов", ns):
        is_folder = cat.find("v8:IsFolder", ns)
        if is_folder is not None and is_folder.text == "true":
            continue
        ref = cat.find("v8:Ref", ns)
        desc = cat.find("v8:Description", ns)
        if ref is not None and ref.text:
            c.execute(
                "INSERT OR REPLACE INTO payroll_calc_types (ref, name) VALUES (?,?)",
                (ref.text.strip(), desc.text.strip() if desc is not None and desc.text else ""),
            )

    # Employees
    for cat in data.findall("v8:CatalogObject.Сотрудники", ns):
        is_folder = cat.find("v8:IsFolder", ns)
        if is_folder is not None and is_folder.text == "true":
            continue
        ref = cat.find("v8:Ref", ns)
        desc = cat.find("v8:Description", ns)
        hire = cat.find("v8:ДатаПринятия", ns)
        fire = cat.find("v8:ДатаУвольнения", ns)
        gender = cat.find("v8:Пол", ns)
        ctype = cat.find("v8:ВидДоговора", ns)
        wtype = cat.find("v8:МестоРаботы", ns)
        cend = cat.find("v8:ДатаОкончанияКонтракта", ns)

        if ref is None or desc is None:
            continue

        fire_date = ""
        if fire is not None and fire.text and fire.text[:4] != "0001":
            fire_date = fire.text[:10]

        c.execute("""INSERT OR REPLACE INTO employees
                     (ref, name, hired, fired, gender, contract_type, work_type, contract_end, active)
                     VALUES (?,?,?,?,?,?,?,?,?)""", (
            ref.text.strip(),
            desc.text.strip() if desc.text else "",
            hire.text[:10] if hire is not None and hire.text and hire.text[:4] != "0001" else "",
            fire_date,
            gender.text if gender is not None and gender.text else "",
            ctype.text if ctype is not None and ctype.text else "",
            wtype.text if wtype is not None and wtype.text else "",
            cend.text[:10] if cend is not None and cend.text and cend.text[:4] != "0001" else "",
            1 if not fire_date else 0,
        ))

    # Currencies
    currencies = {}
    for cat in data.findall("v8:CatalogObject.Валюты", ns):
        ref = cat.find("v8:Ref", ns)
        desc = cat.find("v8:Description", ns)
        if ref is not None and desc is not None:
            currencies[ref.text.strip()] = desc.text.strip() if desc.text else ""

    # Build employee lookup
    c.execute("SELECT ref, name FROM employees")
    emp_lookup = {r: n for r, n in c.fetchall()}

    # Build contragent lookup
    c.execute("SELECT ref, name FROM contragents")
    contr_lookup = {r: n for r, n in c.fetchall()}

    # ===== BANK OPERATIONS =====
    bank_rows = []
    for doc in data.findall("v8:DocumentObject.ВыпискаБанка", ns):
        date_el = doc.find("v8:Date", ns)
        cur_el = doc.find("v8:Валюта", ns)
        date_val = date_el.text[:10] if date_el is not None and date_el.text else ""
        cur_name = currencies.get(cur_el.text.strip() if cur_el is not None and cur_el.text else "", "BYN")

        for section, op_type in [("ПоступлениеСводное", "income"), ("СписаниеСводное", "expense")]:
            for item in doc.findall(f"v8:{section}", ns):
                summa = item.find("v8:Сумма", ns)
                content = item.find("v8:Содержание", ns)
                sub1 = item.find("v8:Субконто1", ns)
                vid = item.find("v8:ВидОплаты", ns)

                contr_ref = sub1.text.strip() if sub1 is not None and sub1.text else ""
                contr_name = contr_lookup.get(contr_ref, contr_ref[:30] if contr_ref else "")

                bank_rows.append((
                    file_id, date_val, op_type,
                    float(summa.text) if summa is not None and summa.text else 0,
                    contr_ref, contr_name,
                    content.text[:500] if content is not None and content.text else "",
                    vid.text if vid is not None and vid.text else "",
                    cur_name,
                ))

    c.executemany("""INSERT INTO bank_operations
                     (file_id, date, type, amount, contragent_ref, contragent_name, content, vid_oplaty, currency)
                     VALUES (?,?,?,?,?,?,?,?,?)""", bank_rows)

    # ===== SALARY ACCRUALS =====
    sal_rows = []
    for doc in data.findall("v8:DocumentObject.НачислениеЗаработнойПлаты", ns):
        for row in doc.findall("v8:Расчеты", ns):
            emp_ref = row.find("v8:Сотрудник", ns)
            vid = row.find("v8:ВидРасчета", ns)
            summa = row.find("v8:Сумма", ns)
            is_acc = row.find("v8:ФлагНачисление", ns)
            per = row.find("v8:ПериодРасчета", ns)

            if emp_ref is None or summa is None:
                continue

            emp_key = emp_ref.text.strip() if emp_ref.text else ""
            acc_flag = 0
            if is_acc is not None and is_acc.text is not None:
                t = is_acc.text.strip().lower()
                acc_flag = 1 if t in ("true", "1", "yes", "да") else 0
            sal_rows.append((
                file_id,
                per.text[:7] if per is not None and per.text else period,
                emp_key,
                emp_lookup.get(emp_key, ""),
                vid.text.strip() if vid is not None and vid.text else "",
                acc_flag,
                float(summa.text) if summa.text else 0,
            ))

    c.executemany("""INSERT INTO salary_accruals
                     (file_id, period, employee_ref, employee_name, calc_type, is_accrual, amount)
                     VALUES (?,?,?,?,?,?,?)""", sal_rows)

    # ===== SALARY PAYOUTS =====
    pay_rows = []
    for doc in data.findall("v8:DocumentObject.ВыплатаПоВедомости", ns):
        date_el = doc.find("v8:Date", ns)
        kind_el = doc.find("v8:ВидВыплаты", ns)
        date_val = date_el.text[:10] if date_el is not None else ""
        kind = kind_el.text if kind_el is not None and kind_el.text else ""

        for child in doc:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "Суммы":
                emp_ref = child.find("v8:Сотрудник", ns)
                s = child.find("v8:КВыдаче", ns)
                if emp_ref is not None and s is not None and s.text:
                    emp_key = emp_ref.text.strip() if emp_ref.text else ""
                    pay_rows.append((
                        file_id, date_val, emp_key,
                        emp_lookup.get(emp_key, ""),
                        kind,
                        float(s.text),
                    ))

    c.executemany("""INSERT INTO salary_payouts
                     (file_id, date, employee_ref, employee_name, payout_type, amount)
                     VALUES (?,?,?,?,?,?)""", pay_rows)

    # ===== CURRENCY RATES =====
    rate_rows = []
    for rs in data.findall("v8:InformationRegisterRecordSet.КурсыВалют", ns):
        for rec in rs.findall("v8:Record", ns):
            per = rec.find("v8:Period", ns)
            cur_ref = rec.find("v8:Валюта", ns)
            rate = rec.find("v8:Курс", ns)
            mult = rec.find("v8:Кратность", ns)
            if per is None or rate is None or cur_ref is None:
                continue
            rate_rows.append((
                file_id,
                per.text[:10],
                cur_ref.text.strip() if cur_ref.text else "",
                currencies.get(cur_ref.text.strip() if cur_ref.text else "", ""),
                float(rate.text) if rate.text else 0,
                float(mult.text) if mult is not None and mult.text else 1,
            ))

    c.executemany("""INSERT INTO currency_rates
                     (file_id, date, currency_ref, currency_name, rate, multiplier)
                     VALUES (?,?,?,?,?,?)""", rate_rows)

    # ===== FIXED ASSETS =====
    asset_rows = []
    for cat in data.findall("v8:CatalogObject.ОсновныеСредства", ns):
        is_folder = cat.find("v8:IsFolder", ns)
        if is_folder is not None and is_folder.text == "true":
            continue
        ref = cat.find("v8:Ref", ns)
        desc = cat.find("v8:Description", ns)
        inv = cat.find("v8:ИнвентарныйНомер", ns)
        dvvod = cat.find("v8:ДатаВводаВЭксплуатацию", ns)
        if ref is None:
            continue
        asset_rows.append((
            ref.text.strip(),
            file_id,
            desc.text.strip() if desc is not None and desc.text else "",
            inv.text.strip() if inv is not None and inv.text else "",
            dvvod.text[:10] if dvvod is not None and dvvod.text and dvvod.text[:4] != "0001" else "",
        ))

    c.executemany("INSERT OR REPLACE INTO fixed_assets (ref, file_id, name, inv_number, commissioned_date) VALUES (?,?,?,?,?)",
                  asset_rows)

    # ===== OPERATIONS =====
    op_rows = []
    for doc in data.findall("v8:DocumentObject.Операция", ns):
        date_el = doc.find("v8:Date", ns)
        content = doc.find("v8:Содержание", ns)
        summa = doc.find("v8:СуммаОперации", ns)
        op_rows.append((
            file_id,
            date_el.text[:10] if date_el is not None and date_el.text else "",
            float(summa.text) if summa is not None and summa.text else 0,
            content.text[:200] if content is not None and content.text else "",
        ))

    c.executemany("INSERT INTO operations (file_id, date, amount, content) VALUES (?,?,?,?)", op_rows)

    # ===== ADVANCE REPORTS =====
    adv_rows = []
    for doc in data.findall("v8:DocumentObject.АвансовыйОтчет", ns):
        date_el = doc.find("v8:Date", ns)
        summa = doc.find("v8:СуммаДокумента", ns)
        emp = doc.find("v8:Сотрудник", ns)
        emp_key = emp.text.strip() if emp is not None and emp.text else ""
        adv_rows.append((
            file_id,
            date_el.text[:10] if date_el is not None else "",
            emp_key,
            emp_lookup.get(emp_key, ""),
            float(summa.text) if summa is not None and summa.text else 0,
        ))

    c.executemany("INSERT INTO advance_reports (file_id, date, employee_ref, employee_name, amount) VALUES (?,?,?,?,?)",
                  adv_rows)

    conn.commit()

    # Print summary
    print(f"     Период: {period}")
    print(f"     Банковских операций: {len(bank_rows)}")
    print(f"     Начислений ЗП: {len(sal_rows)}")
    print(f"     Выплат по ведомости: {len(pay_rows)}")
    print(f"     Курсов валют: {len(rate_rows)}")
    print(f"     ОС: {len(asset_rows)}")
    print(f"     Операций: {len(op_rows)}")
    print(f"     Авансовых отчётов: {len(adv_rows)}")

    return file_id


def build_pnl_summary(conn, file_id):
    """Build P&L summary for a file from parsed data."""
    c = conn.cursor()

    c.execute("SELECT period FROM files WHERE id = ?", (file_id,))
    period = c.fetchone()[0]

    # Income
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM bank_operations WHERE file_id=? AND type='income'", (file_id,))
    total_income = c.fetchone()[0]

    # Salary payouts
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM salary_payouts WHERE file_id=?", (file_id,))
    salary_payout = c.fetchone()[0]

    # Tax payments (from bank)
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM bank_operations WHERE file_id=? AND type='expense' AND content LIKE '%ПОДОХОДНЫЙ%'", (file_id,))
    tax_income = c.fetchone()[0]

    # FSZN
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM bank_operations WHERE file_id=? AND type='expense' AND content LIKE '%СТРАХОВЫЕ ВЗНОСЫ%'", (file_id,))
    fszn = c.fetchone()[0]

    # BGS (from accruals)
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM salary_accruals WHERE file_id=? AND calc_type='dfcb7b0a-f2b1-4446-96db-cfc6b51b4de0'", (file_id,))
    bgs = c.fetchone()[0]

    # Office expenses (bank fees, rent, etc.)
    c.execute("""SELECT COALESCE(SUM(amount), 0) FROM bank_operations
                 WHERE file_id=? AND type='expense'
                 AND (content LIKE '%КОМИССИЯ%' OR content LIKE '%Плата за услуги%'
                      OR content LIKE '%абонентская%' OR content LIKE '%Вознагражд%'
                      OR content LIKE '%АРЕНД%' OR content LIKE '%ОФФШОРН%')""", (file_id,))
    office = c.fetchone()[0]

    # Total expense
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM bank_operations WHERE file_id=? AND type='expense'", (file_id,))
    total_expense = c.fetchone()[0]

    c.execute("""INSERT INTO pnl_summary
                 (file_id, period, total_income, total_expense, salary_payout, tax_income, fszn, bgs, office)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
              (file_id, period, total_income, total_expense, salary_payout, tax_income, fszn, bgs, office))

    conn.commit()


def main():
    if len(sys.argv) < 2:
        print("Использование: python parse_1c.py <путь_к_файлу_или_папке>")
        print("Пример: python parse_1c.py ./data/")
        sys.exit(1)

    path = sys.argv[1]
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)

    print(f"🗄  База данных: {db_path}")
    conn = init_db(db_path)

    files = []
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "*.xml")))
        print(f"📁 Найдено XML файлов: {len(files)}")
    elif os.path.isfile(path):
        files = [path]
    else:
        print(f"❌ Путь не найден: {path}")
        sys.exit(1)

    for filepath in files:
        file_id = parse_file(filepath, conn)
        if file_id:
            build_pnl_summary(conn, file_id)

    # Print overall stats
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM files")
    print(f"\n✅ Готово! Файлов в базе: {c.fetchone()[0]}")
    c.execute("SELECT period, filename FROM files ORDER BY period")
    for period, fname in c.fetchall():
        print(f"   {period} — {fname}")

    conn.close()


if __name__ == "__main__":
    main()
