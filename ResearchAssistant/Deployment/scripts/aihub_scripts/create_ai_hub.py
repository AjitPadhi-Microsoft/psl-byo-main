from azure.ai.ml import MLClient
from azure.ai.ml.entities import (
    Project,
    ApiKeyConfiguration,
    AzureAISearchConnection,
    AzureOpenAIConnection,
    Workspace,
    IdentityConfiguration
)
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_secrets_from_kv(kv_name, secret_name):
    # Create a secret client object using the credential and Key Vault name
    secret_client = SecretClient(
        vault_url=f"https://{kv_name}.vault.azure.net/",
        credential=DefaultAzureCredential()
    )

    # Retrieve the secret value
    return secret_client.get_secret(secret_name).value

try:
    # Azure configuration
    key_vault_name = "kv_to-be-replaced"
    subscription_id = "subscription_to-be-replaced"
    resource_group_name = "rg_to-be-replaced"
    aihub_name = "ai_hub_" + "solutionname_to-be-replaced"
    project_name = "ai_project_" + "solutionname_to-be-replaced"
    deployment_name = "draftsinference-" + "solutionname_to-be-replaced"
    solutionLocation = "solutionlocation_to-be-replaced"

    # Open AI Details
    open_ai_key = get_secrets_from_kv(key_vault_name, "AZURE-OPENAI-KEY")
    open_ai_res_name = (
        get_secrets_from_kv(key_vault_name, "AZURE-OPENAI-ENDPOINT")
        .replace("https://", "")
        .replace(".openai.azure.com", "")
        .replace("/", "")
    )
    openai_api_version = get_secrets_from_kv(
        key_vault_name, "AZURE-OPENAI-PREVIEW-API-VERSION"
    )

    # Azure Search Details
    ai_search_endpoint = get_secrets_from_kv(key_vault_name, "AZURE-SEARCH-ENDPOINT")
    ai_search_res_name = (
        get_secrets_from_kv(key_vault_name, "AZURE-SEARCH-ENDPOINT")
        .replace("https://", "")
        .replace(".search.windows.net", "")
        .replace("/", "")
    )
    ai_search_key = get_secrets_from_kv(key_vault_name, "AZURE-SEARCH-KEY")

    # Initialize the MLClient
    ml_client = MLClient(DefaultAzureCredential(), subscription_id, resource_group_name)

    # Define the workspace configuration with identity-based authentication
    identity_config = IdentityConfiguration(type="SystemAssigned")

    my_hub = Workspace(
        name=aihub_name,
        location=solutionLocation,
        display_name=aihub_name,
        identity=identity_config,
    )

    created_hub = ml_client.workspaces.begin_create(my_hub).result()

    # Construct the project
    my_project = Project(
        name=project_name,
        location=solutionLocation,
        display_name=project_name,
        hub_id=created_hub.id,
    )

    created_project = ml_client.workspaces.begin_create(workspace=my_project).result()

    # Ensure all necessary attributes are set for AzureOpenAIConnection
    open_ai_connection = AzureOpenAIConnection(
        name="Azure_OpenAI",
        api_key=open_ai_key,
        api_version=openai_api_version,
        azure_endpoint=f"https://{open_ai_res_name}.openai.azure.com/",
        open_ai_resource_id=f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.CognitiveServices/accounts/{open_ai_res_name}",
    )

    # Log the attributes to ensure they are set correctly
    logger.info(f"OpenAI Connection Name: {open_ai_connection.name}")
    logger.info(f"OpenAI API Key: {open_ai_connection.api_key}")
    logger.info(f"OpenAI API Version: {open_ai_connection.api_version}")
    logger.info(f"OpenAI Azure Endpoint: {open_ai_connection.azure_endpoint}")
    logger.info(f"OpenAI Resource ID: {open_ai_connection.open_ai_resource_id}")

    # Check if all required attributes are set
    if not open_ai_connection.name or not open_ai_connection.api_key or not open_ai_connection.api_version or not open_ai_connection.azure_endpoint or not open_ai_connection.open_ai_resource_id:
        raise ValueError("One or more required attributes for AzureOpenAIConnection are missing")

    ml_client.connections.create_or_update(open_ai_connection)

    target = f"https://{ai_search_res_name}.search.windows.net/"

    # Create AI Search resource
    aisearch_connection = AzureAISearchConnection(
        name="Azure_AISearch",
        endpoint=target,
        credentials=ApiKeyConfiguration(key=ai_search_key),
    )

    aisearch_connection.tags["ResourceId"] = (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Search/searchServices/{ai_search_res_name}"
    )
    aisearch_connection.tags["ApiVersion"] = "2024-05-01-preview"

    ml_client.connections.create_or_update(aisearch_connection)

except Exception as e:
    logger.error(f"An error occurred: {e}")
    raise