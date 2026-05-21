"""
Phase 6.11: Scheduled Flow Executor
Polls for flows with scheduled triggers and executes them at the right time.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
import pytz

from models import FlowDefinition, FlowNode, FlowRun
from flows.flow_engine import FlowEngine

logger = logging.getLogger(__name__)

# Brazil timezone (GMT-3)
BRAZIL_TZ = pytz.timezone('America/Sao_Paulo')


class ScheduledFlowExecutor:
    """
    Polls for scheduled flows and executes them when their time arrives.
    """

    def __init__(self, db: Session, poll_interval_seconds: int = 10):
        self.db = db
        self.poll_interval = poll_interval_seconds
        self.flow_engine = FlowEngine(db)
        self.running = False

    async def start(self):
        """Start the scheduled flow executor (non-blocking)."""
        self.running = True
        logger.info(f"ScheduledFlowExecutor started (polling every {self.poll_interval}s)")

        while self.running:
            try:
                await self.check_and_execute_scheduled_flows()
            except Exception as e:
                logger.error(f"Error in scheduled flow executor: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    def stop(self):
        """Stop the executor."""
        self.running = False
        logger.info("ScheduledFlowExecutor stopped")

    async def check_and_execute_scheduled_flows(self):
        """
        Check for flows that are scheduled to run now and execute them.
        """
        logger.info("🔍 Checking for scheduled flows...")

        # Find active flows
        active_flows = self.db.query(FlowDefinition).filter(
            FlowDefinition.is_active == True
        ).all()

        logger.info(f"📋 Found {len(active_flows)} active flows")

        # Use timezone-aware UTC time
        now_utc = datetime.now(pytz.UTC).replace(tzinfo=None)  # Naive UTC for comparison
        logger.info(f"🕐 Current UTC time: {now_utc}")

        for flow in active_flows:
            try:
                logger.info(f"⚙️  Checking flow #{flow.id} '{flow.name}' (method: {flow.execution_method})")

                # Check if flow has a time trigger
                should_execute, trigger_context = self._should_execute_flow(flow, now_utc)

                if should_execute:
                    logger.info(f"✅ Executing scheduled flow #{flow.id}: {flow.name}")

                    # Execute flow asynchronously
                    await self._execute_flow_async(flow, trigger_context)
                else:
                    logger.info(f"⏭️  Flow #{flow.id} not due for execution")

            except Exception as e:
                logger.error(f"❌ Error checking/executing flow #{flow.id}: {e}", exc_info=True)

    def _should_execute_flow(self, flow: FlowDefinition, now_utc: datetime) -> tuple:
        """
        Check if flow should execute based on its trigger configuration.
        Supports both Phase 8.0 (FlowDefinition.scheduled_at) and legacy (Trigger node).
        Now also supports recurring flows.

        Returns:
            (should_execute: bool, trigger_context: dict)
        """
        # Phase 8.0: Check recurring flows
        if flow.execution_method == 'recurring' and flow.recurrence_rule:
            return self._check_recurring_flow(flow, now_utc)

        # Phase 8.0: Check FlowDefinition-level scheduling first
        if flow.execution_method == 'scheduled' and flow.scheduled_at:
            scheduled_at = flow.scheduled_at

            # Ensure scheduled_at is naive UTC for comparison
            if scheduled_at.tzinfo is not None:
                scheduled_at = scheduled_at.astimezone(pytz.UTC).replace(tzinfo=None)

            logger.debug(f"Flow #{flow.id}: Comparing {scheduled_at} <= {now_utc}")

            if scheduled_at <= now_utc:
                # Check if already executed
                existing_run = self.db.query(FlowRun).filter(
                    FlowRun.flow_definition_id == flow.id,
                    FlowRun.status.in_(['completed', 'running'])
                ).first()

                if existing_run:
                    logger.debug(f"Flow #{flow.id} already executed/running (run #{existing_run.id})")
                    return False, {}

                logger.info(f"Flow #{flow.id} is due: scheduled={scheduled_at}, now={now_utc}")

                trigger_context = {
                    "trigger_type": "scheduled",
                    "scheduled_at": flow.scheduled_at.isoformat() if flow.scheduled_at else None,
                    "executed_at": now_utc.isoformat(),
                    "flow_type": flow.flow_type
                }

                return True, trigger_context

            return False, {}

        # Legacy: Check for Trigger node (backward compatibility)
        first_node = self.db.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow.id,
            FlowNode.position == 1
        ).first()

        if not first_node or first_node.type != "Trigger":
            return False, {}

        try:
            config = json.loads(first_node.config_json)
            trigger_type = config.get("type")

            if trigger_type == "time":
                # Time-based trigger
                scheduled_at_str = config.get("scheduled_at")
                if not scheduled_at_str:
                    return False, {}

                # Parse scheduled_at (ISO format, handle both 'Z' suffix and +00:00)
                # Replace 'Z' with '+00:00' for proper timezone parsing
                scheduled_at_str_clean = scheduled_at_str.replace('Z', '+00:00')

                try:
                    # Try parsing with timezone info first
                    scheduled_at_aware = datetime.fromisoformat(scheduled_at_str_clean)
                    # Convert to naive UTC for comparison
                    if scheduled_at_aware.tzinfo is not None:
                        scheduled_at = scheduled_at_aware.astimezone(pytz.UTC).replace(tzinfo=None)
                    else:
                        scheduled_at = scheduled_at_aware
                except ValueError:
                    # Fallback to naive parsing
                    scheduled_at = datetime.fromisoformat(scheduled_at_str.replace('Z', ''))

                # Check if time has arrived (with logging for debugging)
                logger.debug(f"Flow #{flow.id}: Comparing {scheduled_at} <= {now_utc}")

                if scheduled_at <= now_utc:
                    # Log timezone info for debugging
                    scheduled_brt = pytz.UTC.localize(scheduled_at).astimezone(BRAZIL_TZ)
                    now_brt = pytz.UTC.localize(now_utc).astimezone(BRAZIL_TZ)
                    logger.info(f"Flow #{flow.id} is due: scheduled={scheduled_brt.strftime('%Y-%m-%d %H:%M BRT')}, now={now_brt.strftime('%Y-%m-%d %H:%M BRT')}")

                    # Check if already executed
                    existing_run = self.db.query(FlowRun).filter(
                        FlowRun.flow_definition_id == flow.id,
                        FlowRun.status.in_(['completed', 'running'])
                    ).first()

                    if existing_run:
                        # Already executed or currently running
                        logger.debug(f"Flow #{flow.id} already executed/running (run #{existing_run.id})")
                        return False, {}

                    # Build trigger context
                    trigger_context = {
                        "trigger_type": "time",
                        "scheduled_at": scheduled_at_str,
                        "executed_at": now_utc.isoformat(),
                        **config.get("context_fields", {})
                    }

                    return True, trigger_context

            # Other trigger types (webhook, manual, etc.) are handled elsewhere
            return False, {}

        except Exception as e:
            logger.error(f"Error parsing trigger config for flow #{flow.id}: {e}")
            return False, {}

    def _check_recurring_flow(self, flow: FlowDefinition, now_utc: datetime) -> tuple:
        """
        Check if a recurring flow should execute based on its recurrence rule.

        Args:
            flow: FlowDefinition with recurring execution_method
            now_utc: Current time in UTC (naive)

        Returns:
            (should_execute: bool, trigger_context: dict)
        """
        try:
            # Parse recurrence rule (stored as JSON)
            recurrence_rule = flow.recurrence_rule
            if isinstance(recurrence_rule, str):
                recurrence_rule = json.loads(recurrence_rule)

            logger.info(f"🔁 Checking recurring flow #{flow.id}: rule={recurrence_rule}")

            frequency = recurrence_rule.get('frequency', 'daily')
            interval = max(int(recurrence_rule.get('interval', 1) or 1), 1)
            timezone_str = recurrence_rule.get('timezone', 'America/Sao_Paulo')
            days_of_week = recurrence_rule.get('days_of_week')  # For weekly recurrence
            start_time = recurrence_rule.get('start_time')  # HH:MM format
            cron_expression = recurrence_rule.get('cron_expression')

            logger.info(f"   Frequency: {frequency}, Interval: {interval}, Start time: {start_time}, Timezone: {timezone_str}")

            # Get timezone
            tz = pytz.timezone(timezone_str)

            # Convert now_utc to target timezone
            now_aware = pytz.UTC.localize(now_utc)
            now_local = now_aware.astimezone(tz)

            # Get last execution time
            last_executed_at = flow.last_executed_at
            if last_executed_at:
                if last_executed_at.tzinfo is None:
                    last_executed_aware = pytz.UTC.localize(last_executed_at)
                else:
                    last_executed_aware = last_executed_at.astimezone(pytz.UTC)
                last_executed_local = last_executed_aware.astimezone(tz)
            else:
                last_executed_local = None

            # Check if we should execute based on frequency
            should_execute = False
            scheduled_for = None

            if cron_expression:
                return self._check_cron_recurring_flow(
                    flow=flow,
                    recurrence_rule=recurrence_rule,
                    cron_expression=cron_expression,
                    timezone_str=timezone_str,
                    now_utc=now_utc,
                    last_executed_at=last_executed_at,
                )

            if frequency == 'hourly':
                target_minute = 0

                if flow.scheduled_at:
                    if flow.scheduled_at.tzinfo is None:
                        scheduled_aware = pytz.UTC.localize(flow.scheduled_at)
                    else:
                        scheduled_aware = flow.scheduled_at.astimezone(pytz.UTC)
                    scheduled_local = scheduled_aware.astimezone(tz)
                    target_minute = scheduled_local.minute
                else:
                    scheduled_local = None

                if start_time:
                    time_parts = start_time.split(':')
                    # For hourly recurrence, start_time provides the minute
                    # within each hour. The hour component is only meaningful
                    # when scheduled_at provides an interval anchor.
                    target_minute = int(time_parts[1]) if len(time_parts) > 1 else 0

                current_window = now_local.replace(
                    minute=target_minute,
                    second=0,
                    microsecond=0,
                )

                if now_local >= current_window:
                    scheduled_for = current_window.astimezone(pytz.UTC).replace(tzinfo=None)
                    anchor_local = scheduled_local
                    if anchor_local is None:
                        anchor_local = now_local.replace(
                            hour=0,
                            minute=target_minute,
                            second=0,
                            microsecond=0,
                        )
                    anchor_window = anchor_local.replace(
                        minute=target_minute,
                        second=0,
                        microsecond=0,
                    )
                    elapsed_hours = int((current_window - anchor_window).total_seconds() // 3600)
                    if elapsed_hours < 0 or elapsed_hours % interval != 0:
                        logger.info(f"   ✗ Hourly interval not due")
                        return False, {}

                    last_executed_utc = None
                    if last_executed_at:
                        last_executed_utc = (
                            last_executed_at.astimezone(pytz.UTC).replace(tzinfo=None)
                            if last_executed_at.tzinfo is not None
                            else last_executed_at
                        )

                    if last_executed_utc and last_executed_utc >= scheduled_for:
                        logger.info(f"   ✗ Already executed in this hourly window")
                    else:
                        logger.info(f"   ✓ Should execute hourly recurrence")
                        should_execute = True
                else:
                    logger.info(f"   ✗ Hourly target minute not yet reached")

            elif frequency == 'daily':
                # For daily, check if start_time has arrived today
                if start_time:
                    # Parse start_time (format: "HH:MM")
                    time_parts = start_time.split(':')
                    target_hour = int(time_parts[0])
                    target_minute = int(time_parts[1]) if len(time_parts) > 1 else 0

                    logger.info(f"   Target time: {target_hour:02d}:{target_minute:02d} (local)")

                    # Check if current time has passed target time today
                    current_hour = now_local.hour
                    current_minute = now_local.minute

                    logger.info(f"   Current time: {current_hour:02d}:{current_minute:02d} (local)")
                    logger.info(f"   Last executed: {last_executed_local}")

                    if (current_hour > target_hour) or (current_hour == target_hour and current_minute >= target_minute):
                        scheduled_for = now_local.replace(
                            hour=target_hour,
                            minute=target_minute,
                            second=0,
                            microsecond=0,
                        ).astimezone(pytz.UTC).replace(tzinfo=None)
                        # Check if we already executed today
                        if last_executed_local:
                            if last_executed_local.date() < now_local.date():
                                logger.info(f"   ✓ Should execute: Time passed and not executed today")
                                should_execute = True
                            else:
                                logger.info(f"   ✗ Already executed today")
                        else:
                            logger.info(f"   ✓ Should execute: Time passed and never executed")
                            should_execute = True
                    else:
                        logger.info(f"   ✗ Time not yet reached")

            elif frequency == 'weekly':
                # For weekly, check day of week and time
                if flow.scheduled_at and days_of_week:
                    current_day = now_local.isoweekday()  # 1=Monday, 7=Sunday

                    if current_day in days_of_week:
                        # Check if time has arrived
                        if flow.scheduled_at.tzinfo is None:
                            scheduled_aware = pytz.UTC.localize(flow.scheduled_at)
                        else:
                            scheduled_aware = flow.scheduled_at.astimezone(pytz.UTC)
                        scheduled_local = scheduled_aware.astimezone(tz)

                        target_hour = scheduled_local.hour
                        target_minute = scheduled_local.minute

                        current_hour = now_local.hour
                        current_minute = now_local.minute

                        if (current_hour > target_hour) or (current_hour == target_hour and current_minute >= target_minute):
                            scheduled_for = now_local.replace(
                                hour=target_hour,
                                minute=target_minute,
                                second=0,
                                microsecond=0,
                            ).astimezone(pytz.UTC).replace(tzinfo=None)
                            # Check if we already executed today
                            if last_executed_local:
                                if last_executed_local.date() < now_local.date():
                                    should_execute = True
                            else:
                                should_execute = True

            elif frequency == 'monthly':
                # For monthly, execute on same day of month at scheduled time
                if flow.scheduled_at:
                    if flow.scheduled_at.tzinfo is None:
                        scheduled_aware = pytz.UTC.localize(flow.scheduled_at)
                    else:
                        scheduled_aware = flow.scheduled_at.astimezone(pytz.UTC)
                    scheduled_local = scheduled_aware.astimezone(tz)

                    target_day = scheduled_local.day
                    target_hour = scheduled_local.hour
                    target_minute = scheduled_local.minute

                    if now_local.day == target_day:
                        current_hour = now_local.hour
                        current_minute = now_local.minute

                        if (current_hour > target_hour) or (current_hour == target_hour and current_minute >= target_minute):
                            scheduled_for = now_local.replace(
                                day=target_day,
                                hour=target_hour,
                                minute=target_minute,
                                second=0,
                                microsecond=0,
                            ).astimezone(pytz.UTC).replace(tzinfo=None)
                            # Check if we already executed this month
                            if last_executed_local:
                                if (last_executed_local.year < now_local.year) or \
                                   (last_executed_local.year == now_local.year and last_executed_local.month < now_local.month):
                                    should_execute = True
                            else:
                                should_execute = True

            if should_execute:
                logger.info(f"Recurring flow #{flow.id} is due: frequency={frequency}, last_executed={last_executed_local}")

                trigger_context = {
                    "trigger_type": "recurring",
                    "frequency": frequency,
                    "interval": interval,
                    "executed_at": now_utc.isoformat(),
                    "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
                    "flow_type": flow.flow_type
                }

                return True, trigger_context

            return False, {}

        except Exception as e:
            logger.error(f"Error checking recurring flow #{flow.id}: {e}", exc_info=True)
            return False, {}

    def _check_cron_recurring_flow(
        self,
        *,
        flow: FlowDefinition,
        recurrence_rule: dict,
        cron_expression: str,
        timezone_str: str,
        now_utc: datetime,
        last_executed_at: Optional[datetime],
    ) -> tuple:
        """
        Check recurring flow execution using a raw cron expression.

        The cron expression overrides frequency-based recurrence. We evaluate
        the next cron fire after the last execution, falling back to the flow's
        scheduled/created baseline for first execution so old windows are not
        replayed on newly-created flows.
        """
        try:
            from services.cron_preview_service import (
                calculate_next_fire_times,
                validate_cron_expression,
            )

            expression = validate_cron_expression(cron_expression)

            has_execution_baseline = bool(last_executed_at)
            if last_executed_at:
                if last_executed_at.tzinfo is not None:
                    base_utc = last_executed_at.astimezone(pytz.UTC).replace(tzinfo=None)
                else:
                    base_utc = last_executed_at
            elif flow.scheduled_at:
                if flow.scheduled_at.tzinfo is not None:
                    base_utc = flow.scheduled_at.astimezone(pytz.UTC).replace(tzinfo=None)
                else:
                    base_utc = flow.scheduled_at
            elif getattr(flow, "created_at", None):
                created_at = flow.created_at
                if created_at.tzinfo is not None:
                    base_utc = created_at.astimezone(pytz.UTC).replace(tzinfo=None)
                else:
                    base_utc = created_at
            else:
                base_utc = now_utc

            if not has_execution_baseline:
                base_utc = base_utc - timedelta(seconds=1)

            next_fire_times = calculate_next_fire_times(
                expression,
                timezone_str,
                base=base_utc,
                count=1,
            )
            if not next_fire_times:
                return False, {}

            scheduled_for = next_fire_times[0]
            if scheduled_for > now_utc:
                logger.info(
                    f"   ✗ Cron not due: next={scheduled_for.isoformat()}, now={now_utc.isoformat()}"
                )
                return False, {}

            if last_executed_at:
                last_executed_utc = (
                    last_executed_at.astimezone(pytz.UTC).replace(tzinfo=None)
                    if last_executed_at.tzinfo is not None
                    else last_executed_at
                )
                if last_executed_utc >= scheduled_for:
                    logger.info(f"   ✗ Already executed cron window {scheduled_for.isoformat()}")
                    return False, {}

            logger.info(
                f"Recurring cron flow #{flow.id} is due: cron={expression}, scheduled_for={scheduled_for}"
            )
            return True, {
                "trigger_type": "recurring",
                "frequency": recurrence_rule.get("frequency", "daily"),
                "cron_expression": expression,
                "executed_at": now_utc.isoformat(),
                "scheduled_for": scheduled_for.isoformat(),
                "flow_type": flow.flow_type,
            }
        except Exception as e:
            logger.error(f"Error checking cron recurring flow #{flow.id}: {e}", exc_info=True)
            return False, {}

    async def _execute_flow_async(self, flow: FlowDefinition, trigger_context: dict):
        """
        Execute flow asynchronously.
        """
        try:
            # Execute via FlowEngine
            flow_run = await self.flow_engine.run_flow(
                flow_definition_id=flow.id,
                trigger_context=trigger_context,
                initiator="scheduler"
            )

            if flow_run.status == "completed":
                logger.info(f"✅ Flow #{flow.id} completed successfully (run #{flow_run.id})")

                # For one-time scheduled flows (agentic notifications), deactivate after execution
                if flow.initiator_type == "agentic" and flow.flow_type in ["notification", "conversation"]:
                    flow.is_active = False
                    self.db.commit()
                    logger.info(f"Deactivated one-time agentic flow #{flow.id}")

            else:
                logger.error(f"❌ Flow #{flow.id} failed (run #{flow_run.id}): {flow_run.error_text}")

        except Exception as e:
            logger.error(f"Error executing flow #{flow.id}: {e}", exc_info=True)


async def start_scheduled_flow_executor(db: Session):
    """
    Start the scheduled flow executor as a background task.

    Usage:
        asyncio.create_task(start_scheduled_flow_executor(db))
    """
    executor = ScheduledFlowExecutor(db, poll_interval_seconds=10)
    await executor.start()


# Global executor instance (singleton pattern)
_executor_instance = None
_executor_task = None


def get_scheduled_flow_executor(db: Session, poll_interval_seconds: int = 10):
    """
    Get or create the global scheduled flow executor instance.

    Args:
        db: Database session
        poll_interval_seconds: Polling interval (only used on first creation)

    Returns:
        ScheduledFlowExecutor instance
    """
    global _executor_instance

    if _executor_instance is None:
        _executor_instance = ScheduledFlowExecutor(db, poll_interval_seconds)

    return _executor_instance


def start_flow_executor(db: Session, poll_interval_seconds: int = 10):
    """
    Start the global scheduled flow executor as an asyncio task.
    Returns the asyncio task handle.
    """
    global _executor_task

    try:
        executor = get_scheduled_flow_executor(db, poll_interval_seconds)
        logger.info(f"Creating asyncio task for ScheduledFlowExecutor...")
        _executor_task = asyncio.create_task(executor.start())
        logger.info(f"Asyncio task created: {_executor_task}")
        return _executor_task
    except Exception as e:
        logger.error(f"Failed to start flow executor: {e}", exc_info=True)
        raise


def stop_flow_executor():
    """Stop the global scheduled flow executor."""
    global _executor_instance, _executor_task

    if _executor_instance:
        _executor_instance.stop()

    if _executor_task:
        _executor_task.cancel()
