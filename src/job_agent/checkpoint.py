"""
Day 11 + Day 12: Checkpoint manager for agent state persistence.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# Required keys for a valid checkpoint state
REQUIRED_STATE_KEYS = {
    "search_query",
    "jobs_found",
    "jobs_processed",
    "applications_generated",
    "status"
}

VALID_STATUSES = {"search_complete", "in_progress", "completed", "failed"}


class CheckpointError(Exception):
    """Raised when checkpoint operations fail."""
    pass


class CorruptedCheckpointError(CheckpointError):
    """Raised when a checkpoint file contains invalid data."""
    pass


class CheckpointManager:
    """
    Manages checkpoint persistence for agent state.

    Checkpoints are stored as JSONL (one JSON object per line).
    The latest checkpoint is the last line of the file.
    """

    def __init__(self, checkpoint_dir: str = "checkpoints", run_id: Optional[str] = None):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_id = run_id

        self.checkpoint_file = self.checkpoint_dir / f"checkpoint_{run_id}.jsonl"
        self.checkpoint_counter = 0

    def save_checkpoint(self, state: Dict[str, Any]) -> int:
        """
        Save a checkpoint with the current agent state.

        Returns:
            checkpoint_id: The ID of the saved checkpoint
        """
        self.checkpoint_counter += 1

        checkpoint = {
            "timestamp": datetime.utcnow().isoformat(),
            "checkpoint_id": self.checkpoint_counter,
            "run_id": self.run_id,
            "state": state
        }

        with open(self.checkpoint_file, "a") as f:
            f.write(json.dumps(checkpoint, default=str) + "\n")

        logger.info(f"Checkpoint {self.checkpoint_counter} saved to {self.checkpoint_file}")
        return self.checkpoint_counter

    def load_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        """
        Load the most recent checkpoint.

        Returns:
            state: Dictionary containing the latest agent state, or None if none exists
        """
        if not self.checkpoint_file.exists():
            logger.info(f"No checkpoint file found at {self.checkpoint_file}")
            return None

        lines = self._read_lines()
        if not lines:
            return None

        # Walk backwards to find the last valid checkpoint
        for line in reversed(lines):
            checkpoint = self._parse_line(line)
            if checkpoint is not None:
                self.checkpoint_counter = checkpoint["checkpoint_id"]
                state = checkpoint["state"]
                self.validate_state(state)
                logger.info(
                    f"Loaded checkpoint {self.checkpoint_counter} "
                    f"from {self.checkpoint_file}"
                )
                return state

        raise CorruptedCheckpointError(
            f"No valid checkpoints found in {self.checkpoint_file}"
        )

    def load_checkpoint(self, checkpoint_id: int) -> Dict[str, Any]:
        """
        Load a specific checkpoint by ID.

        Args:
            checkpoint_id: The ID of the checkpoint to load

        Returns:
            state: Dictionary containing the checkpoint state

        Raises:
            CheckpointError: If the checkpoint ID is not found
            CorruptedCheckpointError: If the checkpoint data is invalid
        """
        if not self.checkpoint_file.exists():
            raise CheckpointError(
                f"No checkpoint file found at {self.checkpoint_file}"
            )

        lines = self._read_lines()
        for line in lines:
            checkpoint = self._parse_line(line)
            if checkpoint is not None and checkpoint["checkpoint_id"] == checkpoint_id:
                state = checkpoint["state"]
                self.validate_state(state)
                self.checkpoint_counter = checkpoint_id
                logger.info(f"Loaded checkpoint {checkpoint_id}")
                return state

        raise CheckpointError(
            f"Checkpoint {checkpoint_id} not found in {self.checkpoint_file}"
        )

    @staticmethod
    def validate_state(state: Dict[str, Any]) -> None:
        """
        Validate that a checkpoint state contains all required keys
        and has valid values.

        Raises:
            CorruptedCheckpointError: If state is invalid
        """
        if not isinstance(state, dict):
            raise CorruptedCheckpointError(f"State must be a dict, got {type(state)}")

        missing = REQUIRED_STATE_KEYS - set(state.keys())
        if missing:
            raise CorruptedCheckpointError(f"Missing required state keys: {missing}")

        if state["status"] not in VALID_STATUSES:
            raise CorruptedCheckpointError(
                f"Invalid status '{state['status']}'. "
                f"Must be one of {VALID_STATUSES}"
            )

        if not isinstance(state["jobs_found"], list):
            raise CorruptedCheckpointError("jobs_found must be a list")

        if not isinstance(state["jobs_processed"], list):
            raise CorruptedCheckpointError("jobs_processed must be a list")

        if not isinstance(state["applications_generated"], list):
            raise CorruptedCheckpointError("applications_generated must be a list")

    def find_interrupted_runs(self) -> List[Dict[str, Any]]:
        """
        Scan all checkpoint files and find runs that did not complete.

        Returns:
            List of dicts with run_id, last_checkpoint_id, status, timestamp,
            and jobs_progress info.
        """
        interrupted = []

        for cp_file in sorted(self.checkpoint_dir.glob("checkpoint_*.jsonl")):
            run_id = cp_file.stem.replace("checkpoint_", "")
            lines = self._read_lines_from(cp_file)

            if not lines:
                continue

            # Find the last valid checkpoint in this file
            last_valid = None
            for line in reversed(lines):
                parsed = self._parse_line(line)
                if parsed is not None:
                    last_valid = parsed
                    break

            if last_valid is None:
                continue

            state = last_valid["state"]
            status = state.get("status", "unknown")

            if status not in ("completed",):
                jobs_found = len(state.get("jobs_found", []))
                jobs_processed = len(state.get("jobs_processed", []))
                interrupted.append({
                    "run_id": run_id,
                    "last_checkpoint_id": last_valid["checkpoint_id"],
                    "status": status,
                    "timestamp": last_valid["timestamp"],
                    "query": state.get("search_query", "unknown"),
                    "progress": f"{jobs_processed}/{jobs_found} jobs processed"
                })

        return interrupted

    def get_checkpoint_path(self) -> Path:
        """Return the path to the checkpoint file."""
        return self.checkpoint_file

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all checkpoints for this run."""
        if not self.checkpoint_file.exists():
            return []

        checkpoints = []
        for line in self._read_lines():
            parsed = self._parse_line(line)
            if parsed is not None:
                checkpoints.append({
                    "checkpoint_id": parsed["checkpoint_id"],
                    "timestamp": parsed["timestamp"],
                    "status": parsed["state"].get("status", "unknown")
                })

        return checkpoints

    # ── Internal helpers ──

    def _read_lines(self) -> List[str]:
        """Read all non-empty lines from the checkpoint file."""
        return self._read_lines_from(self.checkpoint_file)

    @staticmethod
    def _read_lines_from(path: Path) -> List[str]:
        """Read all non-empty lines from a given file."""
        if not path.exists():
            return []
        with open(path, "r") as f:
            return [line for line in f if line.strip()]

    @staticmethod
    def _parse_line(line: str) -> Optional[Dict[str, Any]]:
        """Parse a single JSONL line, returning None on failure."""
        try:
            return json.loads(line.strip())
        except json.JSONDecodeError:
            logger.warning(f"Skipping corrupted checkpoint line: {line[:80]}...")
            return None