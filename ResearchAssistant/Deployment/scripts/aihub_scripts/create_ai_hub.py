from azure.mgmt.machinelearningservices import MachineLearningServicesManagementClient
from azure.mgmt.machinelearningservices.models import Workspace
from azure.ai.ml.entities import (
    Project,
    ApiKeyConfiguration,
    AzureAISearchConnection,
    AzureOpenAIConnection,
)
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import StorageAccountCreateParameters, Sku, Kind


# Get Azure Key Vault Client
key_vault_name = "kv_to-be-replaced"


def get_secrets_from_kv(kv_name, secret_name):
    # Set the name of the Azure Key Vault
    key_vault_name = kv_name

    # Create a credential object using the default Azure credentials
    credential = DefaultAzureCredential()

    # Create a secret client object using the credential and Key Vault name
    secret_client = SecretClient(
        vault_url=f"https://{key_vault_name}.vault.azure.net/", credential=credential
    )

    # Retrieve the secret value
    return secret_client.get_secret(secret_name).value


# Azure configuration

key_vault_name = "kv_to-be-replaced"
subscription_id = "subscription_to-be-replaced"
resource_group_name = "rg_to-be-replaced"
aihub_name = "ai_hub_" + "solutionname_to-be-replaced"
project_name = "ai_project_" + "solutionname_to-be-replaced"
deployment_name = "draftsinference-" + "solutionname_to-be-replaced"
solutionLocation = "solutionlocation_to-be-replaced"
storage_account_name = "ai_project_" + "solutionname_to-be-replaced"

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

# Credentials
credential = DefaultAzureCredential()

# Initialize clients
storage_client = StorageManagementClient(credential, subscription_id)
ml_client = MachineLearningServicesManagementClient(credential, subscription_id)

# Create the storage account if it doesn't exist
storage_account_params = StorageAccountCreateParameters(
    sku=Sku(name="Standard_LRS"), kind=Kind.STORAGE_V2, location=solutionLocation
)
storage_account = storage_client.storage_accounts.begin_create(
    resource_group_name, storage_account_name, storage_account_params
).result()

# Define the AI hub
my_hub = Workspace(
    location=solutionLocation,
    display_name=aihub_name,
    identity={"type": "SystemAssigned"},
)

# Create the AI hub
created_hub = ml_client.workspaces.begin_create_or_update(
    resource_group_name, aihub_name, my_hub
).result()

# Assign managed identity to the storage account
storage_account = storage_client.storage_accounts.get_properties(
    resource_group_name, storage_account_name
)
storage_account.identity = {"type": "SystemAssigned"}
storage_client.storage_accounts.begin_create_or_update(
    resource_group_name, storage_account_name, storage_account
).result()

# construct the project
my_project = Project(
    name=project_name,
    location=solutionLocation,
    display_name=project_name,
    hub_id=created_hub.id,
)

created_project = ml_client.workspaces.begin_create(workspace=my_project).result()

open_ai_connection = AzureOpenAIConnection(
    name="Azure_OpenAI",
    api_key=open_ai_key,
    api_version=openai_api_version,
    azure_endpoint=f"https://{open_ai_res_name}.openai.azure.com/",
    open_ai_resource_id=f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.CognitiveServices/accounts/{open_ai_res_name}",
)

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
