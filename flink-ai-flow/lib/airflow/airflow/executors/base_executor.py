# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Base executor - this is the base class for all the implemented executors."""
import sys
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set, Tuple

from airflow.events.scheduler_events import TaskStateChangedEvent
from sqlalchemy.orm import Session, selectinload

from airflow.configuration import conf
from airflow.executors.scheduling_action import SchedulingAction
from airflow.models.taskinstance import TaskInstance, TaskInstanceKey
from airflow.stats import Stats
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.utils.session import provide_session, create_session
from airflow.utils.state import State
from airflow.settings import CHECK_TASK_STOPPED_INTERVAL, CHECK_TASK_STOPPED_NUM

PARALLELISM: int = conf.getint('core', 'PARALLELISM')

NOT_STARTED_MESSAGE = "The executor should be started first!"

# Command to execute - list of strings
# the first element is always "airflow".
# It should be result of TaskInstance.generate_command method.q
CommandType = List[str]


# Task that is queued. It contains all the information that is
# needed to run the task.
#
# Tuple of: command, priority, queue name, TaskInstance
QueuedTaskInstanceType = Tuple[CommandType, int, Optional[str], TaskInstance]

# Event_buffer dict value type
# Tuple of: state, info
EventBufferValueType = Tuple[Optional[str], Any]


class BaseExecutor(LoggingMixin):
    """
    Class to derive in order to interface with executor-type systems
    like Celery, Kubernetes, Local, Sequential and the likes.

    :param parallelism: how many jobs should run at one time. Set to
        ``0`` for infinity
    """

    job_id: Optional[str] = None

    def __init__(self, parallelism: int = PARALLELISM):
        super().__init__()
        self.parallelism: int = parallelism
        self.queued_tasks: OrderedDict[TaskInstanceKey, QueuedTaskInstanceType] = OrderedDict()
        self.running: Set[TaskInstanceKey] = set()
        self.event_buffer: Dict[TaskInstanceKey, EventBufferValueType] = {}
        self._mailbox = None
        self._server_uri = None

    def set_mailbox(self, mailbox):
        self._mailbox = mailbox

    def set_server_uri(self, server_uri):
        self._server_uri = server_uri

    def start(self):  # pragma: no cover
        """Executors may need to get things started."""

    def queue_command(
        self,
        task_instance: TaskInstance,
        command: CommandType,
        priority: int = 1,
        queue: Optional[str] = None,
    ):
        """Queues command to task"""
        if task_instance.key not in self.queued_tasks and task_instance.key not in self.running:
            self.log.info("Adding to queue: %s", command)
            self.queued_tasks[task_instance.key] = (command, priority, queue, task_instance)
        else:
            self.log.error("could not queue task %s", task_instance.key)

    def queue_task_instance(
        self,
        task_instance: TaskInstance,
        mark_success: bool = False,
        pickle_id: Optional[str] = None,
        ignore_all_deps: bool = False,
        ignore_depends_on_past: bool = False,
        ignore_task_deps: bool = False,
        ignore_ti_state: bool = False,
        pool: Optional[str] = None,
        cfg_path: Optional[str] = None,
    ) -> None:
        """Queues task instance."""
        pool = pool or task_instance.pool

        # TODO (edgarRd): AIRFLOW-1985:
        # cfg_path is needed to propagate the config values if using impersonation
        # (run_as_user), given that there are different code paths running tasks.
        # For a long term solution we need to address AIRFLOW-1986
        command_list_to_run = task_instance.command_as_list(
            local=True,
            mark_success=mark_success,
            ignore_all_deps=ignore_all_deps,
            ignore_depends_on_past=ignore_depends_on_past,
            ignore_task_deps=ignore_task_deps,
            ignore_ti_state=ignore_ti_state,
            pool=pool,
            pickle_id=pickle_id,
            cfg_path=cfg_path,
        )
        self.log.debug("created command %s", command_list_to_run)
        self.queue_command(
            task_instance,
            command_list_to_run,
            priority=task_instance.task.priority_weight_total,
            queue=task_instance.task.queue,
        )

    def schedule_task(self, key: TaskInstanceKey, action: SchedulingAction):
        """
        Schedule a task

        :param key: task instance key
        :param action: task scheduling action in [START, STOP, RESTART]
        """
        with create_session() as session:
            ti = session.query(TaskInstance).filter(
                TaskInstance.dag_id == key.dag_id,
                TaskInstance.task_id == key.task_id,
                TaskInstance.execution_date == key.execution_date
            ).first()
            if SchedulingAction.START == action:
                if ti.state not in State.running:
                    self._start_task_instance(key)
                    self._send_message(ti)
            elif SchedulingAction.STOP == action:
                if ti.state in State.unfinished:
                    if self._stop_task_instance(key):
                        self._send_message(ti)
            elif SchedulingAction.RESTART == action:
                if ti.state in State.running:
                    self._restart_task_instance(key)
                else:
                    self._start_task_instance(key)
                self._send_message(ti)
            else:
                raise ValueError('The task scheduling action must in ["START", "STOP", "RESTART"].')

    def _send_message(self, ti):
        self.send_message(TaskInstanceKey(ti.dag_id, ti.task_id, ti.execution_date, ti.try_number))

    def _start_task_instance(self, key: TaskInstanceKey):
        """
        Ignore all dependencies, force start a task instance
        """
        ti = self.get_task_instance(key)
        if ti is None:
            self.log.error("TaskInstance not found in DB, %s.", str(key))
            return
        command = TaskInstance.generate_command(
            ti.dag_id,
            ti.task_id,
            ti.execution_date,
            local=True,
            mark_success=False,
            ignore_all_deps=True,
            ignore_depends_on_past=True,
            ignore_task_deps=True,
            ignore_ti_state=True,
            pool=ti.pool,
            file_path=ti.dag_model.fileloc,
            pickle_id=ti.dag_model.pickle_id,
            server_uri=self._server_uri,
        )
        ti.set_state(State.QUEUED)
        self.execute_async(
            key=key,
            command=command,
            queue=ti.queue,
            executor_config=ti.executor_config
        )

    def _stop_related_process(self, ti: TaskInstance) -> bool:
        raise NotImplementedError()

    def _stop_task_instance(self, key: TaskInstanceKey) -> bool:
        """
        Force stopping a task instance.
        return: True if successfully kill the task instance
        """
        ti = self.get_task_instance(key)
        if ti is None:
            self.log.error("Task not found in DB, %s.", str(key))
            return False
        elif ti.state in State.finished:
            self.log.info("Task has been finished with state %s, %s", ti.state, str(key))
            return True
        elif ti.state != State.RUNNING:
            ti.set_state(State.KILLED)
            return True
        try:
            self.running.remove(ti.key)
        except KeyError:
            self.log.debug('Could not find key: %s', str(ti.key))
        ti.set_state(State.KILLING)
        self._stop_related_process(ti)
        stopped = self._wait_for_stopping_task(
            key=key,
            check_interval=CHECK_TASK_STOPPED_INTERVAL,
            max_check_num=CHECK_TASK_STOPPED_NUM)
        if not stopped:
            self.log.error("Failed to stop task instance: %s, please try again.", str(ti))
        return stopped

    def _restart_task_instance(self, key: TaskInstanceKey):
        """Force restarting a task instance"""
        if self._stop_task_instance(key):
            self._start_task_instance(key)

    def has_task(self, task_instance: TaskInstance) -> bool:
        """
        Checks if a task is either queued or running in this executor.

        :param task_instance: TaskInstance
        :return: True if the task is known to this executor
        """
        return task_instance.key in self.queued_tasks or task_instance.key in self.running

    def sync(self) -> None:
        """
        Sync will get called periodically by the heartbeat method.
        Executors should override this to perform gather statuses.
        """

    def heartbeat(self) -> None:
        """Heartbeat sent to trigger new jobs."""
        if not self.parallelism:
            open_slots = len(self.queued_tasks)
        else:
            open_slots = self.parallelism - len(self.running)

        num_running_tasks = len(self.running)
        num_queued_tasks = len(self.queued_tasks)

        self.log.debug("%s running task instances", num_running_tasks)
        self.log.debug("%s in queue", num_queued_tasks)
        self.log.debug("%s open slots", open_slots)

        Stats.gauge('executor.open_slots', open_slots)
        Stats.gauge('executor.queued_tasks', num_queued_tasks)
        Stats.gauge('executor.running_tasks', num_running_tasks)

        self.trigger_tasks(open_slots)

        # Calling child class sync method
        self.log.debug("Calling the %s sync method", self.__class__)
        self.sync()

    def order_queued_tasks_by_priority(self) -> List[Tuple[TaskInstanceKey, QueuedTaskInstanceType]]:
        """
        Orders the queued tasks by priority.

        :return: List of tuples from the queued_tasks according to the priority.
        """
        return sorted(
            [(k, v) for k, v in self.queued_tasks.items()],  # pylint: disable=unnecessary-comprehension
            key=lambda x: x[1][1],
            reverse=True,
        )

    def trigger_tasks(self, open_slots: int) -> None:
        """
        Triggers tasks

        :param open_slots: Number of open slots
        """
        sorted_queue = self.order_queued_tasks_by_priority()

        for _ in range(min((open_slots, len(self.queued_tasks)))):
            key, (command, _, _, ti) = sorted_queue.pop(0)
            self.queued_tasks.pop(key)
            self.running.add(key)
            self.execute_async(key=key, command=command, queue=None, executor_config=ti.executor_config)

    def change_state(self, key: TaskInstanceKey, state: str, info=None) -> None:
        """
        Changes state of the task.

        :param info: Executor information for the task instance
        :param key: Unique key for the task instance
        :param state: State to set for the task.
        """
        self.log.debug("Changing state: %s", key)
        try:
            self.running.remove(key)
        except KeyError:
            self.log.debug('Could not find key: %s', str(key))
        self.event_buffer[key] = state, info

    def fail(self, key: TaskInstanceKey, info=None) -> None:
        """
        Set fail state for the event.

        :param info: Executor information for the task instance
        :param key: Unique key for the task instance
        """
        self.change_state(key, State.FAILED, info)

    def success(self, key: TaskInstanceKey, info=None) -> None:
        """
        Set success state for the event.

        :param info: Executor information for the task instance
        :param key: Unique key for the task instance
        """
        self.change_state(key, State.SUCCESS, info)

    def get_event_buffer(self, dag_ids=None) -> Dict[TaskInstanceKey, EventBufferValueType]:
        """
        Returns and flush the event buffer. In case dag_ids is specified
        it will only return and flush events for the given dag_ids. Otherwise
        it returns and flushes all events.

        :param dag_ids: to dag_ids to return events for, if None returns all
        :return: a dict of events
        """
        cleared_events: Dict[TaskInstanceKey, EventBufferValueType] = {}
        if dag_ids is None:
            cleared_events = self.event_buffer
            self.event_buffer = {}
        else:
            for ti_key in list(self.event_buffer.keys()):
                if ti_key.dag_id in dag_ids:
                    cleared_events[ti_key] = self.event_buffer.pop(ti_key)

        return cleared_events

    def execute_async(
        self,
        key: TaskInstanceKey,
        command: CommandType,
        queue: Optional[str] = None,
        executor_config: Optional[Any] = None,
    ) -> None:  # pragma: no cover
        """
        This method will execute the command asynchronously.

        :param key: Unique key for the task instance
        :param command: Command to run
        :param queue: name of the queue
        :param executor_config: Configuration passed to the executor.
        """
        raise NotImplementedError()

    def end(self) -> None:  # pragma: no cover
        """
        This method is called when the caller is done submitting job and
        wants to wait synchronously for the job submitted previously to be
        all done.
        """
        raise NotImplementedError()

    def terminate(self):
        """This method is called when the daemon receives a SIGTERM"""
        raise NotImplementedError()

    def try_adopt_task_instances(self, tis: List[TaskInstance]) -> List[TaskInstance]:
        """
        Try to adopt running task instances that have been abandoned by a SchedulerJob dying.

        Anything that is not adopted will be cleared by the scheduler (and then become eligible for
        re-scheduling)

        :return: any TaskInstances that were unable to be adopted
        :rtype: list[airflow.models.TaskInstance]
        """
        # By default, assume Executors cannot adopt tasks, so just say we failed to adopt anything.
        # Subclasses can do better!
        return tis

    @property
    def slots_available(self):
        """Number of new tasks this executor instance can accept"""
        if self.parallelism:
            return self.parallelism - len(self.running) - len(self.queued_tasks)
        else:
            return sys.maxsize

    @staticmethod
    def validate_command(command: List[str]) -> None:
        """Check if the command to execute is airflow command"""
        if command[0:3] != ["airflow", "tasks", "run"]:
            raise ValueError('The command must start with ["airflow", "tasks", "run"].')

    def debug_dump(self):
        """Called in response to SIGUSR2 by the scheduler"""
        self.log.info(
            "executor.queued (%d)\n\t%s",
            len(self.queued_tasks),
            "\n\t".join(map(repr, self.queued_tasks.items())),
        )
        self.log.info("executor.running (%d)\n\t%s", len(self.running), "\n\t".join(map(repr, self.running)))
        self.log.info(
            "executor.event_buffer (%d)\n\t%s",
            len(self.event_buffer),
            "\n\t".join(map(repr, self.event_buffer.items())),
        )

    @provide_session
    def get_task_instance(self, key: TaskInstanceKey, session: Session = None) -> Optional[TaskInstance]:
        """
        Returns the task instance specified by TaskInstanceKey

        :param key: the task instance key
        :type key: TaskInstanceKey
        :param session: Sqlalchemy ORM Session
        :type session: Session
        """
        return (
            session.query(TaskInstance).filter(
                TaskInstance.dag_id == key.dag_id,
                TaskInstance.execution_date == key.execution_date,
                TaskInstance.task_id == key.task_id
            ).options(selectinload('dag_model')).first()
        )

    def send_message(self, key: TaskInstanceKey):
        if self._mailbox is not None:
            ti = self.get_task_instance(key)
            if ti is None:
                self.log.warning("Failed to find TaskInstance {} {} {} {}. It might be deleted manually."
                                 .format(key.dag_id, key.task_id, key.execution_date, key.try_number))
                return
            task_status_changed_event = TaskStateChangedEvent(
                ti.task_id,
                ti.dag_id,
                ti.execution_date,
                ti.state
            )
            self._mailbox.send_message(task_status_changed_event.to_event())

    def _wait_for_stopping_task(
        self,
        key: TaskInstanceKey,
        check_interval: int,
        max_check_num: int,
    ) -> bool:
        """
        Wait check_interval * max_check_num seconds for task to be killed successfully
        :param key: the task instance key
        :type key: TaskInstanceKey
        :param check_interval: interval between checking state
        :type check_interval: int
        :param max_check_num: max times of checking state
        :type max_check_num: int
        """
        check_num = 0
        while check_num < max_check_num and check_interval > 0:
            check_num = check_num + 1
            ti = self.get_task_instance(key)
            if ti and ti.state == State.KILLED:
                return True
            else:
                time.sleep(check_interval)
        return False

    def recover_state(self):
        """
        Recover the state of dags after restarting scheduler.
        """
        pass
