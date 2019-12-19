.SHELLFLAGS = -ec
DEFAULT_GOAL = help

ci-test:  ## Run CI oriented tests
	$(PWD)/tests/run_tests.sh

help:  ## Display this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[0;32m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: \
	ci-test \
	help
