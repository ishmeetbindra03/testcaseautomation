

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



### Deployment to Agent Engine

```
adk deploy agent_engine --project=<project_id> --region=<region> --display_name="qa_agent_worker" --agent_engine_id=<optional if it's already deployed> qa_agent_worker
```


#### 1. Running QA Tests & Automatically Generating the Report (Default)
To execute the QA tests and **automatically generate** the interactive HTML report immediately afterwards in a single step, run:
```bash
python run_qa_tests.py \
  --input_file inputfile/input.csv \
  --output_result outputfile/results.jsonl \
  --project_id <YOUR_GCP_PROJECT_ID> \
  --app_id <YOUR_DIALOGFLOW_CX_APP_ID> \
  --region_id <YOUR_GCP_REGION_ID>
```
*Note: If you have set the `GCP_PROJECT_ID`, `GCP_APP_ID`, and `GCP_REGION_ID` environment variables in your terminal, you can omit those command-line flags.*

*By default, the report will be saved at `outputfile/report.html`.*

To specify a custom output path for the HTML report:
```bash
python run_qa_tests.py \
  --input_file inputfile/input.csv \
  --output_result outputfile/results.jsonl \
  --project_id <YOUR_GCP_PROJECT_ID> \
  --app_id <YOUR_DIALOGFLOW_CX_APP_ID> \
  --report_html outputfile/custom_report.html
```

#### 2. Running QA Tests *Without* Generating a Report
If you only want to run the tests and save the raw JSONL results *without* generating the HTML report, pass the `--no_report` flag:
```bash
python run_qa_tests.py \
  --input_file inputfile/input.csv \
  --output_result outputfile/results.jsonl \
  --project_id <YOUR_GCP_PROJECT_ID> \
  --app_id <YOUR_DIALOGFLOW_CX_APP_ID> \
  --no_report
```

#### 3. Generating the HTML Report Separately
If you already have a results JSONL file (e.g. `outputfile/results.jsonl`) and want to regenerate the HTML report without re-running the tests, you can still run the standalone generator script:
```bash
python generate_html_report.py --results_file outputfile/results.jsonl --output_html outputfile/report.html
```

