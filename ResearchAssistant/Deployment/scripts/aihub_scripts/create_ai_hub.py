import uuid
from azure.ai.ml import MLClient
from azure.ai.ml.entities import (
    Hub,
    Project,
    ApiKeyConfiguration,
    AzureAISearchConnection,
    AzureOpenAIConnection,
    IdentityConfiguration,
)
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import (
    StorageAccountCreateParameters,
    Sku,
    Kind,
    Identity,
    IdentityType,
    StorageAccountUpdateParameters,
)
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.authorization.models import RoleAssignmentCreateParameters


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
storage_account_name = "storageaihub" + "solutionname_to-be-replaced"

# Create a credential object using the default Azure credentials
credential = DefaultAzureCredential()

# Create a Storage Management client
storage_client = StorageManagementClient(credential, subscription_id)

# Create the storage account with identity-based access
storage_async_operation = storage_client.storage_accounts.begin_create(
    resource_group_name,
    storage_account_name,
    StorageAccountCreateParameters(
        sku=Sku(name="Standard_LRS"),
        kind=Kind.STORAGE_V2,
        location=solutionLocation,
        identity=Identity(type=IdentityType.SYSTEM_ASSIGNED),
    ),
)
storage_account = storage_async_operation.result()

# Disable key-based access for the storage account
storage_client.storage_accounts.update(
    resource_group_name,
    storage_account_name,
    StorageAccountUpdateParameters(
        allow_blob_public_access=False, allow_shared_key_access=False
    ),
)

# Get the storage account resource ID
storage_account_resource_id = storage_account.id

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

# Create an ML client
ml_client = MLClient(
    workspace_name=aihub_name,
    resource_group_name=resource_group_name,
    subscription_id=subscription_id,
    credential=credential,
)

# Construct a hub with the existing storage account and managed identity
my_hub = Hub(
    name=aihub_name,
    location=solutionLocation,
    display_name=aihub_name,
    storage_account=storage_account_resource_id,
    identity=IdentityConfiguration(type="SystemAssigned"),
)

created_hub = ml_client.workspaces.begin_create(my_hub).result()

# Assign the managed identity of the hub access to the storage account
authorization_client = AuthorizationManagementClient(credential, subscription_id)
role_assignment_params = RoleAssignmentCreateParameters(
    role_definition_id=f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/b24988ac-6180-42a0-ab88-20f7382dd24c",  # Replace with the appropriate role ID
    principal_id=created_hub.identity.principal_id,
    principal_type="ServicePrincipal"
)
authorization_client.role_assignments.create(
    scope=storage_account_resource_id,
    role_assignment_name=str(uuid.uuid4()),
    parameters=role_assignment_params,
)

# Construct the project
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

# Create a BlobServiceClient object using the managed identity credential and storage account URL
blob_service_client = BlobServiceClient(
    account_url=f"https://{storage_account_name}.blob.core.windows.net",
    credential=ManagedIdentityCredential(),
)
