package main

import rego.v1

has_user if {
  some i
  input[i].Cmd == "user"
}

has_healthcheck if {
  some i
  input[i].Cmd == "healthcheck"
}

deny contains msg if {
  not has_user
  msg := "Dockerfile must run as an explicit non-root USER"
}

deny contains msg if {
  some i
  input[i].Cmd == "user"
  count(input[i].Value) > 0
  lower(input[i].Value[0]) == "root"
  msg := "Dockerfile must not select root as its runtime USER"
}

deny contains msg if {
  not has_healthcheck
  msg := "Dockerfile must define a HEALTHCHECK for orchestrator liveness"
}
