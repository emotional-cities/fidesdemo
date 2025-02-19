"""
Utility script to configure fidesops with:
1. A `client` for OAuth authentication and executing API calls
2. A `connection` to the Flaskr PostgreSQL database
2. A `dataset` that annotates the Flaskr schema
3. A `policy` to fetch all user identifiable data
4. A `storage` to upload results to
"""
import json
import logging
import secrets
import sys
import time
from datetime import datetime
from os.path import exists

import requests
import yaml

logger = logging.getLogger(__name__)


def get_access_token(client_id, client_secret):
    """
    Authorize with fidesops via OAuth.

    Returns a valid access token if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/OAuth/acquire_access_token_api_v1_oauth_token_post
    """
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    response = requests.post(f"{FIDESOPS_URL}/api/v1/oauth/token", data=data)

    if response.ok:
        access_token = (response.json())["access_token"]
        if access_token:
            logger.info("Completed fidesops oauth login via /api/v1/oauth/token")
            return access_token

    raise RuntimeError(
        f"fidesops oauth login failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def oauth_headers(access_token):
    """Return valid authorization headers given the provided OAuth access token"""
    return {"Authorization": f"Bearer {access_token}"}


def create_oauth_client(access_token):
    """
    Create a new OAuth client in fidesops.

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/OAuth/acquire_access_token_api_v1_oauth_token_post
    """
    scopes_data = [
        "client:create",
        "client:update",
        "client:read",
        "client:delete",
        "policy:create_or_update",
        "policy:read",
        "policy:delete",
        "connection:create_or_update",
        "connection:read",
        "connection:delete",
        "privacy-request:create",
        "privacy-request:read",
        "privacy-request:delete",
        "rule:create_or_update",
        "rule:read",
        "rule:delete",
        "storage:create_or_update",
        "storage:read",
        "storage:delete",
        "dataset:create_or_update",
        "dataset:read",
        "dataset:delete",
    ]
    response = requests.post(
        f"{FIDESOPS_URL}/api/v1/oauth/client",
        headers=oauth_headers(access_token),
        json=scopes_data,
    )

    if response.ok:
        client = response.json()
        if client["client_id"] and client["client_secret"]:
            logger.info("Created fidesops oauth client via /api/v1/oauth/client")
            return client

    raise RuntimeError(
        f"fidesops oauth client creation failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def create_postgres_connection(key, access_token):
    """
    Create a connection in fidesops for our PostgreSQL database

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/Connections/put_connections_api_v1_connection_put
    """
    connection_create_data = [
        {
            "name": key,
            "key": key,
            "connection_type": "postgres",
            "access": "write",
        },
    ]
    response = requests.put(
        f"{FIDESOPS_URL}/api/v1/connection",
        headers=oauth_headers(access_token=access_token),
        json=connection_create_data,
    )

    if response.ok:
        connections = (response.json())["succeeded"]
        if len(connections) > 0:
            logger.info(
                f"Created fidesops connection with key={key} via /api/v1/connection"
            )
            return response.json()

    raise RuntimeError(
        f"fidesops connection creation failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def configure_postgres_connection(
    key, host, port, dbname, username, password, access_token
):
    """
    Configure the connection with the given `key` in fidesops with our PostgreSQL database credentials.

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/Connections/put_connection_config_secrets_api_v1_connection__connection_key__secret_put
    """
    connection_secrets_data = {
        "host": host,
        "port": port,
        "dbname": dbname,
        "username": username,
        "password": password,
    }
    response = requests.put(
        f"{FIDESOPS_URL}/api/v1/connection/{key}/secret",
        headers=oauth_headers(access_token=access_token),
        json=connection_secrets_data,
    )

    if response.ok:
        if (response.json())["test_status"] != "failed":
            logger.info(
                f"Configured fidesops connection secrets via /api/v1/connection/{key}/secret"
            )
            return response.json()

    raise RuntimeError(
        f"fidesops connection configuration failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def validate_dataset(connection_key, yaml_path, access_token):
    """
    Validate a dataset in fidesops given a YAML manifest file.

    Requires the `connection_key` for the PostgreSQL connection, and `yaml_path`
    that is a local filepath to a .yml dataset Fides manifest file.

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/Datasets/validate_dataset_api_v1_connection__connection_key__validate_dataset_put
    """

    with open(yaml_path, "r") as file:
        dataset = yaml.safe_load(file).get("dataset", [])[0]

    validate_dataset_data = dataset
    response = requests.put(
        f"{FIDESOPS_URL}/api/v1/connection/{connection_key}/validate_dataset",
        headers=oauth_headers(access_token=access_token),
        json=validate_dataset_data,
    )

    if response.ok:
        traversal_details = (response.json())["traversal_details"]
        if traversal_details["is_traversable"]:
            logger.info(
                f"Validated fidesops dataset via /api/v1/connection/{connection_key}/dataset"
            )
            return response.json()
        else:
            raise RuntimeError(
                f"fidesops dataset is not traversable! traversal_details={traversal_details}"
            )

    raise RuntimeError(
        f"fidesops dataset creation failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def create_dataset(connection_key, yaml_path, access_token):
    """
    Create a dataset in fidesops given a YAML manifest file.

    Requires the `connection_key` for the PostgreSQL connection, and `yaml_path`
    that is a local filepath to a .yml dataset Fides manifest file.

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/Datasets/put_datasets_api_v1_connection__connection_key__dataset_put
    """

    with open(yaml_path, "r") as file:
        dataset = yaml.safe_load(file).get("dataset", [])[0]

    dataset_create_data = [dataset]
    response = requests.put(
        f"{FIDESOPS_URL}/api/v1/connection/{connection_key}/dataset",
        headers=oauth_headers(access_token=access_token),
        json=dataset_create_data,
    )

    if response.ok:
        datasets = (response.json())["succeeded"]
        if len(datasets) > 0:
            logger.info(
                f"Created fidesops dataset via /api/v1/connection/{connection_key}/dataset"
            )
            return response.json()

    raise RuntimeError(
        f"fidesops dataset creation failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def create_local_storage(key, format, access_token):
    """
    Create a storage config in fidesops to write to a local file.

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/Storage/put_config_api_v1_storage_config_put
    """
    storage_create_data = [
        {
            "name": key,
            "key": key,
            "type": "local",
            "format": format,
            "details": {
                "naming": "request_id",
            },
        },
    ]
    response = requests.put(
        f"{FIDESOPS_URL}/api/v1/storage/config",
        headers=oauth_headers(access_token=access_token),
        json=storage_create_data,
    )

    if response.ok:
        storage = (response.json())["succeeded"]
        if len(storage) > 0:
            logger.info(
                f"Created fidesops storage with key={key} via /api/v1/storage/config"
            )
            return response.json()

    raise RuntimeError(
        f"fidesops storage creation failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def create_policy(key, access_token):
    """
    Create a request policy in fidesops with the given key.

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/Policy/create_or_update_policies_api_v1_policy_put
    """

    policy_create_data = [
        {
            "name": key,
            "key": key,
        },
    ]
    response = requests.put(
        f"{FIDESOPS_URL}/api/v1/policy",
        headers=oauth_headers(access_token=access_token),
        json=policy_create_data,
    )

    if response.ok:
        policies = (response.json())["succeeded"]
        if len(policies) > 0:
            logger.info(f"Created fidesops policy with key={key} via /api/v1/policy")
            return response.json()

    raise RuntimeError(
        f"fidesops policy creation failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def delete_policy_rule(policy_key, key, access_token):
    """
    Deletes a policy rule with the given key.

    Returns the response JSON.

    See http://localhost:8000/docs#/Policy/delete_rule_api_v1_policy__policy_key__rule__rule_key__delete
    """
    return requests.delete(
        f"{FIDESOPS_URL}/api/v1/policy/{policy_key}/rule/{key}",
        headers=oauth_headers(access_token=access_token),
    )


def create_policy_rule(
    policy_key, key, action_type, storage_destination_key, access_token
):
    """
    Create a policy rule to return matched data in an access request to the given storage destination.

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/Policy/create_or_update_rules_api_v1_policy__policy_key__rule_put
    """

    rule_create_data = [
        {
            "name": key,
            "key": key,
            "action_type": action_type,
            "storage_destination_key": storage_destination_key,
        },
    ]
    response = requests.put(
        f"{FIDESOPS_URL}/api/v1/policy/{policy_key}/rule",
        headers=oauth_headers(access_token=access_token),
        json=rule_create_data,
    )

    if response.ok:
        rules = (response.json())["succeeded"]
        if len(rules) > 0:
            logger.info(
                f"Created fidesops policy rule via /api/v1/policy/{policy_key}/rule"
            )
            return response.json()

    raise RuntimeError(
        f"fidesops policy rule creation failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def create_policy_rule_target(policy_key, rule_key, data_category, access_token):
    """
    Create a policy rule target that matches the given data_category.

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/Policy/create_or_update_rule_targets_api_v1_policy__policy_key__rule__rule_key__target_put
    """

    target_create_data = [
        {
            "data_category": data_category,
        },
    ]
    response = requests.put(
        f"{FIDESOPS_URL}/api/v1/policy/{policy_key}/rule/{rule_key}/target",
        headers=oauth_headers(access_token=access_token),
        json=target_create_data,
    )

    if response.ok:
        targets = (response.json())["succeeded"]
        if len(targets) > 0:
            logger.info(
                f"Created fidesops policy rule target for '{data_category}' via /api/v1/policy/{policy_key}/rule/{rule_key}/target"
            )
            return response.json()

    raise RuntimeError(
        f"fidesops policy rule target creation failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def create_privacy_request(email, policy_key, access_token):
    """
    Create a privacy request that is executed against the given request policy.

    Returns the response JSON if successful, or throws an error otherwise.

    See http://localhost:8000/docs#/Privacy%20Requests/create_privacy_request_api_v1_privacy_request_post
    """

    privacy_request_data = [
        {
            "requested_at": str(datetime.utcnow()),
            "policy_key": policy_key,
            "identities": [{"email": email}],
        },
    ]
    response = requests.post(
        f"{FIDESOPS_URL}/api/v1/privacy-request",
        headers=oauth_headers(access_token=access_token),
        json=privacy_request_data,
    )

    if response.ok:
        privacy_requests = (response.json())["succeeded"]
        if len(privacy_requests) > 0:
            logger.info(
                f"Created fidesops privacy request for email={email} via /api/v1/privacy-request"
            )
            return response.json()

    raise RuntimeError(
        f"fidesops privacy request creation failed! response.status_code={response.status_code}, response.json()={response.json()}"
    )


def print_results(privacy_request_id):
    """
    Check to see if a result JSON for the given privacy request exists, and
    print it to the console if so.
    """
    results_path = f"fides_uploads/{privacy_request_id}.json"
    if exists(results_path):
        logger.info(
            f"Successfully read fidesops privacy request results from {results_path}:"
        )
        with open(f"fides_uploads/{privacy_request_id}.json", "r") as file:
            results_json = json.loads(file.read())
            print(json.dumps(results_json, indent=4))
    else:
        raise RuntimeError(
            f"fidesops privacy request results not found at results_path={results_path}"
        )


if __name__ == "__main__":
    # If --test is provided, enable a flag to provide more detailed output
    test_mode = False
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_mode = True

    # NOTE: In a real application, these secrets and config values would be provided
    # via ENV vars or similar, but we've inlined everything here for simplicity
    FIDESOPS_URL = "http://localhost:8000"
    ROOT_CLIENT_ID = "fidesopsadmin"
    ROOT_CLIENT_SECRET = "fidesopsadminsecret"
    POSTGRES_SERVER = "db"
    POSTGRES_USER = "postgres"
    POSTGRES_PASSWORD = "postgres"
    POSTGRES_PORT = "5432"

    if test_mode:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARN)

    print("Setting up fideops environment with the following configuration:")
    print(f"  FIDESOPS_URL = {FIDESOPS_URL}")
    print(f"  ROOT_CLIENT_ID = {ROOT_CLIENT_ID}")
    print(f"  ROOT_CLIENT_SECRET = {ROOT_CLIENT_SECRET}")
    print(f"  POSTGRES_SERVER = {POSTGRES_SERVER}")
    print(f"  POSTGRES_USER = {POSTGRES_USER}")
    print(f"  POSTGRES_PASSWORD = {POSTGRES_PASSWORD}")
    print(f"  POSTGRES_PORT = {POSTGRES_PORT}")

    # Create a new OAuth client to use for our app
    if test_mode:
        print("Press [enter] to continue...")
        input()

    # Ensure fidesops is ready for requests
    print("Waiting for fidesops to be healthy...")
    while True:
        try:
            requests.get(f"{FIDESOPS_URL}/health")
            break
        except requests.ConnectionError:
            time.sleep(1)

    root_token = get_access_token(
        client_id=ROOT_CLIENT_ID, client_secret=ROOT_CLIENT_SECRET
    )
    client = create_oauth_client(access_token=root_token)
    access_token = get_access_token(
        client_id=client["client_id"], client_secret=client["client_secret"]
    )

    # Connect to our PostgreSQL database
    if test_mode:
        print("Press [enter] to continue...")
        input()

    create_postgres_connection(key="flaskr_postgres", access_token=access_token)
    configure_postgres_connection(
        key="flaskr_postgres",
        host=POSTGRES_SERVER,
        port=POSTGRES_PORT,
        dbname="flaskr",
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        access_token=access_token,
    )

    # Configure a storage config to upload the results
    if test_mode:
        print("Press [enter] to continue...")
        input()

    create_local_storage(
        key="example_storage",
        format="json",
        access_token=access_token,
    )

    while True:
        # Upload the dataset YAML for our PostgreSQL schema
        if test_mode:
            print("Press [enter] to continue...")
            input()

        validate_dataset(
            connection_key="flaskr_postgres",
            yaml_path="fides_resources/flaskr_postgres_dataset.yml",
            access_token=access_token,
        )
        datasets = create_dataset(
            connection_key="flaskr_postgres",
            yaml_path="fides_resources/flaskr_postgres_dataset.yml",
            access_token=access_token,
        )

        # Create a policy that returns all user data
        print(
            "\n\nEnter a list of target data categories for request policy "
            "[user]"
        )
        data_categories = [
            e.strip()
            for e in str(
                input() or "user"
            ).split(",")
        ]
        create_policy(
            key="example_request_policy",
            access_token=access_token,
        )
        # Delete any existing policy rule so we can reconfigure it based on input
        delete_policy_rule(
            policy_key="example_request_policy",
            key="access_user_data",
            access_token=access_token,
        )
        create_policy_rule(
            policy_key="example_request_policy",
            key="access_user_data",
            action_type="access",
            storage_destination_key="example_storage",
            access_token=access_token,
        )
        for data_category in data_categories:
            create_policy_rule_target(
                policy_key="example_request_policy",
                rule_key="access_user_data",
                data_category=data_category,
                access_token=access_token,
            )

        # Execute a privacy request for user@example.com
        print(
            "\n\nEnter an email address to create a privacy request [user@example.com]:"
        )
        email = str(input() or "user@example.com")
        privacy_requests = create_privacy_request(
            email=email,
            policy_key="example_request_policy",
            access_token=access_token,
        )
        privacy_request_id = privacy_requests["succeeded"][0]["id"]
        print_results(privacy_request_id=privacy_request_id)

        print("Complete! Press [y] to execute another request (or any key to quit)")
        should_continue = input() == "y"
        if not should_continue:
            exit(0)
