TIMESTAMP := $(shell date +%Y%m%d_%H_%M_%S)

zip:
	zip -r testcaseautomation_$(TIMESTAMP).zip . -x "*.git/*" -x "*.venv/*" -x "*__pycache__*" -x "*.zip" -x results