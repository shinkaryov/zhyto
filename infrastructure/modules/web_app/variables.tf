variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "web_app_name" {
  description = "Name of the web app"
  type        = string
}

variable "app_service_plan_name" {
  description = "Name of the app service plan"
  type        = string
}

variable "app_service_plan_sku" {
  description = "SKU of the app service plan"
  type        = string
  default     = "B1"
}

variable "container_registry_url" {
  description = "URL of the container registry"
  type        = string
}

variable "container_registry_id" {
  description = "Resource ID of the container registry"
  type        = string
}

variable "container_image_name" {
  description = "Name of the container image"
  type        = string
}

variable "container_image_tag" {
  description = "Tag of the container image"
  type        = string
  default     = "latest"
}

variable "app_settings" {
  description = "App settings for the web app"
  type        = map(string)
  default     = {}
}

variable "health_check_path" {
  description = "Health check path for backend container"
  type        = string
  default     = "/health"
}

variable "always_on" {
  description = "Always-on behavior for App Service"
  type        = bool
  default     = false
}

variable "enable_app_service_storage" {
  description = "Enables App Service persistent storage mount under /home for Linux containers"
  type        = bool
  default     = true
}

variable "storage_mounts" {
  description = "Storage mounts for app runtime"
  type = list(object({
    name         = string
    type         = string
    account_name = string
    share_name   = string
    access_key   = string
    mount_path   = string
  }))
  default = []
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
