from database.db_utils import DatabaseManager
from database.models import ProcessingRecord, Paper
import datetime
import json

def fix_pending_records():
    print("Fixing stale processing records...")
    db = DatabaseManager()
    
    with db.get_session() as session:
        # Find the paper by title
        paper = session.query(Paper).filter(Paper.title.like('%Analytical theory of the skewed wake effect%')).first()
        
        if not paper:
            print("Paper not found")
            return
            
        print(f"Found paper: ID={paper.id}, Title={paper.title}")
        
        # 1. Fix all pending records for this paper
        pending_records = session.query(ProcessingRecord).filter_by(
            paper_id=paper.id, 
            status="pending"
        ).all()
        
        print(f"Found {len(pending_records)} pending processing records for this paper")
        
        current_time = datetime.datetime.utcnow()
        
        for record in pending_records:
            print(f"Updating record ID={record.id}, Status={record.status}, Type={record.process_type}")
            
            # Check if stuck at LLM API call
            try:
                message_data = json.loads(record.message) if record.message and record.message.startswith('{') else {}
                current_step = message_data.get("current_step", "")
                if current_step == "llm_api_call":
                    print(f"Record ID={record.id} is stuck at LLM API call stage")
            except:
                print(f"Could not parse message JSON for record ID={record.id}")
            
            record.status = "failed"
            record.message = "Process interrupted due to API timeout"
            record.updated_at = current_time
        
        # 2. Fix all failed records with timestamp issues
        failed_records = session.query(ProcessingRecord).filter_by(
            paper_id=paper.id, 
            status="failed"
        ).all()
        
        print(f"Found {len(failed_records)} failed processing records for this paper")
        
        for record in failed_records:
            if record.updated_at is None:
                print(f"Fixing missing timestamp for record ID={record.id}")
                record.updated_at = current_time
            # Fix future timestamps
            elif record.updated_at.year > 2024 or record.created_at.year > 2024:
                print(f"Fixing future timestamp for record ID={record.id}")
                if record.updated_at.year > 2024:
                    record.updated_at = current_time
                if record.created_at.year > 2024:
                    record.created_at = current_time
        
        # 3. Mark the paper as not processed so we can try again
        paper.processed = False
        print(f"Reset processed flag for paper ID={paper.id}")
        
        # 4. Clear any other issues with the paper
        if paper.updated_at and paper.updated_at.year > 2024:
            paper.updated_at = current_time
            print(f"Fixed future timestamp for paper ID={paper.id}")
        
        # Commit all changes
        session.commit()
        print("All records have been fixed")

if __name__ == "__main__":
    fix_pending_records() 