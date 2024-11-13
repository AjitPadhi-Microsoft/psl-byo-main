from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient
from azure.ai.ml.entities import (
    Workspace,
    IdentityConfiguration,
    WorkspaceConnection,
    ManagedIdentityConfiguration,
)
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import StorageAccountCreateParameters, Sku, Kind
from azure.keyvault.secrets import SecretClient


# Function to get secrets from Azure Key Vault
def get_secrets_from_kv(kv_name, secret_name):
    credential = DefaultAzureCredential()
    secret_client = SecretClient(
        vault_url=f"https://{kv_name}.vault.azure.net/", credential=credential
    )
    return secret_client.get_secret(secret_name).value


# Azure configuration
key_vault_name = "kv_to-be-replaced"
subscription_id = "subscription_to-be-replaced"
resource_group_name = "rg_to-be-replaced"
aihub_name = "ai_hub_" + "solutionname_to-be-replaced"
project_name = "ai_project_" + "solutionname_to-be-replaced"
solutionLocation = "solutionlocation_to-be-replaced"
storage_account_name = "storageaihub" + "solutionname_to-be-replaced"

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
ai_search_api_version = "2024-05-01-preview"  # Example API version

# Credentials
credential = DefaultAzureCredential()

# Initialize clients
storage_client = StorageManagementClient(credential, subscription_id)
ml_client = MLClient(credential, subscription_id, resource_group_name)

# Create the storage account if it doesn't exist
storage_account_params = StorageAccountCreateParameters(
    sku=Sku(name="Standard_LRS"), kind=Kind.STORAGE_V2, location=solutionLocation
)
storage_account = storage_client.storage_accounts.begin_create(
    resource_group_name, storage_account_name, storage_account_params
).result()

# Assign managed identity to the storage account
storage_account = storage_client.storage_accounts.get_properties(
    resource_group_name, storage_account_name
)
storage_account.identity = {"type": "SystemAssigned"}
storage_client.storage_accounts.update(
    resource_group_name, storage_account_name, storage_account
)

# Define the AI hub with Managed Identity
my_hub = Workspace(
    name=aihub_name,
    location=solutionLocation,
    display_name=aihub_name,
    identity=IdentityConfiguration(type="SystemAssigned"),
)

# Create the AI hub
created_hub = ml_client.workspaces.begin_create(my_hub).result()

# Define the workspace connection using managed identity
open_ai_connection = WorkspaceConnection(
    name="Azure_OpenAI",
    type="AzureOpenAI",
    target=f"https://{open_ai_res_name}.openai.azure.com/",
    identity=IdentityConfiguration(type="SystemAssigned"),
    api_version=openai_api_version,
    credentials=ManagedIdentityConfiguration(),
    resource_id=f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.CognitiveServices/accounts/{open_ai_res_name}",
)

# Create or update the workspace connection
ml_client.connections.create_or_update(open_ai_connection)

# Define the AI Search connection using managed identity
ai_search_connection = WorkspaceConnection(
    name="Azure_AISearch",
    type="AzureSearch",
    target=f"https://{ai_search_res_name}.search.windows.net/",
    identity=IdentityConfiguration(type="SystemAssigned"),
    api_version=ai_search_api_version,
    credentials=ManagedIdentityConfiguration(),
    resource_id=f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Search/searchServices/{ai_search_res_name}",
)

# Create or update the AI Search connection
ml_client.connections.create_or_update(ai_search_connection)
