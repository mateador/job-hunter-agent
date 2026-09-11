"""
Day 11: Agent runner with checkpointing.
"""
import logging
from typing import List, Dict, Any, Optional

from .llm_client import LLMClient
from .audit_logger import AuditLogger
from .checkpoint import CheckpointManager
from .tools import search_freehire, search_duckduckgo
from .models import Job, AgentState
from .prompts import SYSTEM_PROMPT
from .application_generator import generate_application

logger = logging.getLogger(__name__)

class AgentRunner:
    def __init__(
        self,
        audit_logger: AuditLogger,
        checkpoint_manager: CheckpointManager,
        model: str = "gpt-4o-mini",
        max_jobs: int = 10
    ):
        self.audit_logger = audit_logger
        self.checkpoint_manager = checkpoint_manager
        self.llm_client = LLMClient(audit_logger=audit_logger, model=model)
        self.max_jobs = max_jobs
        
    def run(self, query: str, resume: bool = False) -> Dict[str, Any]:
        """
        Run the agent loop.
        
        Args:
            query: Job search query
            resume: If True, attempt to resume from last checkpoint
            
        Returns:
            Dictionary containing jobs, applications, and metadata
        """
        # Initialize or resume state
        if resume:
            state = self.checkpoint_manager.load_latest_checkpoint()
            if state:
                logger.info(f"Resuming from checkpoint {self.checkpoint_manager.checkpoint_counter}")
                jobs_found = state.get("jobs_found", [])
                jobs_processed = set(state.get("jobs_processed", []))
                applications = state.get("applications_generated", [])
                messages = state.get("agent_messages", [])
            else:
                logger.info("No checkpoint found, starting fresh")
                jobs_found = []
                jobs_processed = set()
                applications = []
                messages = []
        else:
            jobs_found = []
            jobs_processed = set()
            applications = []
            messages = []
        
        # Initialize conversation if starting fresh
        if not messages:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages.append({"role": "user", "content": f"Search for jobs: {query}"})
        
        # Step 1: Search for jobs (if not already done)
        if not jobs_found:
            logger.info("Searching for jobs...")
            jobs_found = search_freehire(
                query=query,
                limit=self.max_jobs,
                audit_logger=self.audit_logger
            )
            self.audit_logger.log_event(
                event_type="jobs_found",
                count=len(jobs_found)
            )
            
            # Checkpoint after finding jobs
            self._save_checkpoint(
                query=query,
                jobs_found=jobs_found,
                jobs_processed=jobs_processed,
                applications=applications,
                messages=messages,
                status="search_complete"
            )
        
        # Step 2: Process each job
        for idx, job_data in enumerate(jobs_found):
            job_id = job_data.get("id", f"job_{idx}")
            
            # Skip if already processed
            if job_id in jobs_processed:
                logger.info(f"Skipping already processed job {job_id}")
                continue
            
            logger.info(f"Processing job {idx + 1}/{len(jobs_found)}: {job_id}")
            
            try:
                # Generate application materials
                job = Job(**job_data)
                app = generate_application(
                    job=job,
                    llm_client=self.llm_client,
                    audit_logger=self.audit_logger
                )
                
                applications.append({
                    "job_id": job_id,
                    "cover_letter": app.cover_letter,
                    "cv_bullets": app.cv_bullets
                })
                jobs_processed.add(job_id)
                
                self.audit_logger.log_event(
                    event_type="job_processed",
                    job_id=job_id,
                    progress=f"{len(jobs_processed)}/{len(jobs_found)}"
                )
                
                # Checkpoint after each job
                self._save_checkpoint(
                    query=query,
                    jobs_found=jobs_found,
                    jobs_processed=jobs_processed,
                    applications=applications,
                    messages=messages,
                    status="in_progress"
                )
                
            except Exception as e:
                logger.error(f"Failed to process job {job_id}: {e}")
                self.audit_logger.log_event(
                    event_type="job_failed",
                    job_id=job_id,
                    error=str(e)
                )
                # Continue with next job (partial completion)
                continue
        
        # Final checkpoint
        self._save_checkpoint(
            query=query,
            jobs_found=jobs_found,
            jobs_processed=jobs_processed,
            applications=applications,
            messages=messages,
            status="completed"
        )
        
        return {
            "query": query,
            "jobs_found": jobs_found,
            "jobs_processed": list(jobs_processed),
            "applications": applications,
            "checkpoint_file": str(self.checkpoint_manager.get_checkpoint_path())
        }
    
    def _save_checkpoint(
        self,
        query: str,
        jobs_found: List[Dict],
        jobs_processed: set,
        applications: List[Dict],
        messages: List[Dict],
        status: str
    ):
        """Helper to save checkpoint with current state."""
        state = {
            "search_query": query,
            "jobs_found": jobs_found,
            "jobs_processed": list(jobs_processed),
            "applications_generated": applications,
            "agent_messages": messages,
            "status": status
        }
        self.checkpoint_manager.save_checkpoint(state)