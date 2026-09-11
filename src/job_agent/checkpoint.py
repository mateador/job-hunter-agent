"""
Day 11: Checkpoint manager for agent state persistence.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class CheckpointManager:
    """
    Manages checkpoint persistence for agent state.
    
    Checkpoints are stored as JSONL (one JSON object per line).
    The latest checkpoint is the last line of the file.
    """
    
    def __init__(self, checkpoint_dir: str = "checkpoints", run_id: Optional[str] = None):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate run_id if not provided
        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_id = run_id
        
        self.checkpoint_file = self.checkpoint_dir / f"checkpoint_{run_id}.jsonl"
        self.checkpoint_counter = 0
        
    def save_checkpoint(self, state: Dict[str, Any]) -> int:
        """
        Save a checkpoint with the current agent state.
        
        Args:
            state: Dictionary containing agent state (jobs_found, jobs_processed, etc.)
            
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
            state: Dictionary containing the latest agent state, or None if no checkpoint exists
        """
        if not self.checkpoint_file.exists():
            logger.info(f"No checkpoint file found at {self.checkpoint_file}")
            return None
        
        try:
            with open(self.checkpoint_file, "r") as f:
                lines = f.readlines()
                
            if not lines:
                logger.info("Checkpoint file is empty")
                return None
            
            # Read the last line (most recent checkpoint)
            last_line = lines[-1].strip()
            if not last_line:
                logger.warning("Last line of checkpoint file is empty")
                return None
            
            checkpoint = json.loads(last_line)
            self.checkpoint_counter = checkpoint["checkpoint_id"]
            
            logger.info(
                f"Loaded checkpoint {self.checkpoint_counter} "
                f"from {self.checkpoint_file}"
            )
            return checkpoint["state"]
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None
    
    def get_checkpoint_path(self) -> Path:
        """Return the path to the checkpoint file."""
        return self.checkpoint_file
    
    def list_checkpoints(self) -> list[Dict[str, Any]]:
        """
        List all checkpoints for this run.
        
        Returns:
            List of checkpoint metadata (timestamp, checkpoint_id)
        """
        if not self.checkpoint_file.exists():
            return []
        
        checkpoints = []
        with open(self.checkpoint_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        checkpoint = json.loads(line)
                        checkpoints.append({
                            "checkpoint_id": checkpoint["checkpoint_id"],
                            "timestamp": checkpoint["timestamp"]
                        })
                    except (json.JSONDecodeError, KeyError):
                        continue
        
        return checkpoints