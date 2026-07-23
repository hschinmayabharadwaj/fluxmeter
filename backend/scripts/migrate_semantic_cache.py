#!/usr/bin/env python3
"""
Semantic Cache Schema Migration Script
Safe, testable, with rollback capability
"""

import psycopg2
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Migration SQL - Safe, tested
MIGRATION_SQL = [
    # Step 1: Add new columns to semantic_cache_metadata
    """
    ALTER TABLE IF EXISTS semantic_cache_metadata
    ADD COLUMN IF NOT EXISTS candidate_email VARCHAR(255);
    """,
    
    # Step 2: Add job_id
    """
    ALTER TABLE IF EXISTS semantic_cache_metadata
    ADD COLUMN IF NOT EXISTS job_id VARCHAR(255);
    """,
    
    # Step 3: Add model
    """
    ALTER TABLE IF EXISTS semantic_cache_metadata
    ADD COLUMN IF NOT EXISTS model VARCHAR(100);
    """,
    
    # Step 4: Add estimated_tokens
    """
    ALTER TABLE IF EXISTS semantic_cache_metadata
    ADD COLUMN IF NOT EXISTS estimated_tokens INTEGER DEFAULT 0;
    """,
    
    # Step 5: Add created_by
    """
    ALTER TABLE IF EXISTS semantic_cache_metadata
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(255);
    """,
    
    # Step 6: Add invalidation_reason
    """
    ALTER TABLE IF EXISTS semantic_cache_metadata
    ADD COLUMN IF NOT EXISTS invalidation_reason VARCHAR(255);
    """,
    
    # Step 7: Add invalidated_at
    """
    ALTER TABLE IF EXISTS semantic_cache_metadata
    ADD COLUMN IF NOT EXISTS invalidated_at TIMESTAMP;
    """,
    
    # Step 8: Add updated_at column if missing
    """
    ALTER TABLE IF EXISTS semantic_cache_metadata
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    """,
    
    # Step 9: Create cache_hit_log table
    """
    CREATE TABLE IF NOT EXISTS cache_hit_log (
        id BIGSERIAL PRIMARY KEY,
        cache_id UUID NOT NULL,
        tenant_id UUID NOT NULL,
        correlation_id VARCHAR(255),
        ledger_id BIGINT,
        hit_reason VARCHAR(100),
        similarity_score DECIMAL(5,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    
    # Step 10: Create indexes on cache_hit_log
    """
    CREATE INDEX IF NOT EXISTS idx_hit_log_cache 
    ON cache_hit_log(cache_id);
    """,
    
    # Step 11: Create index on ledger_id
    """
    CREATE INDEX IF NOT EXISTS idx_hit_log_ledger 
    ON cache_hit_log(ledger_id);
    """,
    
    # Step 12: Create index on correlation_id
    """
    CREATE INDEX IF NOT EXISTS idx_hit_log_correlation 
    ON cache_hit_log(correlation_id);
    """,
    
    # Step 13: Create index on created_at for time queries
    """
    CREATE INDEX IF NOT EXISTS idx_hit_log_created 
    ON cache_hit_log(created_at DESC);
    """,
    
    # Step 14: Add foreign key constraint for cache_id
    """
    ALTER TABLE IF EXISTS cache_hit_log
    ADD CONSTRAINT fk_cache_hit_log_cache_id 
    FOREIGN KEY (cache_id) 
    REFERENCES semantic_cache_metadata(cache_id) 
    ON DELETE CASCADE;
    """,
    
    # Step 15: Add foreign key constraint for tenant_id
    """
    ALTER TABLE IF EXISTS cache_hit_log
    ADD CONSTRAINT fk_cache_hit_log_tenant_id 
    FOREIGN KEY (tenant_id) 
    REFERENCES tenants(tenant_id) 
    ON DELETE CASCADE;
    """,
    
    # Step 16: Add foreign key constraint for ledger_id
    """
    ALTER TABLE IF EXISTS cache_hit_log
    ADD CONSTRAINT fk_cache_hit_log_ledger_id 
    FOREIGN KEY (ledger_id) 
    REFERENCES ledger(id) 
    ON DELETE SET NULL;
    """,
]

ROLLBACK_SQL = [
    # Rollback: Drop new table
    """
    DROP TABLE IF EXISTS cache_hit_log CASCADE;
    """,
    
    # Rollback: Drop new columns
    """
    ALTER TABLE IF EXISTS semantic_cache_metadata
    DROP COLUMN IF EXISTS candidate_email,
    DROP COLUMN IF EXISTS job_id,
    DROP COLUMN IF EXISTS model,
    DROP COLUMN IF EXISTS estimated_tokens,
    DROP COLUMN IF EXISTS created_by,
    DROP COLUMN IF EXISTS invalidation_reason,
    DROP COLUMN IF EXISTS invalidated_at,
    DROP COLUMN IF EXISTS updated_at;
    """,
]

def get_connection(host, port, user, password, database):
    """Get database connection"""
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        logger.info(f"Connected to database: {database}@{host}:{port}")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def backup_database(conn, filename):
    """Create database backup"""
    import subprocess
    try:
        with open(filename, 'w') as f:
            subprocess.run(
                ['pg_dump', '-U', 'ledgerline', 'ledgerline'],
                stdout=f,
                check=True
            )
        logger.info(f"Database backup created: {filename}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return False

def verify_schema(conn):
    """Verify schema integrity after migration"""
    cursor = conn.cursor()
    
    # Check if new columns exist
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'semantic_cache_metadata'
    """)
    
    columns = [row[0] for row in cursor.fetchall()]
    required_columns = [
        'candidate_email', 'job_id', 'model', 'estimated_tokens',
        'created_by', 'invalidation_reason', 'invalidated_at'
    ]
    
    for col in required_columns:
        if col not in columns:
            logger.error(f"Missing column: {col}")
            return False
    
    # Check if cache_hit_log table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'cache_hit_log'
        )
    """)
    
    if not cursor.fetchone()[0]:
        logger.error("cache_hit_log table does not exist")
        return False
    
    logger.info("Schema verification passed")
    return True

def run_migration(conn):
    """Execute migration SQL"""
    cursor = conn.cursor()
    
    try:
        for i, sql in enumerate(MIGRATION_SQL, 1):
            logger.info(f"Executing migration step {i}/{len(MIGRATION_SQL)}...")
            cursor.execute(sql)
            conn.commit()
        
        logger.info("All migration steps completed successfully")
        return True
    except Exception as e:
        logger.error(f"Migration failed at step {i}: {e}")
        conn.rollback()
        return False

def run_rollback(conn):
    """Execute rollback SQL"""
    cursor = conn.cursor()
    
    try:
        for i, sql in enumerate(ROLLBACK_SQL, 1):
            logger.info(f"Executing rollback step {i}/{len(ROLLBACK_SQL)}...")
            cursor.execute(sql)
            conn.commit()
        
        logger.info("All rollback steps completed successfully")
        return True
    except Exception as e:
        logger.error(f"Rollback failed at step {i}: {e}")
        conn.rollback()
        return False

def main():
    import os
    
    # Get database credentials from environment
    host = os.getenv('DB_HOST', 'localhost')
    port = int(os.getenv('DB_PORT', 5432))
    user = os.getenv('DB_USER', 'ledgerline')
    password = os.getenv('DB_PASSWORD', 'ledgerline')
    database = os.getenv('DB_NAME', 'ledgerline')
    
    # Get action from command line
    action = sys.argv[1] if len(sys.argv) > 1 else 'migrate'
    
    # Get connection
    conn = get_connection(host, port, user, password, database)
    
    try:
        if action == 'migrate':
            # Create backup
            backup_file = f"backup_ledgerline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            if not backup_database(conn, backup_file):
                logger.error("Backup failed - aborting migration")
                sys.exit(1)
            
            # Run migration
            if not run_migration(conn):
                logger.error("Migration failed - attempting rollback")
                run_rollback(conn)
                sys.exit(1)
            
            # Verify schema
            if not verify_schema(conn):
                logger.error("Schema verification failed - attempting rollback")
                run_rollback(conn)
                sys.exit(1)
            
            logger.info("✅ Migration completed successfully")
            sys.exit(0)
        
        elif action == 'rollback':
            logger.warning("⚠️  Starting schema rollback...")
            if run_rollback(conn):
                logger.info("✅ Rollback completed successfully")
                sys.exit(0)
            else:
                logger.error("❌ Rollback failed")
                sys.exit(1)
        
        elif action == 'verify':
            if verify_schema(conn):
                logger.info("✅ Schema verification passed")
                sys.exit(0)
            else:
                logger.error("❌ Schema verification failed")
                sys.exit(1)
        
        else:
            logger.error(f"Unknown action: {action}")
            logger.info("Usage: python3 migrate.py [migrate|rollback|verify]")
            sys.exit(1)
    
    finally:
        conn.close()

if __name__ == '__main__':
    main()
