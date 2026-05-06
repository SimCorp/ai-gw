FROM python:3.12-slim

WORKDIR /tests

# Install test dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy test sources
COPY . /tests/

# pytest.ini lives in /tests/ and sets testpaths = . so pytest discovers
# all test_*.py files in the working directory.
# Override CMD to run a subset:
#   docker compose run --rm test-runner test_smoke.py
#   docker compose run --rm test-runner test_proxy.py test_cache.py
#   docker compose run --rm test-runner -k "not streaming"
ENTRYPOINT ["pytest"]
CMD ["-v", "--tb=short"]
