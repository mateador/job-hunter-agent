"""
Day 13: Agent runner with partial completion tracking.
"""
import logging
from typing import List, Dict, Any, Optional

from .llm_client import LLMClient
from .audit_logger import AuditLogger
from .checkpoint import CheckpointManager, CheckpointError, CorruptedCheckpointError
from .tools import search_freehire, search_duckduckgo
from .models import Job, Application, FailedJob
from .prompts import SYSTEM_PROMPT
from .application_generator import generate_application
from .failures import classify_exception

logger = logging.getLogger(__name__)


class ResumeError(Exception):
    """Raised when resume fails due to state issues."""
    pass


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

    def run(
        self,
        query: str,
        resume: bool = False,
        resume_from: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run the agent loop with partial completion support.

        Args:
            query: Job search query
            resume: If True, resume from latest checkpoint
            resume_from: If set, resume from a specific checkpoint ID

        Returns:
            Dictionary containing jobs, applications, failures, and metadata
        """
        # ── Initialize or resume state ──
        if resume or resume_from is not None:
            state = self._load_resume_state(resume_from)
            if state is not None:
                saved_query = state.get("search_query", "")
                if saved_query and saved_query != query:
                    raise ResumeError(
                        f"Query mismatch: checkpoint was for '{saved_query}' "
                        f"but you requested '{query}'. "
                        f"Use the original query to resume."
                    )

                jobs_found = state.get("jobs_found", [])
                jobs_processed = set(state.get("jobs_processed", []))
                applications = [Application(**app) for app in state.get("applications_generated", [])]
                failed_jobs = [FailedJob(**fj) for fj in state.get("failed_jobs", [])]
                messages = state.get("agent_messages", [])

                self.audit_logger.log_event(
                    event_type="resume",
                    checkpoint_id=self.checkpoint_manager.checkpoint_counter,
                    jobs_already_processed=len(jobs_processed),
                    jobs_remaining=len(jobs_found) - len(jobs_processed),
                    status=state.get("status")
                )
                logger.info(
                    f"Resumed: {len(jobs_processed)}/{len(jobs_found)} jobs "
                    f"already processed, {len(applications)} applications generated, "
                    f"{len(failed_jobs)} failures"
                )
            else:
                logger.info("No valid checkpoint found, starting fresh")
                jobs_found, jobs_processed, applications, failed_jobs, messages = self._fresh_state()
        else:
            jobs_found, jobs_processed, applications, failed_jobs, messages = self._fresh_state()

        # ── Step 1: Search for jobs (if not already done) ──
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
            self._save_checkpoint(
                query=query,
                jobs_found=jobs_found,
                jobs_processed=jobs_processed,
                applications=applications,
                failed_jobs=failed_jobs,
                messages=messages,
                status="search_complete"
            )

        # ── Step 2: Process each job ──
        for idx, job_data in enumerate(jobs_found):
            job_id = job_data.get("id", f"job_{idx}")

            if job_id in jobs_processed:
                logger.info(f"Skipping already processed job {job_id}")
                continue

            logger.info(f"Processing job {idx + 1}/{len(jobs_found)}: {job_id}")

            try:
                job = Job(**job_data)
                app = generate_application(
                    job=job,
                    llm_client=self.llm_client,
                    audit_logger=self.audit_logger
                )

                applications.append(app)
                jobs_processed.add(job_id)

                self.audit_logger.log_event(
                    event_type="job_processed",
                    job_id=job_id,
                    progress=f"{len(jobs_processed)}/{len(jobs_found)}"
                )

                self._save_checkpoint(
                    query=query,
                    jobs_found=jobs_found,
                    jobs_processed=jobs_processed,
                    applications=applications,
                    failed_jobs=failed_jobs,
                    messages=messages,
                    status="in_progress"
                )

            except Exception as e:
                logger.error(f"Failed to process job {job_id}: {e}")
                
                # Classify the failure
                failure_record = classify_exception(
                    e,
                    tool_name="application_generation",
                    attempt_number=1
                )
                
                # Track the failure
                failed_job = FailedJob(
                    job_id=job_id,
                    job_title=job_data.get("title", "Unknown"),
                    error=str(e),
                    error_category=failure_record.category.value,
                    attempt_number=failure_record.attempt_number
                )
                failed_jobs.append(failed_job)
                
                # Mark as processed so we don't retry
                jobs_processed.add(job_id)
                
                self.audit_logger.log_event(
                    event_type="job_failed",
                    job_id=job_id,
                    error=str(e),
                    error_category=failure_record.category.value
                )
                
                # Save checkpoint with failure tracked
                self._save_checkpoint(
                    query=query,
                    jobs_found=jobs_found,
                    jobs_processed=jobs_processed,
                    applications=applications,
                    failed_jobs=failed_jobs,
                    messages=messages,
                    status="in_progress"
                )
                continue

        # ── Determine final status ──
        if len(applications) == len(jobs_found):
            status = "completed"
        elif len(applications) > 0:
            status = "partial"
        else:
            status = "failed"

        # ── Final checkpoint ──
        self._save_checkpoint(
            query=query,
            jobs_found=jobs_found,
            jobs_processed=jobs_processed,
            applications=applications,
            failed_jobs=failed_jobs,
            messages=messages,
            status=status
        )

        return {
            "query": query,
            "jobs_found": [Job(**j) for j in jobs_found],
            "applications": applications,
            "failed_jobs": failed_jobs,
            "checkpoint_file": str(self.checkpoint_manager.get_checkpoint_path()),
            "status": status
        }

    def _load_resume_state(self, checkpoint_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Load state from a specific checkpoint or the latest one."""
        try:
            if checkpoint_id is not None:
                logger.info(f"Attempting to resume from checkpoint {checkpoint_id}")
                return self.checkpoint_manager.load_checkpoint(checkpoint_id)
            else:
                logger.info("Attempting to resume from latest checkpoint")
                return self.checkpoint_manager.load_latest_checkpoint()
        except CorruptedCheckpointError as e:
            logger.error(f"Checkpoint corrupted: {e}")
            self.audit_logger.log_event(
                event_type="resume_failed",
                reason="corrupted_checkpoint",
                error=str(e)
            )
            return None
        except CheckpointError as e:
            logger.warning(f"Checkpoint not found: {e}")
            return None

    @staticmethod
    def _fresh_state():
        """Return empty initial state."""
        return [], set(), [], [], []

    def _save_checkpoint(
        self,
        query: str,
        jobs_found: List[Dict],
        jobs_processed: set,
        applications: List[Application],
        failed_jobs: List[FailedJob],
        messages: List[Dict],
        status: str
    ):
        """Helper to save checkpoint with current state."""
        state = {
            "search_query": query,
            "jobs_found": jobs_found,
            "jobs_processed": list(jobs_processed),
            "applications_generated": [app.model_dump() for app in applications],
            "failed_jobs": [fj.model_dump() for fj in failed_jobs],
            "agent_messages": messages,
            "status": status
        }
        self.checkpoint_manager.save_checkpoint(state)