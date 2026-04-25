variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "storage_account_name" {
  description = "Name of the storage account"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "chroma_share_name" {
  description = "Azure Files share name used for persistent Chroma data"
  type        = string
  default     = "chroma"
}

variable "chroma_share_quota_gb" {
  description = "Azure Files share quota in GB for Chroma persistence"
  type        = number
  default     = 100
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
