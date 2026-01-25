"""
Development Utilities - POUZE PRO DEV!

Endpointy pro administraci a debugging. 
V produkci tyto endpointy deaktivovat!
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.connection import get_db

router = APIRouter(prefix="/api/dev", tags=["Development"])


class SQLExecuteRequest(BaseModel):
    sql: str


@router.post("/execute-sql")
async def execute_sql(
    request: SQLExecuteRequest,
    db: Session = Depends(get_db)
):
    """
    Execute raw SQL (migrations, updates, etc.)
    
    ⚠️ WARNING: Only for development! Disable in production!
    """
    try:
        # Split by semicolons for multiple statements
        statements = [s.strip() for s in request.sql.split(';') if s.strip()]
        
        results = []
        for stmt in statements:
            if not stmt:
                continue
                
            result = db.execute(text(stmt))
            
            # Try to fetch results if SELECT
            try:
                rows = result.fetchall()
                results.append({
                    "statement": stmt[:100] + "..." if len(stmt) > 100 else stmt,
                    "rows": len(rows),
                    "data": [dict(row._mapping) for row in rows[:10]]  # Max 10 rows preview
                })
            except Exception:
                # Not a SELECT, just count affected rows
                results.append({
                    "statement": stmt[:100] + "..." if len(stmt) > 100 else stmt,
                    "affected_rows": result.rowcount
                })
        
        db.commit()
        
        return {
            "success": True,
            "executed_statements": len(statements),
            "results": results
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"SQL execution failed: {str(e)}")
