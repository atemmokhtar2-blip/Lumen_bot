package main

has_user {
  input[_].Cmd == "user"
}

has_healthcheck {
  input[_].Cmd == "healthcheck"
}

deny[msg] {
  not has_user
  msg := "Dockerfile must run as an explicit non-root USER"
}

deny[msg] {
  input[i].Cmd == "user"
  lower(input[i].Value[0]) == "root"
  msg := "Dockerfile must not select root as its runtime USER"
}

deny[msg] {
  not has_healthcheck
  msg := "Dockerfile must define a HEALTHCHECK for orchestrator liveness"
}
