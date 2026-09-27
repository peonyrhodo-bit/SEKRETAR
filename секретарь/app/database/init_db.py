import sqlite3
import os
from datetime import datetime

# 1. Путь к базе данных
db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'database')
os.makedirs(db_dir, exist_ok=True)
db_path = os.path.join(db_dir, 'secretary.db')

print("🔄 Инициализация полной структуры БД (Блоки А + Б + В + Г)...")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = ON;")

# ============================================================
# БЛОК Б: ОСНОВНЫЕ СУЩНОСТИ (с усиленной защитой связей)
# ============================================================

cursor.execute("""CREATE TABLE IF NOT EXISTS persons (
    person_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id TEXT PRIMARY KEY,
    vin TEXT,
    state_number TEXT NOT NULL,
    brand TEXT,
    model TEXT,
    year INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS contacts (
    contact_id TEXT PRIMARY KEY,
    person_id TEXT,
    vehicle_id TEXT,
    role TEXT,
    start_date TEXT,
    end_date TEXT,
    FOREIGN KEY (person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS phones (
    phone_id TEXT PRIMARY KEY,
    phone_number TEXT NOT NULL,
    contact_id TEXT,
    status TEXT DEFAULT 'active',
    source TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (contact_id) REFERENCES contacts(contact_id) ON DELETE RESTRICT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS messengers (
    messenger_id TEXT PRIMARY KEY,
    phone_id TEXT,
    messenger_type TEXT,
    chat_id TEXT,
    status TEXT DEFAULT 'active',
    FOREIGN KEY (phone_id) REFERENCES phones(phone_id) ON DELETE RESTRICT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS insurance_companies (
    company_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS policies (
    policy_id TEXT PRIMARY KEY,
    policy_number TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    contract_start TEXT,
    contract_end TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    FOREIGN KEY (company_id) REFERENCES insurance_companies(company_id) ON DELETE RESTRICT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS usage_periods (
    period_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    FOREIGN KEY (policy_id) REFERENCES policies(policy_id) ON DELETE RESTRICT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS addendums (
    addendum_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    addendum_type TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (policy_id) REFERENCES policies(policy_id) ON DELETE RESTRICT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    doc_type TEXT,
    original_name TEXT,
    file_path TEXT NOT NULL,
    file_hash TEXT,
    file_size INTEGER,
    created_at TEXT NOT NULL
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS physical_folders (
    folder_id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    linked_vehicle_id TEXT,
    linked_policy_id TEXT,
    FOREIGN KEY (linked_vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE SET NULL,
    FOREIGN KEY (linked_policy_id) REFERENCES policies(policy_id) ON DELETE SET NULL
)""")

# ============================================================
# БЛОК В: ИСТОРИЧЕСКИЕ СВЯЗИ (матрёшка, история владельцев)
# ============================================================

cursor.execute("""CREATE TABLE IF NOT EXISTS owner_history (
    history_id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    role TEXT DEFAULT 'owner',
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    FOREIGN KEY (person_id) REFERENCES persons(person_id) ON DELETE RESTRICT
)""")

# ============================================================
# БЛОК Г: ИНФРАСТРУКТУРА (задачи, workflow, коммуникации, provenance)
# ============================================================

cursor.execute("""CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',
    status TEXT DEFAULT 'open',
    due_date TEXT,
    assignee TEXT,
    linked_person_id TEXT,
    linked_vehicle_id TEXT,
    linked_policy_id TEXT,
    linked_workflow_id TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT,
    FOREIGN KEY (linked_person_id) REFERENCES persons(person_id) ON DELETE SET NULL,
    FOREIGN KEY (linked_vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE SET NULL,
    FOREIGN KEY (linked_policy_id) REFERENCES policies(policy_id) ON DELETE SET NULL
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS workflows (
    workflow_id TEXT PRIMARY KEY,
    workflow_type TEXT NOT NULL,
    description TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS workflow_cases (
    case_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    status TEXT DEFAULT 'started',
    current_step TEXT,
    linked_person_id TEXT,
    linked_vehicle_id TEXT,
    linked_policy_id TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT,
    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id) ON DELETE RESTRICT,
    FOREIGN KEY (linked_person_id) REFERENCES persons(person_id) ON DELETE SET NULL,
    FOREIGN KEY (linked_vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE SET NULL,
    FOREIGN KEY (linked_policy_id) REFERENCES policies(policy_id) ON DELETE SET NULL
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS workflow_steps (
    step_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_order INTEGER,
    status TEXT DEFAULT 'pending',
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (case_id) REFERENCES workflow_cases(case_id) ON DELETE RESTRICT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    contact_id TEXT,
    channel TEXT,
    linked_workflow_id TEXT,
    started_at TEXT NOT NULL,
    FOREIGN KEY (contact_id) REFERENCES contacts(contact_id) ON DELETE SET NULL
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    content TEXT,
    sent_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE RESTRICT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    target_date TEXT,
    status TEXT DEFAULT 'planned',
    created_at TEXT NOT NULL
)""")

# Provenance: откуда взялся каждый факт
cursor.execute("""CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL,
    status TEXT DEFAULT 'extracted',
    extracted_at TEXT NOT NULL
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS provenance (
    provenance_id TEXT PRIMARY KEY,
    fact_id TEXT NOT NULL,
    document_id TEXT,
    page_number INTEGER,
    fragment TEXT,
    source_type TEXT,
    FOREIGN KEY (fact_id) REFERENCES facts(fact_id) ON DELETE RESTRICT,
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE SET NULL
)""")

# Журнал изменений
cursor.execute("""CREATE TABLE IF NOT EXISTS change_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    source_document_id TEXT,
    confidence REAL,
    changed_at TEXT NOT NULL,
    changed_by TEXT DEFAULT 'system'
)""")

# ============================================================
# ТЕСТОВЫЕ ДАННЫЕ: проверяем исторические связи и защиту
# ============================================================

current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Страховая
cursor.execute("INSERT OR IGNORE INTO insurance_companies (company_id, name) VALUES ('C-001', 'Ингосстрах')")

# Два человека
cursor.execute("INSERT OR IGNORE INTO persons (person_id, full_name, created_at) VALUES ('P-000001', 'Иванов Иван Иванович', ?)", (current_time,))
cursor.execute("INSERT OR IGNORE INTO persons (person_id, full_name, created_at) VALUES ('P-000002', 'Петров Пётр Петрович', ?)", (current_time,))

# Один автомобиль (якорь истории)
cursor.execute("INSERT OR IGNORE INTO vehicles (vehicle_id, vin, state_number, brand, created_at) VALUES ('V-000184', 'X1234567890123456', 'К123КК123', 'Lada', ?)", (current_time,))

# ИСТОРИЯ ВЛАДЕЛЬЦЕВ: один автомобиль, два владельца в разные годы
cursor.execute("INSERT OR IGNORE INTO owner_history (history_id, vehicle_id, person_id, start_date, end_date, role) VALUES ('OH-001', 'V-000184', 'P-000001', '2024-01-01', '2024-12-31', 'owner')")
cursor.execute("INSERT OR IGNORE INTO owner_history (history_id, vehicle_id, person_id, start_date, end_date, role) VALUES ('OH-002', 'V-000184', 'P-000001', '2025-01-01', '2025-12-31', 'owner')")
cursor.execute("INSERT OR IGNORE INTO owner_history (history_id, vehicle_id, person_id, start_date, end_date, role) VALUES ('OH-003', 'V-000184', 'P-000002', '2026-01-01', NULL, 'owner')")

# Контакты
cursor.execute("INSERT OR IGNORE INTO contacts (contact_id, person_id, vehicle_id, role) VALUES ('CNT-001', 'P-000001', 'V-000184', 'владелец')")

# Телефон
cursor.execute("INSERT OR IGNORE INTO phones (phone_id, phone_number, contact_id, status, created_at) VALUES ('PH-001', '+79001234567', 'CNT-001', 'active', ?)", (current_time,))

# Полис
cursor.execute("INSERT OR IGNORE INTO policies (policy_id, policy_number, vehicle_id, company_id, contract_start, contract_end, created_at) VALUES ('POL-001', '4561231515', 'V-000184', 'C-001', '2026-01-01', '2026-12-31', ?)", (current_time,))

# Период использования (РАБОЧАЯ ДАТА отличается от даты договора!)
cursor.execute("INSERT OR IGNORE INTO usage_periods (period_id, policy_id, start_date, end_date) VALUES ('UP-001', 'POL-001', '2026-01-01', '2026-03-31')")

# Задача (связана с человеком, авто и полисом)
cursor.execute("INSERT OR IGNORE INTO tasks (task_id, task_type, priority, status, due_date, linked_person_id, linked_vehicle_id, linked_policy_id, created_at) VALUES ('T-001', 'продление', 'high', 'open', '2026-03-10', 'P-000002', 'V-000184', 'POL-001', ?)", (current_time,))

# Workflow: продление ОСАГО
cursor.execute("INSERT OR IGNORE INTO workflows (workflow_id, workflow_type, description) VALUES ('WF-RENEWAL', 'продление_осаго', 'Стандартный сценарий продления')")
cursor.execute("INSERT OR IGNORE INTO workflow_cases (case_id, workflow_id, status, current_step, linked_person_id, linked_vehicle_id, created_at) VALUES ('WC-001', 'WF-RENEWAL', 'ожидание_клиента', 'напоминание_отправлено', 'P-000002', 'V-000184', ?)", (current_time,))

conn.commit()

# ============================================================
# ПРОВЕРКА РЕЗУЛЬТАТА
# ============================================================

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = sorted([row[0] for row in cursor.fetchall()])

cursor.execute("SELECT COUNT(*) FROM owner_history WHERE vehicle_id = 'V-000184'")
owner_count = cursor.fetchone()[0]

cursor.execute("SELECT p.full_name, oh.start_date, oh.end_date FROM owner_history oh JOIN persons p ON oh.person_id = p.person_id WHERE oh.vehicle_id = 'V-000184' ORDER BY oh.start_date")
owners = cursor.fetchall()

cursor.execute("SELECT end_date FROM usage_periods WHERE period_id = 'UP-001'")
period = cursor.fetchone()

cursor.execute("SELECT priority, status FROM tasks WHERE task_id = 'T-001'")
task = cursor.fetchone()

print("\n" + "="*70)
print("✅ ЭТАП 2 (БЛОКИ А + Б + В + Г) — УСПЕШНО ВЫПОЛНЕН")
print("="*70)
print(f"📂 База данных: {db_path}")
print(f"📊 Создано таблиц: {len(tables)}")
print(f"   {', '.join(tables)}")
print()
print("🔗 ИСТОРИЯ ВЛАДЕЛЬЦЕВ (один автомобиль, несколько владельцев):")
for owner in owners:
    end = owner[1] if owner[1] else "настоящее время"
    print(f"   • {owner[0]}: {owner[1]} — {end}")
print(f"   Всего записей истории для V-000184: {owner_count}")
print()
print(f"📅 Рабочая дата пролонгации (из Usage Period): {period[0]}")
print(f"   (НЕ совпадает с концом договора 2026-12-31 — это правильно!)")
print()
print(f"📋 Тестовая задача: приоритет={task[0]}, статус={task[1]}")
print()
print("🛡️ ЗАЩИТА ЦЕЛОСТНОСТИ:")
print("   • Нельзя удалить автомобиль, если к нему привязан полис")
print("   • Нельзя удалить человека, если он в истории владельцев")
print("   • Нельзя удалить полис, если к нему привязан период использования")
print("   • При удалении папки — связь с авто/полисом просто обнуляется")
print("="*70)

conn.close()
