import sqlite3
import os
import shutil
from datetime import datetime

# Путь к базе данных
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'database', 'secretary.db')

# Путь к папке резервных копий (на уровне корня проекта, не внутри app)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backup_dir = os.path.join(project_root, 'data', 'backups')
os.makedirs(backup_dir, exist_ok=True)

# Создаём имя файла с датой и временем
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_filename = f"secretary_backup_{timestamp}.db"
backup_path = os.path.join(backup_dir, backup_filename)

print("🔄 Создание резервной копии базы данных...")

# Проверяем, что исходная база существует
if not os.path.exists(db_path):
    print(f"❌ ОШИБКА: База данных не найдена по пути: {db_path}")
    exit(1)

# Копируем файл базы данных
try:
    shutil.copy2(db_path, backup_path)
    print(f"✅ Резервная копия создана: {backup_path}")
    
    # Проверяем размер
    original_size = os.path.getsize(db_path)
    backup_size = os.path.getsize(backup_path)
    
    print(f"📊 Размер оригинала: {original_size} байт")
    print(f"📊 Размер копии: {backup_size} байт")
    
    if original_size == backup_size:
        print("✅ Размеры совпадают — копия создана успешно")
    else:
        print("⚠️ ВНИМАНИЕ: Размеры не совпадают!")
        
except Exception as e:
    print(f"❌ ОШИБКА при создании копии: {e}")
    exit(1)

print("\n" + "="*70)
print("✅ РЕЗЕРВНОЕ КОПИРОВАНИЕ ЗАВЕРШЕНО")
print("="*70)
print(f"Копия сохранена в: {backup_dir}")
print(f"Имя файла: {backup_filename}")
print("\n💡 Если что-то сломается, вы можете восстановить базу из этой копии.")
print("="*70)
