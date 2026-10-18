terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.10"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.13"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }
}

provider "azurerm" {
  subscription_id = var.subscription_id

  features {
    # O ambiente existe so durante a demonstracao: o destroy tem de libertar os nomes
    # para o apply seguinte, em vez de os deixar em soft-delete durante dias.
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = false
    }
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
    log_analytics_workspace {
      permanently_delete_on_destroy = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}
