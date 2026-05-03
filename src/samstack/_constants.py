"""Internal constants shared across samstack fixtures."""

# LocalStack accepts any non-empty value for AWS credentials.
# "test" is its documented default and is not configurable.
LOCALSTACK_ACCESS_KEY = "test"
LOCALSTACK_SECRET_KEY = "test"

# Internal URL Lambda containers use to reach LocalStack on the shared
# Docker network. The hostname ``localstack`` is the network alias attached
# in fixtures/localstack.py; port 4566 is LocalStack's edge port.
LOCALSTACK_INTERNAL_URL = "http://localstack:4566"
