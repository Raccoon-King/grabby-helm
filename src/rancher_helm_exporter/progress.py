"""Progress tracking utilities for export operations."""
from __future__ import annotations

import logging
import sys
import time
from typing import Optional, Protocol

from .types import ProgressCallback


class ProgressTracker(ProgressCallback):
    """Simple progress tracker with console output."""
    
    def __init__(self, enabled: bool = True, show_percentage: bool = True):
        self.enabled = enabled
        self.show_percentage = show_percentage
        self.logger = logging.getLogger(__name__)
        self._last_update = 0.0
        self._update_interval = 0.1  # Update at most every 100ms
    
    def update(self, current: int, total: int, message: str = "") -> None:
        """Update progress display."""
        if not self.enabled:
            return
        
        # Throttle updates
        now = time.time()
        if now - self._last_update < self._update_interval and current < total:
            return
        
        self._last_update = now
        
        if total > 0:
            if self.show_percentage:
                percentage = (current / total) * 100
                progress_msg = f"Progress: {current}/{total} ({percentage:.1f}%)"
            else:
                progress_msg = f"Progress: {current}/{total}"
        else:
            progress_msg = f"Processed: {current}"
        
        if message:
            progress_msg += f" - {message}"
        
        # Use carriage return to overwrite the line
        if current < total:
            print(f"\\r{progress_msg}", end="", flush=True)
        else:
            print(f"\\r{progress_msg}")  # Final update with newline
    
    def finish(self, message: str = "Complete") -> None:
        """Mark progress as finished."""
        if self.enabled:
            print(f"\\r{message}")


class SilentProgressTracker(ProgressCallback):
    """Progress tracker that only logs to the logger."""
    
    def __init__(self, log_interval: int = 10):
        self.log_interval = log_interval
        self.logger = logging.getLogger(__name__)
        self._last_logged = 0
    
    def update(self, current: int, total: int, message: str = "") -> None:
        """Log progress updates at intervals."""
        if current == 0 or current % self.log_interval == 0 or current == total:
            if total > 0:
                percentage = (current / total) * 100
                self.logger.info("Progress: %d/%d (%.1f%%) %s", current, total, percentage, message)
            else:
                self.logger.info("Processed: %d %s", current, message)


class RichProgressTracker(ProgressCallback):
    """Progress tracker using rich library for enhanced display."""
    
    def __init__(self):
        self.enabled = True
        self.progress = None
        self.task_id = None
        
        try:
            from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
            self.progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeRemainingColumn(),
            )
            self.progress.start()
        except ImportError:
            # Fallback to simple tracker if rich is not available
            self.enabled = False
            self.fallback = ProgressTracker()
    
    def update(self, current: int, total: int, message: str = "") -> None:
        """Update progress using rich progress bar."""
        if not self.enabled:
            self.fallback.update(current, total, message)
            return
        
        if self.task_id is None and self.progress:
            self.task_id = self.progress.add_task(message or "Processing...", total=total)
        
        if self.progress and self.task_id is not None:
            self.progress.update(self.task_id, completed=current, description=message or "Processing...")
    
    def finish(self, message: str = "Complete") -> None:
        """Finish the progress tracking."""
        if self.enabled and self.progress:
            if self.task_id is not None:
                self.progress.update(self.task_id, description=message)
            self.progress.stop()
        elif hasattr(self, 'fallback'):
            self.fallback.finish(message)


def create_progress_tracker(
    enabled: bool = True,
    use_rich: bool = True,
    silent: bool = False,
) -> ProgressCallback:
    """
    Create an appropriate progress tracker based on the environment.
    
    Args:
        enabled: Whether progress tracking is enabled
        use_rich: Whether to try using rich library for enhanced display
        silent: Whether to use silent (log-only) progress tracking
        
    Returns:
        Appropriate progress tracker instance
    """
    if not enabled:
        return SilentProgressTracker()
    
    if silent:
        return SilentProgressTracker()
    
    if use_rich:
        try:
            return RichProgressTracker()
        except ImportError:
            pass
    
    return ProgressTracker(enabled=enabled)


class BatchProgressTracker:
    """Tracks progress across multiple batches or phases."""
    
    def __init__(self, progress_tracker: ProgressCallback):
        self.tracker = progress_tracker
        self.phases: list[tuple[str, int]] = []
        self.current_phase = 0
        self.total_items = 0
        self.completed_items = 0
    
    def add_phase(self, name: str, item_count: int) -> None:
        """Add a phase to track."""
        self.phases.append((name, item_count))
        self.total_items += item_count
    
    def start_phase(self, phase_index: int) -> None:
        """Start tracking a specific phase."""
        if 0 <= phase_index < len(self.phases):
            self.current_phase = phase_index
    
    def update_phase_progress(self, current: int) -> None:
        """Update progress within the current phase."""
        if self.current_phase < len(self.phases):
            phase_name, phase_total = self.phases[self.current_phase]
            
            # Calculate total progress
            items_before_current_phase = sum(
                count for _, count in self.phases[:self.current_phase]
            )
            total_completed = items_before_current_phase + current
            
            message = f"{phase_name} ({current}/{phase_total})"
            self.tracker.update(total_completed, self.total_items, message)
    
    def complete_phase(self) -> None:
        """Mark the current phase as complete and move to the next."""
        if self.current_phase < len(self.phases):
            _, phase_count = self.phases[self.current_phase]
            self.completed_items += phase_count
            self.current_phase += 1
    
    def finish(self) -> None:
        """Mark all phases as complete."""
        self.tracker.update(self.total_items, self.total_items, "Complete")


class TimedProgressTracker:
    """Progress tracker that also measures and reports timing."""
    
    def __init__(self, progress_tracker: ProgressCallback):
        self.tracker = progress_tracker
        self.start_time = time.time()
        self.phase_start_time = time.time()
        self.logger = logging.getLogger(__name__)
    
    def update(self, current: int, total: int, message: str = "") -> None:
        """Update progress with timing information."""
        elapsed = time.time() - self.start_time
        
        if current > 0:
            rate = current / elapsed
            if total > current:
                eta = (total - current) / rate
                timing_msg = f"Rate: {rate:.1f}/s, ETA: {eta:.1f}s"
            else:
                timing_msg = f"Rate: {rate:.1f}/s, Total time: {elapsed:.1f}s"
            
            if message:
                message = f"{message} | {timing_msg}"
            else:
                message = timing_msg
        
        self.tracker.update(current, total, message)
    
    def start_phase(self, phase_name: str) -> None:
        """Start timing a new phase."""
        self.phase_start_time = time.time()
        self.logger.info("Starting phase: %s", phase_name)
    
    def end_phase(self, phase_name: str) -> None:
        """End timing the current phase."""
        phase_duration = time.time() - self.phase_start_time
        self.logger.info("Completed phase '%s' in %.2fs", phase_name, phase_duration)
    
    def finish(self) -> None:
        """Finish tracking with total time."""
        total_time = time.time() - self.start_time
        self.logger.info("Export completed in %.2fs", total_time)
        self.tracker.finish(f"Complete (took {total_time:.1f}s)")