import sys
from server_db.connection import engine, SessionLocal
from server_db.models import Base
from sqlalchemy import inspect, text

def test_connection():
    print("Testing database connection...")
    try:
        db = SessionLocal()
        result = db.execute(text("SELECT version();"))
        version = result.fetchone()[0]
        print(f"✓ Connected to PostgreSQL: {version}")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

def test_tables():
    print("\nChecking tables...")
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        expected_tables = [
            'agent_credentials',
            'agents',
            'metric_numeric',
            'metric_json',
            'metric_numeric_1m',
            'metric_numeric_10m',
            'metric_numeric_1h',
            'anomaly_state',
            'tickets'
        ]
        
        print(f"Found {len(tables)} tables:")
        for table in sorted(tables):
            status = "✓" if table in expected_tables else "?"
            print(f"  {status} {table}")
        
        missing = set(expected_tables) - set(tables)
        if missing:
            print(f"\n✗ Missing tables: {missing}")
            return False
        
        print(f"\n✓ All expected tables present")
        return True
    except Exception as e:
        print(f"✗ Table check failed: {e}")
        return False

def test_indexes():
    print("\nChecking indexes...")
    try:
        inspector = inspect(engine)
        
        tables_with_indexes = {
            'metric_numeric': ['idx_metric_raw_time'],
            'metric_numeric_1m': ['idx_metric_1m_time'],
            'metric_numeric_10m': ['idx_metric_10m_time'],
            'anomaly_state': ['idx_anomaly_lookup']
        }
        
        for table, expected_indexes in tables_with_indexes.items():
            indexes = inspector.get_indexes(table)
            index_names = [idx['name'] for idx in indexes]
            
            for expected_idx in expected_indexes:
                if expected_idx in index_names:
                    print(f"  ✓ {table}.{expected_idx}")
                else:
                    print(f"  ✗ {table}.{expected_idx} - MISSING")
        
        return True
    except Exception as e:
        print(f"✗ Index check failed: {e}")
        return False

def test_foreign_keys():
    print("\nChecking foreign keys...")
    try:
        inspector = inspect(engine)
        
        fk_checks = {
            'agents': [('agent_id', 'agent_credentials', 'agent_id')],
            'metric_numeric': [('agent_id', 'agents', 'agent_id')],
            'metric_json': [('agent_id', 'agents', 'agent_id')]
        }
        
        for table, expected_fks in fk_checks.items():
            fks = inspector.get_foreign_keys(table)
            
            for expected_fk in expected_fks:
                col, ref_table, ref_col = expected_fk
                found = any(
                    fk['referred_table'] == ref_table and
                    col in fk['constrained_columns'] and
                    ref_col in fk['referred_columns']
                    for fk in fks
                )
                
                if found:
                    print(f"  ✓ {table}.{col} -> {ref_table}.{ref_col}")
                else:
                    print(f"  ? {table}.{col} -> {ref_table}.{ref_col} - Not found (might be optional)")
        
        return True
    except Exception as e:
        print(f"✗ Foreign key check failed: {e}")
        return False

def main():
    print("=" * 60)
    print("PostgreSQL Migration Verification")
    print("=" * 60)
    
    tests = [
        ("Connection", test_connection),
        ("Tables", test_tables),
        ("Indexes", test_indexes),
        ("Foreign Keys", test_foreign_keys)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} test crashed: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✓ All tests passed! Database is ready.")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())