"""Background scheduler for periodic aircraft ingestion."""

import atexit
import logging
from datetime import datetime, timezone
from math import isfinite

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .data_ingestion import fetch_and_store_aircraft_job

logger = logging.getLogger(__name__)
scheduler = None


def start_scheduler(interval_minutes: int = 5):
    """Start ingestion at the given interval; the first run follows one interval."""
    global scheduler
    if scheduler is not None and scheduler.running:
        logger.warning('Scheduler already running')
        return scheduler
    if not isfinite(interval_minutes) or interval_minutes <= 0:
        raise ValueError('interval_minutes must be finite and positive')

    instance = BackgroundScheduler(timezone=timezone.utc)
    instance.add_job(
        func=fetch_and_store_aircraft_job,
        trigger=IntervalTrigger(minutes=interval_minutes, timezone=timezone.utc),
        id='fetch_aircraft',
        name='Fetch Aircraft Data',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    instance.start()
    scheduler = instance
    logger.info('Scheduler started; fetching every %s minutes', interval_minutes)
    return scheduler


def stop_scheduler():
    """Stop the scheduler, waiting for any running job to finish."""
    global scheduler
    if scheduler is not None:
        if scheduler.running:
            scheduler.shutdown(wait=True)
        scheduler = None
        logger.info('Scheduler stopped')


def get_scheduler_status():
    """Return scheduler state and scheduled job times."""
    if scheduler is None or not scheduler.running:
        return {'running': False, 'jobs': []}
    return {
        'running': scheduler.running,
        'jobs': [
            {
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in scheduler.get_jobs()
        ],
    }


def trigger_job_now(job_id: str = 'fetch_aircraft'):
    """Schedule an existing job immediately while keeping its interval trigger."""
    if scheduler is None or not scheduler.running:
        logger.error('Scheduler not running')
        return False
    try:
        if scheduler.get_job(job_id) is None:
            logger.error('Job %s not found', job_id)
            return False
        scheduler.modify_job(job_id, next_run_time=datetime.now(timezone.utc))
        return True
    except Exception:
        logger.exception('Error triggering job %s', job_id)
        return False


atexit.register(stop_scheduler)
