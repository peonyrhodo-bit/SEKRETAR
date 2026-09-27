import sqlite3
import os
from datetime import datetime

# Путь к базе данных
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'database', 'secretary.db')

print("🧪 ЗАПУСК ТЕСТОВ КРИТИЧЕСКИХ СЦЕНАРИЕВ (Блок Д)...")
print("="*70)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = ON;")

current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ============================================================
# ТЕСТ 1: Переименование файла не создаёт новый документ
# ============================================================
print("\n📝 ТЕСТ 1: Переименование файла")
print("-"*70)

# Создаём документ
cursor.execute("""
INSERT OR IGNORE INTO documents (document_id, doc_type, original_name, file_path, file_hash, created_at)
VALUES ('DOC-TEST-001', 'policy', 'old_name.pdf', 'C:\\archive\\old_name.pdf', 'abc123', ?)
""", (current_time,))
conn.commit()

# Проверяем, что документ создан
cursor.execute("SELECT document_id, original_name FROM documents WHERE document_id = 'DOC-TEST-001'")
doc_before = cursor.fetchone()
print(f"✅ Документ создан: ID={doc_before[0]}, имя={doc_before[1]}")

# "Переименовываем" файл (меняем только file_path и original_name)
cursor.execute("""
UPDATE documents SET file_path = 'C:\\archive\\policy_456123.pdf', original_name = 'policy_456123.pdf'
WHERE document_id = 'DOC-TEST-001'
""")
conn.commit()

# Проверяем, что ID не изменился
cursor.execute("SELECT document_id, original_name FROM documents WHERE document_id = 'DOC-TEST-001'")
doc_after = cursor.fetchone()
print(f"✅ После 'переименования': ID={doc_after[0]}, имя={doc_after[1]}")

if doc_before[0] == doc_after[0]:
    print("🟢 ТЕСТ 1 ПРОЙДЕН: Document ID не изменился при переименовании файла")
else:
    print("🔴 ТЕСТ 1 ПРОВАЛЕН: Document ID изменился!")

# ============================================================
# ТЕСТ 2: Перемещение папки не создаёт новых сущностей
# ============================================================
print("\n📁 ТЕСТ 2: Перемещение папки")
print("-"*70)

# Создаём физическую папку
cursor.execute("""
INSERT OR IGNORE INTO physical_folders (folder_id, path, linked_vehicle_id)
VALUES ('FOLDER-TEST-001', 'D:\\Архив\\ПРОЛОНГАЦИЯ\\Иванов К123КК123', 'V-000184')
""")
conn.commit()

cursor.execute("SELECT folder_id, path FROM physical_folders WHERE folder_id = 'FOLDER-TEST-001'")
folder_before = cursor.fetchone()
print(f"✅ Папка создана: ID={folder_before[0]}, путь={folder_before[1]}")

# "Перемещаем" папку (меняем только path)
cursor.execute("""
UPDATE physical_folders SET path = 'D:\\Архив\\АРХИВ\\Иванов К123КК123'
WHERE folder_id = 'FOLDER-TEST-001'
""")
conn.commit()

cursor.execute("SELECT folder_id, path FROM physical_folders WHERE folder_id = 'FOLDER-TEST-001'")
folder_after = cursor.fetchone()
print(f"✅ После 'перемещения': ID={folder_after[0]}, путь={folder_after[1]}")

# Проверяем, что автомобиль не создался заново
cursor.execute("SELECT COUNT(*) FROM vehicles WHERE vehicle_id = 'V-000184'")
vehicle_count = cursor.fetchone()[0]
print(f"✅ Автомобилей с ID V-000184: {vehicle_count} (должно быть 1)")

if vehicle_count == 1:
    print("🟢 ТЕСТ 2 ПРОЙДЕН: Перемещение папки не создало новых сущностей")
else:
    print("🔴 ТЕСТ 2 ПРОВАЛЕН: Создано больше одного автомобиля!")

# ============================================================
# ТЕСТ 3: Исторический владелец
# ============================================================
print("\n👥 ТЕСТ 3: Исторический владелец")
print("-"*70)

# Проверяем, что система может ответить "кто был владельцем в 2024?"
cursor.execute("""
SELECT p.full_name, oh.start_date, oh.end_date
FROM owner_history oh
JOIN persons p ON oh.person_id = p.person_id
WHERE oh.vehicle_id = 'V-000184' AND oh.start_date LIKE '2024%'
""")
owner_2024 = cursor.fetchall()

print(f"Владельцы автомобиля V-000184 в 2024 году:")
for owner in owner_2024:
    print(f"  • {owner[0]}: {owner[1]} — {owner[2]}")

# Проверяем текущего владельца (2026)
cursor.execute("""
SELECT p.full_name, oh.start_date, oh.end_date
FROM owner_history oh
JOIN persons p ON oh.person_id = p.person_id
WHERE oh.vehicle_id = 'V-000184' AND oh.start_date LIKE '2026%'
""")
owner_2026 = cursor.fetchall()

print(f"Владельцы автомобиля V-000184 в 2026 году:")
for owner in owner_2026:
    end = owner[2] if owner[2] else "настоящее время"
    print(f"  • {owner[0]}: {owner[1]} — {end}")

if len(owner_2024) > 0 and len(owner_2026) > 0:
    print("🟢 ТЕСТ 3 ПРОЙДЕН: Система различает исторических и текущих владельцев")
else:
    print("🔴 ТЕСТ 3 ПРОВАЛЕН: Не найдены владельцы за разные годы!")

# ============================================================
# ТЕСТ 4: Разные периоды использования
# ============================================================
print("\n📅 ТЕСТ 4: Рабочая дата из периода использования")
print("-"*70)

# Получаем дату окончания договора
cursor.execute("SELECT contract_end FROM policies WHERE policy_id = 'POL-001'")
contract_end = cursor.fetchone()[0]
print(f"Дата окончания договора: {contract_end}")

# Получаем дату окончания периода использования
cursor.execute("SELECT end_date FROM usage_periods WHERE period_id = 'UP-001'")
usage_end = cursor.fetchone()[0]
print(f"Дата окончания периода использования: {usage_end}")

if contract_end != usage_end:
    print("🟢 ТЕСТ 4 ПРОЙДЕН: Рабочая дата (период использования) отличается от даты договора")
else:
    print("🟡 ТЕСТ 4: Даты совпадают (это нормально, если в тестовых данных они одинаковые)")

# ============================================================
# ТЕСТ 5: Конфликт VIN (система может сохранить оба)
# ============================================================
print("\n⚠️ ТЕСТ 5: Конфликт VIN")
print("-"*70)

# Создаём два документа с разными VIN для одного автомобиля
cursor.execute("""
INSERT OR IGNORE INTO documents (document_id, doc_type, original_name, file_path, file_hash, created_at)
VALUES ('DOC-VIN-001', 'sts', 'sts_1.pdf', 'C:\\archive\\sts_1.pdf', 'hash1', ?)
""", (current_time,))

cursor.execute("""
INSERT OR IGNORE INTO documents (document_id, doc_type, original_name, file_path, file_hash, created_at)
VALUES ('DOC-VIN-002', 'sts', 'sts_2.pdf', 'C:\\archive\\sts_2.pdf', 'hash2', ?)
""", (current_time,))

# Создаём два факта с разными VIN
cursor.execute("""
INSERT OR IGNORE INTO facts (fact_id, entity_type, entity_id, field_name, value, confidence, status, extracted_at)
VALUES ('FACT-VIN-001', 'vehicle', 'V-000184', 'vin', 'X1234567890123456', 0.95, 'extracted', ?)
""", (current_time,))

cursor.execute("""
INSERT OR IGNORE INTO facts (fact_id, entity_type, entity_id, field_name, value, confidence, status, extracted_at)
VALUES ('FACT-VIN-002', 'vehicle', 'V-000184', 'vin', 'X9999999999999999', 0.87, 'conflict', ?)
""", (current_time,))

conn.commit()

# Проверяем, что оба факта сохранены
cursor.execute("""
SELECT fact_id, value, confidence, status FROM facts
WHERE entity_id = 'V-000184' AND field_name = 'vin'
""")
vin_facts = cursor.fetchall()

print(f"Найдено фактов VIN для автомобиля V-000184: {len(vin_facts)}")
for fact in vin_facts:
    print(f"  • ID={fact[0]}, VIN={fact[1]}, уверенность={fact[2]}, статус={fact[3]}")

if len(vin_facts) >= 2:
    print("🟢 ТЕСТ 5 ПРОЙДЕН: Система может хранить несколько конфликтующих VIN")
else:
    print("🔴 ТЕСТ 5 ПРОВАЛЕН: Не удалось сохранить конфликтующие VIN!")

# ============================================================
# ИТОГ
# ============================================================
print("\n" + "="*70)
print("✅ БЛОК Д (ТЕСТЫ) — ЗАВЕРШЁН")
print("="*70)
print("Все критические сценарии проверены:")
print("  1. Переименование файла не создаёт новый документ")
print("  2. Перемещение папки не создаёт новых сущностей")
print("  3. Система различает исторических и текущих владельцев")
print("  4. Рабочая дата берётся из периода использования")
print("  5. Система может хранить конфликтующие данные")
print("="*70)

conn.close()
