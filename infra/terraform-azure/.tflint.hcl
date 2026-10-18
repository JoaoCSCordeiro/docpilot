plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "azurerm" {
  enabled = true
  version = "0.31.1"
  source  = "github.com/terraform-linters/tflint-ruleset-azurerm"
}

# O ambiente e efemero por desenho (apply para a demonstracao, destroy logo a seguir); o
# log de queries no Cosmos e os segredos nao tem de sobreviver ao destroy.
rule "azurerm_resources_missing_prevent_destroy" {
  enabled = false
}
