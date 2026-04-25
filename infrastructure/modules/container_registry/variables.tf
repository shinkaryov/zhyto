variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "registry_name" {
  description = "Name of the container registry"
  type        = string
}

variable "sku" {
  description = "SKU of the container registry"
  type        = string
  default     = "Basic"
}

variable "admin_enabled" {
  description = "Whether to enable admin user"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

