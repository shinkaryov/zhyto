variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "account_name" {
  description = "Azure OpenAI account name"
  type        = string
}

variable "custom_subdomain_name" {
  description = "Custom subdomain used by Azure OpenAI endpoint"
  type        = string
}

variable "account_sku_name" {
  description = "Azure OpenAI account SKU"
  type        = string
  default     = "S0"
}

variable "public_network_access_enabled" {
  description = "Whether Azure OpenAI public network access is enabled"
  type        = bool
  default     = true
}

variable "default_deployment_name" {
  description = "Default chat deployment name"
  type        = string
}

variable "default_model_name" {
  description = "Default chat model name"
  type        = string
}

variable "default_model_version" {
  description = "Default chat model version"
  type        = string
}

variable "default_deployment_sku_name" {
  description = "SKU name for default chat deployment"
  type        = string
  default     = "GlobalStandard"
}

variable "default_deployment_sku_capacity" {
  description = "SKU capacity for default chat deployment"
  type        = number
  default     = 1
}

variable "enable_advanced_deployment" {
  description = "Whether to create advanced chat deployment"
  type        = bool
  default     = true
}

variable "advanced_deployment_name" {
  description = "Advanced chat deployment name"
  type        = string
}

variable "advanced_model_name" {
  description = "Advanced chat model name"
  type        = string
}

variable "advanced_model_version" {
  description = "Advanced chat model version"
  type        = string
}

variable "advanced_deployment_sku_name" {
  description = "SKU name for advanced chat deployment"
  type        = string
  default     = "GlobalStandard"
}

variable "advanced_deployment_sku_capacity" {
  description = "SKU capacity for advanced chat deployment"
  type        = number
  default     = 1
}

variable "embedding_deployment_name" {
  description = "Embedding deployment name"
  type        = string
}

variable "embedding_model_name" {
  description = "Embedding model name"
  type        = string
}

variable "embedding_model_version" {
  description = "Embedding model version"
  type        = string
}

variable "embedding_deployment_sku_name" {
  description = "SKU name for embedding deployment"
  type        = string
  default     = "GlobalStandard"
}

variable "embedding_deployment_sku_capacity" {
  description = "SKU capacity for embedding deployment"
  type        = number
  default     = 1
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
