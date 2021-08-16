# issue: When using FlinkPythonProcessor, not calling execution_context.statement_set.add_insert_sql will lead to error, and missing job_id

## Issue 

### Describe the bug

当前实现下（https://github.com/alibaba/flink-ai-extended/commit/9dd9c6f312c21ae1334727e6cc334b958f2e4e54），使用FlinkPythonProcessor时，ai_flow_plugins/job_plugins/flink/flink_run_main.py#L75的实现会强制用户调用execution_context.statement_set.add_insert_sql，否则会报错。

如果FlinkPythonProcessor的process方法里只有execution_context.table_env.execute_sql而没有execution_context.statement_set.add_insert_sql的话，上面的行会报错
py4j.protocol.Py4JJavaError: An error occurred while calling o24.execute.
: java.lang.IllegalStateException: No operators defined in streaming topology. Cannot generate StreamGraph

另外，只调用execution_context.table_env.execute_sql的情况下，执行目录下的./job_id文件不会记录由execution_context.table_env.execute_sql触发的flink job的id。

### Your environment
Operating system
PRETTY_NAME="Debian GNU/Linux 10 (buster)"
NAME="Debian GNU/Linux"
VERSION_ID="10"
VERSION="10 (buster)"
VERSION_CODENAME=buster
ID=debian
HOME_URL="https://www.debian.org/"
SUPPORT_URL="https://www.debian.org/support"
BUG_REPORT_URL="https://bugs.debian.org/"

Python version
3.8.10

### To Reproduce

Before running the workflow, you need to setup the cluster including:
- Flink standalone cluster, assuming the ai-flow cluster can access job-manager with host:port as flink-jobmanager:8081
- HDFS & hive cluster, assuming hive database name as "default", and hive_conf_dir="/opt/hive/conf"

Then run the workflow:

```bash
python examples/issue_project/workflows/issue_workflow/issue_workflow.py
```

## Error log

```bash
cat logs/gen_static_user_feature_to_hive_stdout.log 
Traceback (most recent call last):
  File "/home/vscode/.local/lib/python3.8/site-packages/ai_flow_plugins/job_plugins/flink/flink_run_main.py", line 85, in run_project
    flink_execute_func(run_graph=run_graph,
  File "/home/vscode/.local/lib/python3.8/site-packages/ai_flow_plugins/job_plugins/flink/flink_run_main.py", line 60, in flink_execute_func
    job_client = statement_set.execute().get_job_client()
  File "/opt/flink/opt/python/pyflink.zip/pyflink/table/statement_set.py", line 97, in execute
    return TableResult(self._j_statement_set.execute())
  File "/opt/flink/opt/python/py4j-0.10.8.1-src.zip/py4j/java_gateway.py", line 1285, in __call__
    return_value = get_return_value(
  File "/opt/flink/opt/python/pyflink.zip/pyflink/util/exceptions.py", line 146, in deco
    return f(*a, **kw)
  File "/opt/flink/opt/python/py4j-0.10.8.1-src.zip/py4j/protocol.py", line 326, in get_return_value
    raise Py4JJavaError(
py4j.protocol.Py4JJavaError: An error occurred while calling o24.execute.
: java.lang.IllegalStateException: No operators defined in streaming topology. Cannot generate StreamGraph.
        at org.apache.flink.table.planner.utils.ExecutorUtils.generateStreamGraph(ExecutorUtils.java:40)
        at org.apache.flink.table.planner.delegation.StreamExecutor.createPipeline(StreamExecutor.java:50)
        at org.apache.flink.table.api.internal.TableEnvironmentImpl.executeInternal(TableEnvironmentImpl.java:757)
        at org.apache.flink.table.api.internal.TableEnvironmentImpl.executeInternal(TableEnvironmentImpl.java:742)
        at org.apache.flink.table.api.internal.StatementSetImpl.execute(StatementSetImpl.java:99)
        at sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)
        at sun.reflect.NativeMethodAccessorImpl.invoke(NativeMethodAccessorImpl.java:62)
        at sun.reflect.DelegatingMethodAccessorImpl.invoke(DelegatingMethodAccessorImpl.java:43)
        at java.lang.reflect.Method.invoke(Method.java:498)
        at org.apache.flink.api.python.shaded.py4j.reflection.MethodInvoker.invoke(MethodInvoker.java:244)
        at org.apache.flink.api.python.shaded.py4j.reflection.ReflectionEngine.invoke(ReflectionEngine.java:357)
        at org.apache.flink.api.python.shaded.py4j.Gateway.invoke(Gateway.java:282)
        at org.apache.flink.api.python.shaded.py4j.commands.AbstractCommand.invokeMethod(AbstractCommand.java:132)
        at org.apache.flink.api.python.shaded.py4j.commands.CallCommand.execute(CallCommand.java:79)
        at org.apache.flink.api.python.shaded.py4j.GatewayConnection.run(GatewayConnection.java:238)
        at java.lang.Thread.run(Thread.java:748)

Traceback (most recent call last):
  File "/home/vscode/.local/lib/python3.8/site-packages/ai_flow_plugins/job_plugins/flink/flink_run_main.py", line 85, in run_project
    flink_execute_func(run_graph=run_graph,
  File "/home/vscode/.local/lib/python3.8/site-packages/ai_flow_plugins/job_plugins/flink/flink_run_main.py", line 60, in flink_execute_func
    job_client = statement_set.execute().get_job_client()
  File "/opt/flink/opt/python/pyflink.zip/pyflink/table/statement_set.py", line 97, in execute
  File "/opt/flink/opt/python/py4j-0.10.8.1-src.zip/py4j/java_gateway.py", line 1285, in __call__
  File "/opt/flink/opt/python/pyflink.zip/pyflink/util/exceptions.py", line 146, in deco
  File "/opt/flink/opt/python/py4j-0.10.8.1-src.zip/py4j/protocol.py", line 326, in get_return_value
py4j.protocol.Py4JJavaError: An error occurred while calling o24.execute.
: java.lang.IllegalStateException: No operators defined in streaming topology. Cannot generate StreamGraph.
        at org.apache.flink.table.planner.utils.ExecutorUtils.generateStreamGraph(ExecutorUtils.java:40)
        at org.apache.flink.table.planner.delegation.StreamExecutor.createPipeline(StreamExecutor.java:50)
        at org.apache.flink.table.api.internal.TableEnvironmentImpl.executeInternal(TableEnvironmentImpl.java:757)
        at org.apache.flink.table.api.internal.TableEnvironmentImpl.executeInternal(TableEnvironmentImpl.java:742)
        at org.apache.flink.table.api.internal.StatementSetImpl.execute(StatementSetImpl.java:99)
        at sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)
        at sun.reflect.NativeMethodAccessorImpl.invoke(NativeMethodAccessorImpl.java:62)
        at sun.reflect.DelegatingMethodAccessorImpl.invoke(DelegatingMethodAccessorImpl.java:43)
        at java.lang.reflect.Method.invoke(Method.java:498)
        at org.apache.flink.api.python.shaded.py4j.reflection.MethodInvoker.invoke(MethodInvoker.java:244)
        at org.apache.flink.api.python.shaded.py4j.reflection.ReflectionEngine.invoke(ReflectionEngine.java:357)
        at org.apache.flink.api.python.shaded.py4j.Gateway.invoke(Gateway.java:282)
        at org.apache.flink.api.python.shaded.py4j.commands.AbstractCommand.invokeMethod(AbstractCommand.java:132)
        at org.apache.flink.api.python.shaded.py4j.commands.CallCommand.execute(CallCommand.java:79)
        at org.apache.flink.api.python.shaded.py4j.GatewayConnection.run(GatewayConnection.java:238)
        at java.lang.Thread.run(Thread.java:748)


During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/home/vscode/.local/lib/python3.8/site-packages/ai_flow_plugins/job_plugins/flink/flink_run_main.py", line 97, in <module>
    run_project(l_graph_file, l_working_dir, l_flink_file)
  File "/home/vscode/.local/lib/python3.8/site-packages/ai_flow_plugins/job_plugins/flink/flink_run_main.py", line 91, in run_project
    raise Exception(str(e))
Exception: An error occurred while calling o24.execute.
: java.lang.IllegalStateException: No operators defined in streaming topology. Cannot generate StreamGraph.
        at org.apache.flink.table.planner.utils.ExecutorUtils.generateStreamGraph(ExecutorUtils.java:40)
        at org.apache.flink.table.planner.delegation.StreamExecutor.createPipeline(StreamExecutor.java:50)
        at org.apache.flink.table.api.internal.TableEnvironmentImpl.executeInternal(TableEnvironmentImpl.java:757)
        at org.apache.flink.table.api.internal.TableEnvironmentImpl.executeInternal(TableEnvironmentImpl.java:742)
        at org.apache.flink.table.api.internal.StatementSetImpl.execute(StatementSetImpl.java:99)
        at sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)
        at sun.reflect.NativeMethodAccessorImpl.invoke(NativeMethodAccessorImpl.java:62)
        at sun.reflect.DelegatingMethodAccessorImpl.invoke(DelegatingMethodAccessorImpl.java:43)
        at java.lang.reflect.Method.invoke(Method.java:498)
        at org.apache.flink.api.python.shaded.py4j.reflection.MethodInvoker.invoke(MethodInvoker.java:244)
        at org.apache.flink.api.python.shaded.py4j.reflection.ReflectionEngine.invoke(ReflectionEngine.java:357)
        at org.apache.flink.api.python.shaded.py4j.Gateway.invoke(Gateway.java:282)
        at org.apache.flink.api.python.shaded.py4j.commands.AbstractCommand.invokeMethod(AbstractCommand.java:132)
        at org.apache.flink.api.python.shaded.py4j.commands.CallCommand.execute(CallCommand.java:79)
        at org.apache.flink.api.python.shaded.py4j.GatewayConnection.run(GatewayConnection.java:238)
        at java.lang.Thread.run(Thread.java:748)
```