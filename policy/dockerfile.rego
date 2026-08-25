# OPA / Conftest policies for Dockerfile — official OPA engine
package main

deny[msg] {
  input[i].Cmd == "user"
  lower(input[i].Value[0]) == "root"
  msg := "Dockerfile must not set USER root"
}

deny[msg] {
  not has_user
  msg := "Dockerfile must set a non-root USER"
}

has_user {
  input[i].Cmd == "user"
  lower(input[i].Value[0]) != "root"
}

deny[msg] {
  input[i].Cmd == "add"
  msg := "Dockerfile must not use ADD (prefer COPY)"
}

deny[msg] {
  not has_healthcheck
  msg := "Dockerfile must define HEALTHCHECK"
}

has_healthcheck {
  input[i].Cmd == "healthcheck"
}
