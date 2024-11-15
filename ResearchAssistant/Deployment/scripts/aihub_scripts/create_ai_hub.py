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
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import (
    StorageAccountCreateParameters,
    Sku,
    Kind,
)
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.authorization.models import RoleAssignmentCreateParameters
import uuid


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

# Create a Storage Management client
storage_client = StorageManagementClient(credential, subscription_id)

# Create the storage account if it doesn't exist
storage_account_params = StorageAccountCreateParameters(
    sku=Sku(name="Standard_LRS"),
    kind=Kind.STORAGE_V2,
    location=solutionLocation,
    identity={"type": "SystemAssigned"},
    allow_shared_key_access=False,
)
storage_account = storage_client.storage_accounts.begin_create(
    resource_group_name, storage_account_name, storage_account_params
).result()

# Get the principal ID of the managed identity
principal_id = storage_account.identity.principal_id

# Create an Authorization Management client
auth_client = AuthorizationManagementClient(credential, subscription_id)

# Define the role assignment parameters
role_assignment_params = RoleAssignmentCreateParameters(
    role_definition_id=f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe",  # Role ID for Storage Blob Data Contributor
    principal_id=principal_id,
    principal_type="ServicePrincipal",
)

# Assign the Storage Blob Data Contributor role to the managed identity
scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Storage/storageAccounts/{storage_account_name}"

role_assignment = auth_client.role_assignments.create(
    scope, str(uuid.uuid4()), role_assignment_params
)

print(f"Role assignment created: {role_assignment.id}")

# Create a BlobServiceClient object using the managed identity credential
blob_service_client = BlobServiceClient(
    account_url=f"https://{storage_account_name}.blob.core.windows.net",
    credential=credential,
)

# Create a BlobServiceClient object using the managed identity credential
blob_service_client = BlobServiceClient(
    account_url=f"https://{storage_account_name}.blob.core.windows.net",
    credential=credential,
)

# Define the Hub with Managed Identity
my_hub = Hub(
    name=aihub_name,
    location=solutionLocation,
    display_name=aihub_name,
    storage_account=storage_account.id,
    identity=IdentityConfiguration(type="SystemAssigned"),
)

# Create the Hub
created_hub = ml_client.workspaces.begin_create(
    my_hub, update_dependent_resources=True
).result()

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
