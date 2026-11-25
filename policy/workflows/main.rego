package main

import rego.v1

deny contains msg if {
  not input.permissions
  msg := "Workflow must declare explicit top-level token permissions"
}

deny contains msg if {
  input.permissions == "write-all"
  msg := "Workflow must not grant write-all token permissions"
}

deny contains msg if {
  input.permissions.contents != "read"
  msg := "Workflow repository contents permission must remain read-only"
}
