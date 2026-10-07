"""
Day 15: Agent runner with CV text support for tailored applications.
"""
import logging
from typing import List, Dict, Any, Optional

from .llm_client import LLMClient
from .routing import ModelRouter
from .audit_logger import AuditLogger
from .checkpoint import CheckpointManager, CheckpointError, CorruptedCheckpointError
from .tools import search_freehire, search_duckduckgo, research_company
from .research_policy import should_research, normalise_company
from .models import Job, Application, FailedJob
from .prompts import SYSTEM_PROMPT
from .application_generator import generate_application
from .failures import classify_exception
from .grounding import extract_numbers, ungrounded_numbers

logger = logging.getLogger(__name__)


class ResumeError(Exception):
    """Raised when resume fails due to state issues."""
    pass


class InvalidQueryError(ValueError):
    """Raised when the search query is empty or whitespace-only."""


class AgentRunner:
    def __init__(
        self,
        audit_logger: AuditLogger,
        checkpoint_manager: CheckpointManager,
        model: str = "gpt-4o-mini",
        max_jobs: int = 10,
        cv_text: Optional[str] = None,
        retry_model: Optional[str] = None,
    ):
        self.audit_logger = audit_logger
        self.checkpoint_manager = checkpoint_manager
        self.llm_client = LLMClient(audit_logger=audit_logger, model=model,
                                    router=ModelRouter(model, retry_model))
        self.max_jobs = max_jobs
        self.cv_text = cv_text

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
            if not query or not query.strip():
                raise InvalidQueryError(
                    "Search query is empty. An empty query returns an unfiltered job feed."
                )
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
        researched: Dict[str, Any] = {}  # normalised company -> CompanyResearch or None
        research_decisions: List[Dict[str, Any]] = []
        for idx, job_data in enumerate(jobs_found):
            job_id = job_data.get("id", f"job_{idx}")

            if job_id in jobs_processed:
                logger.info(f"Skipping already processed job {job_id}")
                continue

            logger.info(f"Processing job {idx + 1}/{len(jobs_found)}: {job_id}")

            try:
                job = Job(**job_data)
                company_research = self._maybe_research(job, researched, research_decisions)
                app = self._generate_checked(job, company_research)

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

                failure_record = classify_exception(
                    e,
                    tool_name="application_generation",
                    attempt_number=1
                )

                failed_job = FailedJob(
                    job_id=job_id,
                    job_title=job_data.get("title", "Unknown"),
                    error=str(e),
                    error_category=failure_record.category.value,
                    attempt_number=failure_record.attempt_number
                )
                failed_jobs.append(failed_job)

                jobs_processed.add(job_id)

                self.audit_logger.log_event(
                    event_type="job_failed",
                    job_id=job_id,
                    error=str(e),
                    error_category=failure_record.category.value
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
            "status": status,
            "research_decisions": research_decisions,
            "usage": self.llm_client.usage.summary(),
        }

    def _generate_checked(self, job: Job, company_research) -> Application:
        """Generate an application, regenerating once if it states figures nobody supplied.

        Numbers must appear in the CV, the posting or the research. On a second violation the
        application is kept but carries a warning, so the report flags it for review.
        """
        def generate(revision_note: Optional[str] = None) -> Application:
            purpose = "grounding_retry" if revision_note else "application"
            with self.llm_client.tagged(job_id=job.id, purpose=purpose):
                return generate_application(
                    job=job,
                    llm_client=self.llm_client,
                    audit_logger=self.audit_logger,
                    cv_text=self.cv_text,
                    company_research=company_research,
                    revision_note=revision_note,
                )

        app = generate()
        if not extract_numbers(self.cv_text):
            return app  # nothing to ground against (no CV, or a CV without figures)

        sources = [self.cv_text, job.title, job.description,
                   company_research.summary if company_research else None]

        def violations(candidate: Application) -> list:
            return ungrounded_numbers(candidate.cover_letter + " " + " ".join(candidate.cv_bullets), sources)

        bad = violations(app)
        if not bad:
            return app
        self.audit_logger.log_event(event_type="grounding_violation", job_id=job.id, numbers=bad, attempt=1)
        logger.warning(f"Ungrounded figures {bad} for job {job.id}; regenerating once")
        self.audit_logger.log_event(event_type="grounding_retry", job_id=job.id)
        note = (
            "Your previous draft stated figures that do not appear in the candidate's CV or the "
            f"job posting: {', '.join(bad)}. Rewrite the letter and bullets without them. Remove "
            "every unsupported figure and any claim that depended on it, and use only facts "
            "present in the CV. Do not introduce any new numbers."
        )
        try:
            retry_app = generate(note)
        except Exception as e:  # keep the first draft rather than losing the job
            logger.warning(f"Regeneration failed for {job.id}: {e}")
            app.warnings.append(
                f"Figures not found in your CV or the posting: {', '.join(bad)}. "
                "Regeneration failed, so check before sending."
            )
            self.audit_logger.log_event(event_type="grounding_flagged", job_id=job.id, numbers=bad)
            return app

        bad = violations(retry_app)
        if bad:
            self.audit_logger.log_event(event_type="grounding_violation", job_id=job.id, numbers=bad, attempt=2)
            self.audit_logger.log_event(event_type="grounding_flagged", job_id=job.id, numbers=bad)
            retry_app.warnings.append(
                f"Figures not found in your CV or the posting: {', '.join(bad)}. Check before sending."
            )
        return retry_app

    def _maybe_research(
        self,
        job: Job,
        researched: Dict[str, Any],
        decisions: List[Dict[str, Any]],
    ):
        """Escalate to company research when the policy says so. Never raises."""
        decision, reason = should_research(job, researched)
        company_key = normalise_company(job.company)
        record: Dict[str, Any] = {
            "job_id": job.id,
            "company": job.company,
            "decision": decision,
            "reason": reason,
            "description_chars": len((job.description or "").strip()),
            "error": None,
            "summary": None,
            "sources": [],
        }
        self.audit_logger.log_event(
            event_type="research_decision",
            job_id=job.id,
            company=job.company,
            decision=decision,
            reason=reason,
            description_chars=record["description_chars"],
        )

        research = None
        if decision:
            try:
                research = research_company(job.company, audit_logger=self.audit_logger)
            except Exception as e:  # research is optional: degrade, never fail the job
                failure = classify_exception(e, tool_name="research_company", attempt_number=1)
                record["error"] = f"{failure.category.value}: {e}"
                self.audit_logger.log_event(
                    event_type="research_failed",
                    job_id=job.id,
                    company=job.company,
                    error=str(e),
                    error_category=failure.category.value,
                )
                logger.warning(f"Company research failed for {job.company}, continuing without it: {e}")
            researched[company_key] = research
        elif reason == "already_researched":
            research = researched.get(company_key)

        if research:
            record["summary"] = research.summary
            record["sources"] = list(research.sources)
        decisions.append(record)
        return research

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
            "status": status,
            "has_cv_text": self.cv_text is not None,
        }
        self.checkpoint_manager.save_checkpoint(state)