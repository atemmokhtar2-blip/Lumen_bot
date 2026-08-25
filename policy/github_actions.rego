# OPA policies for GitHub Actions workflow documents
package main

# Deny workflows that grant write-all at top level without explicit need marker
deny[msg] {
  input.permissions == "write-all"
  msg := "workflows must not use permissions: write-all"
}

deny[msg] {
  input.permissions.contents == "write"
  input.permissions.id-token == "write"
  not input.permissions.contents == "read"
  msg := "overly broad contents:write with id-token"
}
