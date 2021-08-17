# flink-ai-flow issue:475

https://github.com/alibaba/flink-ai-extended/issues/475

This directory helps to create test environment for testing the bug fix.

## How to run

### Prequisuite

Need `docker` & `docker compose` installed to run.

### Step 1. Build all need images

```bash
./aiflow-flink-hive/scripts/build_images.sh
```

### Step 2. Setup test cluster using docker compose

```bash
./aiflow-flink-hive/scripts/deploy.sh
```

### Step 3. docker login to container

```bash
docker exec -it flink-ai-flow-dev bash 
```

### Step 4. (in container) start ai-flow cluster in container

```bash
start-all-aiflow-services.sh $AIFLOW_MYSQL_CONNECTION
```

### Step 5. (in container) run workflow

```bash
cd /workspace/ai_flow_plugins/tests/issue_475/issue_project/workflows/issue_workflow/
python issue_workflow.py
```
### Step 6. check workflow exection in airflow

access localhost:8080 and check workflow `issue_project.issue_workflow`

### Step final. clear test cluster using docker compose

```bash
./aiflow-flink-hive/scripts/undeploy.sh
```