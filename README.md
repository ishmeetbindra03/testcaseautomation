

### Prerequisities
- gcloud

### Setup
1. Create an .venv
```
uv venv .venv 
```

or 

```
python3 -m venv .venv
```

2. Activate the environment
```
source .venv/bin/activate
```

pip install -r requirements.txt



gcloud auth login
gcloud auth application-default login

gcloud config set project <project_id>
gcloud auth application-default set-quota-project <project_id>


### Scripts

 python test_runner.py --input_csv <input> --results_dir <directory> --project_id <project_id> --region <region> --app_id  <cxas app id> --modality <text | voice> --max_parallel_worker



### Deployment to Agent Engine
```
adk deploy agent_engine --project=<project_id> --region=<region> --display_name="qa_agent_worker" --agent_engine_id=<optional if it's already deployed> qa_agent_worker
```

