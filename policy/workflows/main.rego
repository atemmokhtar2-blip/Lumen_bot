package main

deny[msg] {
  not input.permissions
  msg := "Workflow must declare explicit top-level token permissions"
}

deny[msg] {
  input.permissions == "write-all"
  msg := "Workflow must not grant write-all token permissions"
}

deny[msg] {
  input.permissions.contents != "read"
  msg := "Workflow repository contents permission must remain read-only"
}
